# E2E — Auth Suite (Playwright)

End-to-end tests for the auth stack: signup wizard, login hardening, MFA
enrollment/verification, invitation roles, session rotation/reuse/revocation,
the cross-origin handoff, and the tenant dashboard.

Specs (`specs/`):

- `wizard.spec.ts` — five-step signup wizard (account → verification →
  security → plan → organization) through provisioning and forced MFA setup.
- `login-mfa.spec.ts` — no-account-oracle failures, login-budget throttling, MFA
  enrollment, TOTP + backup-code sign-in, single-use backup codes.
- `sessions.spec.ts` — MFA gate before enrollment, session list/trust/revoke,
  refresh rotation + reuse detection, logout revocation.
- `invite.spec.ts` — owner roles, unknown-role 422, token shown once, invite
  acceptance, standard_user grant, double-accept 409.
- `handoff.spec.ts` — cross-origin handoff PRG to the workspace host, host-bound
  session cookie, single-use tokens, wrong-tenant rejection.
- `dashboard.spec.ts` — owner dashboard nav, module pages, member invites
  (create → pending → expire).

## How it runs

The suite is hybrid: the browser drives the wizard/MFA/login UI on `apps/web`,
while the Playwright `request` fixture asserts rotation, reuse, 429/422, and
role checks directly against the identity service.

- Identity: `http://127.0.0.1:8000` (`E2E_API_BASE`)
- Web: `http://localhost:3000` (`E2E_WEB_PORT`)
- Hosts used: `localhost`, `signup.localhost`, `<slug>.signin.localhost`,
  `<slug>.localhost` — browsers resolve any `*.localhost` to loopback natively
  (Chromium). Node's fetch is shimmed in `global-setup.ts` for the API layer.

## Quick start

```sh
make test-e2e          # infra + migrate + keys + identity (TEST mode) on :8000
make dev-web           # web app on :3000 (separate terminal)
```

`make test-e2e` starts identity only if nothing is already listening on `:8000`;
if it finds a healthy instance it reuses it and expects **TEST mode** (see
"Environment requirements").

Then re-run the suite alone with:

```sh
cd apps/web && pnpm test:e2e
```

## Environment requirements

The identity service must run with `IDENTITY_ENVIRONMENT=test`, which returns
plaintext OTP/captcha codes (`sent.code`, `captcha.answer`) the specs assert on.
In `dev` mode those fields are `null` and the suite fails loudly.

Recommended overrides (docker Postgres on `:5433`, Redis on `:6379`):

```sh
IDENTITY_ENVIRONMENT=test \
IDENTITY_DATABASE_URL=postgresql+asyncpg://skyrict:skyrict@127.0.0.1:5433/skyrict_identity \
IDENTITY_REDIS_URL=redis://127.0.0.1:6379/0 \
IDENTITY_JWT_PRIVATE_KEY_PATH=<abs>/skyrict/.dev/keys/private.pem \
IDENTITY_JWT_PUBLIC_KEY_PATH=<abs>/skyrict/.dev/keys/public.pem \
IDENTITY_MFA_ENCRYPTION_KEY=$(python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())") \
uv run --directory services/identity identity serve
```

Notes:

- JWT keys live in the gitignored repo-root `.dev/keys/` (generate with
  `openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:2048 -out .dev/keys/private.pem`
  then `openssl rsa -pubout -in .dev/keys/private.pem -out .dev/keys/public.pem`).
- Migrate before serving: `uv run --directory services/identity alembic upgrade head`.
- The repo `.env` points at the native Postgres on `:5432` in `dev` mode — do
  not run the suite against it. Use the compose Postgres (`:5433`) or set the
  overrides above.
- Do not run the suite against a dev-mode identity already on `:8000`; stop it
  first so `make test-e2e` starts a TEST-mode instance.

### Rate limits

The e2e env relaxes the identity rate limits so one shared runner IP doesn't 429
the suite (serial specs log in ~6x per account; ~9 signups come from the same
IP). Set these alongside the overrides above:

```sh
IDENTITY_RATE_LIMIT_LOGIN=8 \
IDENTITY_RATE_LIMIT_LOGIN_IP=200 \
IDENTITY_RATE_LIMIT_MFA_VERIFY=200 \
IDENTITY_RATE_LIMIT_MFA_ENROLL=200 \
IDENTITY_SIGNUP_START_RATE_LIMIT=200 \
IDENTITY_SIGNUP_CODE_RATE_LIMIT=200 \
IDENTITY_SIGNUP_VERIFY_RATE_LIMIT=200 \
IDENTITY_SIGNUP_CHECK_RATE_LIMIT=200 \
IDENTITY_SIGNUP_CAPTCHA_RATE_LIMIT=200
```

The login-hardening spec still asserts the throttling mechanism: it exhausts
`E2E_LOGIN_RATE_LIMIT` failed attempts (default 5, set to 8 to match
`IDENTITY_RATE_LIMIT_LOGIN`) and then expects the account to be blocked.

## Web app

The web app must be running on `:3000` before the suite. `next start` (a
production build, `pnpm build && pnpm start`) is the most deterministic; `next
dev` also works.

## Playwright

Browsers are installed once per machine:

```sh
cd apps/web && pnpm exec playwright install chromium
```

Run a single spec:

```sh
pnpm exec playwright test --config e2e/playwright.config.ts specs/sessions.spec.ts
```

Artifacts (traces, screenshots, videos) land in `apps/web/e2e/test-results/`.
Use `--trace on` to keep traces for every run.

## CI

`.github/workflows/ci-e2e.yml` runs the suite on push/PR for web + identity
changes: postgres + redis service containers, migrations, identity in TEST
mode, `pnpm build && pnpm start`, then the Playwright suite. On failure the
`test-results/` artifacts are uploaded. The identity service requires the full
`IDENTITY_*` env (DB, Redis, JWT keys, JWKS issuer/audience, the generated
`.dev/e2e-mfa.key` Fernet key, and the relaxed rate-limit overrides from "Rate
limits") — the workflow exports all of them at job level.
