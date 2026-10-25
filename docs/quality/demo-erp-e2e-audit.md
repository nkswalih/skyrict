# Demo ERP — E2E audit, bugs and fixes

Status: **fixed — all findings applied, suite green**
Last verified: 2026-10-25
Suite: `apps/web/e2e/demo-erp.spec.ts` (`demo` Playwright project)

```bash
# local (boots Next dev on the marketing surface automatically)
pnpm --filter @skyrict/web exec playwright test --project=demo --workers=1

# CI shape (nginx + `next start`, same as the rest of e2e.yml)
E2E_BASE_URL=http://default.localhost:3000 \
E2E_DEMO_BASE_URL=http://localhost:3000 \
E2E_SKIP_WEBSERVER=1 \
pnpm --filter @skyrict/web exec playwright test --project=demo
```

Current result: **26 passing, 0 expected failures** (3.3 min at `--workers=2`).
Every bug below is fixed; the suite grew from 16 tests (12 real + 4
`test.fail`) to 18 real tests for the original audit, then to 26 when the
product shell (profile, notifications, settings) was restored. No
`test.fail(...)` marker remains.

---

## 1. Why the old spec did not run

`demo-erp.spec.ts` was not referenced by any Playwright project, so
`playwright test e2e/demo-erp.spec.ts` reported `No tests found`. It also
assumed the workspace origin (`http://default.localhost:3000`), where
`/demo/erp` is rewritten to `/dashboard/demo/erp` and redirected to
`{tenant}.signin.localhost` without a session. The demo is a **marketing-surface**
route (`localhost` / `web.*`), never an authenticated tenant route.

Fixes in this change:

- new `demo` project in `apps/web/playwright.config.ts`, with
  `baseURL` derived from `E2E_BASE_URL` (host replaced by `localhost`) or
  `E2E_DEMO_BASE_URL`, and **no `setup` dependency**;
- `--project=demo` added to the main E2E workflow job;
- spec rewritten as a real visitor journey (see coverage below).

## 2. What the suite now covers

| Area | Assertions |
| --- | --- |
| Direct entry | 200, demo banner, `robots: noindex`, no redirect to signin |
| Dashboard | seeded KPI values, 6 quick-access tiles rewritten to `/demo/erp/*` |
| Navigation parity | 51 sidebar routes deep-link, correct heading, no 404 page |
| CRM leads | add → filter (name/company/empty) → detail route → back → delete → reset |
| CRM kanban | prospecting → qualified → proposal → negotiation → won, CRM totals recompute |
| Inventory | add product → persisted in `localStorage` → reset restores seed |
| Finance / orders / HR / payroll | seeded ledger, invoices, orders, employees and payroll runs |
| AI gate | 13 gated routes show the gate + CTA, never call the AI stack |
| Account chrome | persona avatar/name, demo-safe user menu, Settings link, bell with unread count |
| Notifications | inbox → detail → mark read → mark all read → snooze, all persisted |
| Profile | edit + save, sidebar persona updates, public preview, reset restores seed |
| Appearance | light/dark/system + density + reduced motion on the demo shell only |
| Settings | workspace + notification preferences persist; security revoke/passkey; integrations connect/filter |
| Sign-out | confirm dialog, cancel stays, confirm exits to `/`, never calls `/api/auth/logout` |
| Mobile | 390×844 banner + drawer navigation |
| Conversion | banner CTA hands off to the signup surface |
| Isolation | every test blocks `**/api/**`, records attempts, asserts zero |
| Console | zero console errors, zero page warnings, zero hydration mismatches |

## 3. Bugs found (verified against the running app)

All nine are fixed. Each section keeps the original reproduction and root
cause; the **Fixed:** note records what actually landed.

| Bug | Severity | Fixed in |
| --- | --- | --- |
| BUG-DEMO-001 hydration mismatch | High | `demo-store.ts`, `demo-provider.tsx` |
| BUG-DEMO-002 live shell in demo | High | `topbar.tsx`, `app-sidebar.tsx`, `demo-erp-shell.tsx`, `session.tsx` |
| BUG-DEMO-003 topbar breadcrumb + duplicate `h1` | Medium | `page-title.ts`, `topbar.tsx` |
| BUG-DEMO-004 dashboard KPI semantics | Medium | `app/demo/erp/page.tsx` |
| BUG-DEMO-005 `/demo` 404 | Medium | `app/demo/page.tsx` |
| BUG-DEMO-006 soft-404 unknown paths | Medium | `app/demo/erp/[...slug]/layout.tsx` |
| BUG-DEMO-007 substring AI gating | Medium | `lib/demo/demo-routes.ts` |
| BUG-DEMO-008 narrow network guard | Low/Medium | `demo-network-guard.ts` |
| BUG-DEMO-009 CRUD/a11y polish | Low | `[...slug]/page.tsx`, `demo-store.ts` |

### BUG-DEMO-001 — Hydration mismatch after any edit + reload (High)

Reproduction: add a lead → reload → row is present, but React throws
“Hydration failed because the server rendered text didn't match the client”.

Root cause: `src/components/demo/demo-provider.tsx:21` initialises state with
`useState(getDemoState)`, and `getDemoState()` reads `localStorage` on the
client. The server HTML is rendered from `SEED_DATA`, so once storage differs
from the seed the first client render mismatches.

Fix (recommended): keep the server snapshot deterministic and hydrate storage
after mount.

```tsx
const [state, setStateInternal] = useState<DemoState>(SEED_DATA);
useEffect(() => {
  setStateInternal(getDemoState());
  // ...
}, []);
```

or use `useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot)`.
`getDemoState()` must stop writing to `localStorage` during render (it currently
does so when the key is absent).

Acceptance: the `edits survive a full reload…` test loses `test.fail` and stays
green; no hydration console/page errors.

**Fixed:** `demo-store.ts` now exports a deterministic `createDemoSeedState()`
(no `new Date()` at module scope). `DemoProvider` starts from that seed and only
calls `getDemoState()` / `ensureDemoStorage()` in a mount effect, so server and
first client render match. Reads are pure and writes are copy-on-write.

### BUG-DEMO-002 — Live shell leaks into the demo (High)

The demo reuses the workspace `Topbar` and `AppSidebar`:

- the notification bell calls `/api/v1/notifications/counts` on every page load
  (blocked by the demo fetch guard, so a `console.warn` + a
  “Could not load notifications” dialog instead of data);
- the bell’s preferences links point to `/settings/notifications`;
- the topbar `Settings` link points to `/settings` → **404** on the marketing
  surface;
- the sidebar footer renders `UserMenu` (“Account”) with `Profile settings`
  (`/settings`, 404) and `Sign out`, which POSTs `/api/auth/logout` and leaves
  the demo.

Fix: give the demo shell an explicit demo mode. Either

1. pass `mode="demo"` into `Topbar`/`AppSidebar` and render a demo top bar
   (no bell, no live settings) plus a “Create workspace” / “Exit demo” action;
   or
2. build `DemoTopbar`/`DemoFooter` components and stop reusing the live ones.

Also skip `SessionProvider.restore()` when `pathname.startsWith("/demo")`;
today every demo page still requests `/api/auth/session`. That request is not
covered by the `/api/v1` guard, so “zero backend traffic” is not actually true.

Acceptance: the shell test loses `test.fail`; all `/api/*` requests are zero
(extend the spec to assert this once the session skip lands).

**Fixed:** `SessionProvider` skips restore entirely under `/demo` and clears any
in-memory token; the spec blocks `**/api/**` and asserts zero attempts. The
first pass isolated the shell with a demo badge, a “Create workspace” button and
a demo footer. Client review rejected that shape (it read as a stripped-down
product and the CTA implied workspace creation, which the demo cannot do), so
the final state keeps the real shell and makes every control demo-safe instead —
see §7.

### BUG-DEMO-003 — Topbar title is a path breadcrumb and duplicates the h1 (Medium)

`resolvePageTitle()` (`src/lib/page-title.ts`) does not understand `/demo/erp`,
so the topbar reads e.g. `Overview · Demo · Erp · Crm · Leads`. The topbar and
`PageHeader` both render `<h1>` (two h1s per page, and verbose screen-reader
output).

Fix: normalise `/demo/erp/*` to the ERP route map (or add explicit demo titles
in the shell), and render the topbar title as a non-heading element
(`<p>`/`<span>`), leaving one `<h1>` per page.

Acceptance: topbar test loses `test.fail`.

**Fixed:** `page-title.ts` gained a demo title map plus demo-aware fallbacks, and
the topbar title renders as `<p>` so each page keeps exactly one `<h1>`.

### BUG-DEMO-004 — Dashboard KPIs disagree with the modules (Medium)

`src/app/demo/erp/page.tsx`:

- “Active Pipeline” sums **all** opportunities, including `won`/`lost`;
- “5 open opportunities” counts the won deal;
- “Orders Confirmed” counts **all** orders, including `draft`;
- the volume next to it also includes drafts.

CRM overview correctly filters won/lost, so the two screens disagree. Fix:
filter `stage !== "won" && stage !== "lost"` and
`status === "confirmed" || status === "fulfilled"`; rename to “Open Pipeline”
and “Confirmed / Fulfilled Orders” if the semantics stay.

Acceptance: dashboard semantics test loses `test.fail`; add a mutation test that
wins a deal and re-checks both screens.

**Fixed:** the dashboard uses the same definitions as CRM: open pipeline excludes
`won`/`lost`, confirmed volume excludes `draft`/`cancelled`, payroll uses active
employees. The kanban test wins a deal and asserts dashboard and CRM agree.

### BUG-DEMO-005 — `/demo` and `/demo/` are 404 (Medium)

Only `/demo/erp` exists. The marketing header’s “Try demo” works, but a shared
`/demo` link (or a user trimming the URL) hits the 404 page.

Fix: add `src/app/demo/page.tsx` with `redirect("/demo/erp")` (or a middleware
redirect); add a test.

**Fixed:** `src/app/demo/page.tsx` redirects to `/demo/erp`; the E2E suite asserts
the redirect lands on the walkthrough.

### BUG-DEMO-006 — Unknown demo paths are soft-404s (Medium)

`/demo/erp/does-not-exist` returns **200** and renders the fallback page with
the title “Does Not Exist”. The catch-all fallback is intentionally generous,
but typos look like real modules and are indexable-ish (meta noindex saves it
from search, not from confusion).

Fix: maintain an explicit route allowlist (or first-segment allowlist) and
`notFound()` for anything else; keep a friendly demo 404 with links to the
modules. Add a test asserting 404.

**Fixed:** `lib/demo/demo-routes.ts` owns the allowlist, and
`app/demo/erp/[...slug]/layout.tsx` calls `notFound()` server-side. Unknown paths
now return a real 404; the in-app fallback remains for client navigation.

### BUG-DEMO-007 — AI gate detection is substring-based (Medium)

`src/app/demo/erp/[...slug]/page.tsx:678` uses
`routePath.includes("ai") || includes("planning") || …`. This:

- misclassifies unrelated future routes containing `ai` (e.g. `maintenance`,
  `email`, `domain`);
- misses AI-gated nav entries whose paths do not contain those strings:
  `inventory/abc`, `hr/attrition`, `hr/compliance`, `hr/correlation`
  (all carry `erp.ai.*` permissions in `sidebar-config.ts`).

Fix: export a `DEMO_AI_ROUTES` set (or derive from nav permissions), use exact
matches, and gate every AI nav row consistently. Add a parity test driven by the
same list.

**Fixed:** `DEMO_AI_ROUTES` is an explicit exact-match set that includes
`inventory/abc`, `hr/attrition`, `hr/compliance` and `hr/correlation`; the spec
iterates a 13-route gate list.

### BUG-DEMO-008 — Network guard is narrower than the claim (Low/Medium)

`installDemoNetworkGuard()` only patches `window.fetch` and is installed in an
effect. XHR/EventSource/`sendBeacon` are not covered, `/api/auth/*` is not
covered, and any request fired before the effect escapes. It also logs a
warning on every blocked call, which is noise in the console.

Fix: install the guard before paint (module init in the demo shell or a tiny
inline script), cover `XMLHttpRequest` and `navigator.sendBeacon`, and exclude
the whole `/api/` tree — or better, stop the calls at the source (BUG-DEMO-002)
and keep the guard as defence-in-depth without console noise.

**Fixed:** the guard patches `fetch`, `XMLHttpRequest` and `navigator.sendBeacon`
for same-origin `/api/*`, installs at module init on a direct demo URL (and in an
effect for SPA entry), and stays silent. Because BUG-DEMO-002 removed the callers,
it is now pure defence-in-depth; E2E asserts zero `/api/**` traffic.

### BUG-DEMO-009 — CRUD and accessibility polish (Low)

- Delete buttons are icon-only with **no `aria-label`**
  (`[...slug]/page.tsx:281`); same for several other icon actions.
- Tables lack `scope="col"`.
- Filtering leads to zero rows with no empty-state message.
- Unknown lead id renders an empty detail card (“Email:”, “Phone:”, …).
- New lead id uses `Date.now()` (collision risk if two adds land in the same
  millisecond) and the email slug leaves punctuation in place.
- `state.updatedAt` is mutated in `setDemoState` (input mutation).
- Cross-tab sync listens only to a custom event; a `storage` listener is needed
  for two tabs.

Fix: add labels/empty states/`notFound`, use `crypto.randomUUID()`, copy state
before stamping `updatedAt`, subscribe to `storage`, and add a confirmation or
undo for destructive actions (optional for a demo).

**Fixed:** delete buttons have `aria-label="Delete lead …"`, tables use
`scope="col"`, both filters have result counts and empty states, an unknown lead
renders “Lead not found”, ids use `crypto.randomUUID()` with a fallback, email
slugs strip punctuation, `setDemoState` copies before stamping `updatedAt`, and
`subscribeDemoState` listens to both the custom event and `storage`.

## 4. Parity gaps (not bugs, but sales-demo quality)

**Resolved** by seeding real screens rather than hiding modules. These sidebar
routes previously rendered the generic “Module Records” fallback:

- CRM: contacts, activities, search
- Inventory: warehouses, movements, alerts, ABC, stock health
- HR: departments, leave, attendance, data quality, attrition, compliance,
  correlation
- Finance: accounts, fiscal periods, statements, controls, audit log, settings
- Payroll: reviews, compensation, settings
- Documents: overview/list (list is an alias of the same fallback)

Two acceptable strategies:

1. **Hide until built** — mark these nav items `soon` in the demo shell (as the
   workspace already does for Integrations), so a visitor never lands on
   boilerplate.
2. **Seed the real layout** — reuse the live module’s shell with 3–5 demo rows.

Do not leave them as generic text: a prospect clicking “Audit Log” and seeing
“Module Records” reads as unfinished.

**Applied:** `lib/demo/demo-modules.ts` defines seeded, state-derived specs for
every route above, rendered by `components/demo/demo-module-records.tsx` with
typed columns, right-aligned numeric cells, status badges, filter counts and
empty states. The E2E navigation-parity test covers all 51 sidebar routes.

Other improvements worth doing after the bugs:

- derive payroll totals from `employees` (currently hard-coded ₹670,000 while
  the roster is editable);
- add an empty state + result count to lead/product filters;
- add a “reset all demo data” confirmation/toast and cross-tab sync;
- add `Disallow: /demo` to `robots.txt` as defence-in-depth (the meta noindex is
  already correct);
- add an analytics event on the demo CTA and on “Create real workspace”.

**Applied:** payroll totals derive from active employees (₹670,000 with the
seed); lead/product filters show `Showing X of Y` plus empty states; the demo
store syncs across tabs via `storage`; `robots.txt` disallows `/demo`. The
analytics event is intentionally **not** added: the demo is a no-tracking
surface by design, and the app has no analytics client to call.

## 5. Fix plan (applied)

| Phase | Change | Size | Status |
| --- | --- | --- | --- |
| 0 | `/demo` redirect, robots disallow, delete `aria-label`s, empty states, `scope="col"` | S | done |
| 1 | Hydration fix (server snapshot → mount effect) | S | done |
| 1 | Demo shell mode: no session restore, no live bell/logout | M | superseded by §7 |
| 1 | Topbar title normalisation + single `h1` | S | done |
| 1 | Dashboard KPI filters | S | done |
| 2 | Explicit AI route map + parity test | S | done |
| 2 | Route allowlist / real 404 | M | done |
| 2 | Nav parity (seeded screens for every sidebar route) | M | done |
| 3 | CRUD hardening (UUID, validation, empty states, cross-tab) | M | done |
| 3 | Derive payroll, add filter counts | S | done |
| 4 | A11y basics (labels, `scope`, one `h1`); Lighthouse remains a future gate | M | partial |

**Definition of done:** met. `--project=demo` has **26 passing, 0 expected
failures**, and the spec asserts zero `/api/**` requests on every screen that
stays inside the demo.

## 6. Verification log

- Final: `npx playwright test --project=demo --workers=2` → **26 passed** (3.3 min).
- Also green: `npx tsc --noEmit` (exit 0),
  `npx vitest run src/components/dashboard/workspace src/lib/demo` (33 passed),
  and `eslint` over the demo + workspace shell sources (0 warnings).
- Pre-fix baseline: 16 tests (12 real + 4 expected failures), 2.9 min.
- Probes confirmed pre-fix: `/settings` → 404, `/demo` → 404,
  `/demo/erp/unknown` → 200 soft-404, `/api/auth/session` on every demo page,
  notification `counts` blocked with a console warning.
- Post-fix probes: `/demo` → 307 → `/demo/erp`; unknown demo path → 404;
  zero `/api/**` requests; no hydration console/page errors.
- Hydration error was captured verbatim from React before the fix.
- Lighthouse on `/demo/erp` is not run in CI; keep it as a future quality gate.

## 7. Restored product shell (post-audit revision)

The original fix removed the live account surface from the demo. Client review
found the result misleading in the other direction: the demo looked like a
different, thinner product, and the topbar “Create workspace” button implied the
demo could provision a workspace. This revision keeps the real shell and makes
every control demo-safe.

### What changed

| Area | Final behaviour |
| --- | --- |
| Topbar | Settings link → `/demo/erp/settings`, demo notification bell. No “Demo” badge, no workspace-creation button, no product-tour button. |
| Sidebar footer | The real `UserMenu` row (avatar, name, email, menu). No demo CTA block. |
| User menu | Persona `Priya Sharma · priya@skyrict.demo`; “Profile settings” → `/demo/erp/settings`; “Sign out” confirms, explains that edits stay in the browser, then exits to `/` via `window.location.assign`. No `/api/auth/logout`. |
| Dashboard | “Deploy Live Instance” removed; the demo is not a deployment surface. |
| Notifications | Six seeded notifications, unread badge, inbox → detail, mark read/all read, snooze, preferences link. State lives in `skyrict:demo:v3`. |
| Settings | `/demo/erp/settings` plus `appearance`, `workspace`, `notifications`, `billing`, `security`, `integrations`. Details are seeded (6/8 integrations connected, 3 sessions, 2 passkeys, plan + invoices). |
| Profile preview | `/demo/erp/profile` derives from the same snapshot, so a profile edit is visible immediately. |
| Appearance | Theme (light / dark / system), table density, reduced motion. Applied with `data-demo-theme`, `data-demo-density`, `data-demo-motion` on the shell; the live `.dark` class and theme tokens are untouched. |

### Intentional constraints

- The demo banner was **not** touched: “Running with localized sample records…”,
  “Reset sample data”, and the banner’s own “Create real workspace” signup link
  all stay exactly as shipped.
- Every settings screen writes only to `localStorage`; no screen imports an API
  client. The network guard stays as defence-in-depth and each in-demo test
  asserts zero `/api/**`.
- Billing is read-only and says so in a dialog; “Talk to sales” and integration
  requests hand off to `/signup`.
- Table density is defined once, under Appearance. An earlier pass also exposed a
  workspace-level “Compact density” switch that only wrote a flag with no visual
  effect; that duplicate was removed rather than wired to a second source of
  truth.
- Demo state keeps schema `version: 3`; the new profile/preferences/security/
  integrations blocks are merged defensively so an older snapshot in a visitor’s
  browser still hydrates.

### New E2E coverage

Eight tests were added or rewritten for the restored shell: account chrome and
absence of creation affordances, settings route/title parity, notification
inbox read/snooze, profile save + preview, appearance switching (including a
computed `--background` check and a reload), workspace + notification
preferences, security revoke/passkey/2FA, integrations connect/filter, and
demo-safe sign-out. The obsolete “no live account, settings or notification
controls” test was deleted because it asserted the opposite of the product
decision.

