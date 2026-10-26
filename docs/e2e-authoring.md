# E2E authoring guide (SKY-103)

How to write and run Playwright end-to-end tests for the Skyrict web app.
The harness lives in `apps/web/e2e/` and runs in CI via
`.github/workflows/e2e.yml`.

## Architecture

Playwright operates in a **host browser** driving the real stack through
nginx. Tenant isolation is exercised through real subdomains:

```
{slug}.localhost:3000  ──►  nginx (container)  ──►  Next.js :3100 (host)
                                └─ injects X-Tenant-Slug
```

Next.js runs on the host (port 3100) behind nginx (port 3000). Next.js is
the single BFF entrypoint: it handles `/api/auth/*` itself and proxies
`/api/v1/*` to the identity/core/ai-agent containers. The E2E nginx conf
(`infra/nginx/e2e.conf`) routes **all** traffic to Next.js — unlike the dev
conf, it never talks to a service directly, because the BFF boundary is what
a real browser hits.

Identity (8000) and Core (8001) ports are published to the host so the
host-side Next.js BFF can reach them via the `API_PROXY_TARGET` /
`CORE_PROXY_TARGET` defaults (`http://localhost:8000` / `:8001`). AI-Agent
stays internal-only — the BFF never talks to it directly (core proxies).

Backends run in a production-like compose stack
(`infra/docker/docker-compose.e2e.yml`): Postgres (pgvector), Redis, Mailpit,
Identity, Core, AI-Agent. Each service migrates and seeds on boot; the CI
workflow additionally seeds the identity admin and the core report catalog.

> **Identity is in `ENVIRONMENT=test` in E2E.** That enables the plaintext
> OTP/captcha affordances the wizard driver uses (the `code`/`answer` fields
> the BFF relays). Do not assert on those in prod-shape specs.

## Running

### Local, full stack (mirrors CI)

```bash
# 1. Boot the compose stack (uses .dev/keys for JWT signing).
docker compose -f infra/docker/docker-compose.e2e.yml up -d --build

# 2. Seed the databases (idempotent). The E2E compose uses Dockerfile.dev
#    images which have uv, but the commands below call the module entry
#    points directly via PYTHONPATH (set in the container env).
docker compose -f infra/docker/docker-compose.e2e.yml exec -T identity \
  python -m identity.seed
docker compose -f infra/docker/docker-compose.e2e.yml exec -T core \
  python -m core.seed \
  --tenant-id 00000000-0000-0000-0000-000000000001

# 3. Build and serve the web app on :3100 (the E2E nginx proxies to it).
pnpm --filter @skyrict/web build
$env:SESSION_COOKIE_SECURE = "false"
$env:PORT = "3100"
Start-Process -NoNewWindow pnpm "--filter @skyrict/web start"

# 4. Run the suite.
$env:E2E_SKIP_WEBSERVER = "1"
$env:E2E_BASE_URL = "http://default.localhost:3000"
pnpm --filter @skyrict/web exec playwright test
```

The CI workflow automates exactly these steps. Locally you can also let
Playwright boot `next dev` itself (omit `E2E_SKIP_WEBSERVER=1`) against a
compose stack or the dev stack.

### Local, web app + dev servers only

```bash
pnpm --filter @skyrict/web exec playwright test   # boots `next dev` on :3000
```

`SESSION_COOKIE_SECURE=false` is required on `http://localhost` — the
`applySessionCookie` helper (`apps/web/src/lib/server/auth.ts`) forces
cookie `Secure` off when the env var is set to `"false"` so the browser jar
accepts the session cookie over loopback. This is a **test-only transport
override**, not the security boundary under test; prod default behavior
(`Secure` on) is unchanged.

### Demo only (public marketing surface)

`/demo/erp` is a public, session-free route served from the **marketing**
origin (`localhost`), not from a tenant subdomain. It has its own `demo`
Playwright project so it never touches auth setup or `storageState`.

```bash
# local: boots `next dev` on :3000 and runs just the demo journey
pnpm --filter @skyrict/web exec playwright test --project=demo --workers=1

# CI / pre-built: point the project at the already-running web server
E2E_SKIP_WEBSERVER=1 \
E2E_DEMO_BASE_URL=http://localhost:3000 \
pnpm --filter @skyrict/web exec playwright test --project=demo
```

`baseURL` is derived from `E2E_BASE_URL` with the host swapped to `localhost`
(so the existing CI env keeps working), or set explicitly with
`E2E_DEMO_BASE_URL`. The project has no `setup` dependency and no
`storageState` — the spec asserts the demo works entirely from the seed +
`localStorage`, with `/api/**` blocked and asserted at zero. `SessionProvider`
skips BFF session restore on `/demo`, so the walkthrough makes no backend calls
at all.

Do **not** run the demo spec on a tenant origin: `/demo/erp` there is
rewritten to `/dashboard/demo/erp` and redirected to signin without a session.

The demo runs the same product chrome as a real workspace — profile menu,
notification inbox, and Settings (profile, appearance, workspace, notifications,
billing, security, integrations). Those screens are demo-safe mocks over the
same `localStorage` snapshot: theme, density and motion apply through
`data-demo-theme` / `data-demo-density` / `data-demo-motion` on the demo shell,
so the live workspace theme is never touched. When adding a test there, assert
the *user-visible* result (heading, badge, persisted snapshot) rather than the
component that renders it; the demo deliberately reuses live layout components,
so component-level assertions would pass even if a screen crashed.

Two practical rules learned from this suite:

- The bell and topbar controls are `aria-hidden` while the notification dialog
  is open. Assert them after closing the dialog, or read
  `skyrict:demo:v3` directly.
- Sign-out is the one test that must **not** call `expectClean`: leaving `/demo`
  for `/` legitimately hydrates the real session (`/api/auth/session`). Instead
  record requests and assert none of them is `/api/auth/logout`.


## The two worker-scoped fixtures

Every Playwright worker owns exactly one browser context so its cookie jar
advances a single refresh-token rotation chain (see "Token rotation" below).
Never load the same storage-state snapshot into two contexts.

| Fixture | Where | Session | Use when |
| --- | --- | --- | --- |
| `workspace` | `e2e/fixtures/auth.ts` | Seeded **default** tenant admin (`admin@skyrict.io`), UI sign-in + MFA | Specs that need the seeded baseline (e.g. the report catalog) |
| `tenant` | `e2e/fixtures/tenants.ts` | **Brand-new** tenant onboarded through the real signup wizard + MFA | Multi-tenant specs that need isolated data |

> The two fixtures are separate `test` exports. The `reports` spec imports
> `test` from `fixtures/auth` (the seeded catalog is what it asserts); a
> tenant-isolation spec imports `test` from `fixtures/tenants`.

## Writing a spec

1. Import the fixture's `test`, not `@playwright/test`:
   ```ts
   import { expect } from "@playwright/test";
   import { test } from "./fixtures/tenants"; // or ./fixtures/auth
   ```
2. Destructure the session and drive the live page:
   ```ts
   test("...", async ({ tenant }) => {
     const { page } = tenant;
     await page.goto("/dashboard/erp/reports");
     await expect(page.getByRole("heading", { level: 1, name: "Reports" })).toBeVisible();
   });
   ```
3. Reach the surfaces with the URL builders (`e2e/support/urls.ts`):
   `workspaceUrl(slug)`, `signinUrl(slug)`, `signupUrl(slug)`,
   `marketingUrl()`. The Playwright `baseURL` is already the workspace origin
   for your fixture, so relative `page.goto("/dashboard/...")` works there.
4. Need a browser-side re-hydration? `tenant.refreshSession()` (or
   `workspace.refreshSession()`) runs `fetch("/api/auth/session",
   { credentials: "include" })` in the page — the same-origin call rotates
   the refresh token in the jar.

### Token rotation — rules that keep the suite green

- Identity rotates the refresh token on **every** `/api/auth/session`
  hydration and treats an already-rotated token as reuse → revokes the whole
  session family.
- Keep each worker's chain on **one context**. Worker-scoped fixtures do
  this for you — do not re-open contexts or load `storageState` files.
- Keep long flows in **one test with `test.step()` blocks** (the reports
  spec is the canonical example): splitting across tests makes Playwright
  reopen pages and trips the reuse detector in the rotation window.
- The `installSessionRefresh` interceptor (installed by the fixtures)
  re-hydrates on 401 so the jar's token stays current across navigation.
- Browser-side `fetch` (via `page.evaluate`) is the refresh mechanism.
  `context.request` runs Node-side and cannot resolve `*.localhost` — avoid
  it for auth-bearing calls.

### Tenant onboarding helper

`registerTenant(page, { email, password, slug })` drives the full 5-step
wizard (account → verify → security → plan → organization) using the
test-environment plaintext OTP/captcha responses, and provisions the tenant.
Use it for one-off onboarding, or rely on the `tenant` fixture which wraps
it plus sign-in + MFA.

## Environment variables

| Variable | Default | Purpose |
| --- | --- | --- |
| `E2E_BASE_URL` | `http://default.localhost:3000` | Origin Playwright hits (nginx) |
| `E2E_SKIP_WEBSERVER` | unset | `"1"` reuses the externally started origin (CI) |
| `E2E_TENANT_SLUG` | `default` | Slug the `workspace` fixture authenticates against |
| `E2E_ADMIN_EMAIL` | `admin@skyrict.io` | Seeded admin login |
| `E2E_ADMIN_PASSWORD` | `Admin123!` | Seeded admin password |
| `E2E_TOTP_SECRET` | none | Needed when the admin **already** has MFA enrolled (challenge path) |
| `SESSION_COOKIE_SECURE` | unset | `"false"` forces cookie `Secure` off for the loopback origin |

## Seeding (idempotent, never modified per scenario)

- `identity seed` → default tenant (`00000000-...-0001`), roles, admin user.
- `core seed --tenant-id 00000000-...-0001` → report catalog for the default
  tenant (what `reports-workspace.spec.ts` asserts).

Test-specific tenants are created **through the signup wizard**, never via
hidden DB writes or seed changes.

## CI

`.github/workflows/e2e.yml` (push to `dev`/`main`, or PR) runs on
ubuntu-latest: pnpm install → generate JWT keys → `docker compose up -d
--build` → wait → seed → `next build` → `next start -p 3100` (background) →
`playwright test` → artifacts (HTML report + test-results) → compose
teardown. Playwright runs with 2 workers via the config.

The workflow only runs when `apps/web/**`, `services/**`, `infra/**`,
`scripts/e2e/**`, or the workflow itself change.

## Gotchas

- **Don't weaken boundaries.** Do not add header-injection shortcuts as the
  primary path, do not share auth state between workers, do not seed
  per-scenario data, and do not gate CI on `next dev`.
- **Ports.** 3000 is nginx, 3100 is Next.js, 8000 is identity (host-published), 8001 is core (host-published); keep split in mind when
  debugging.
- **`localhost` host resolution.** Only Chromium can resolve `*.localhost`
  subdomains (Node cannot). All `fetch`/probes from the pnpm side must use
  plain `localhost`.
- **Horizontal scroll / mobile** specs are out of scope for this harness —
  viewport is desktop-only.