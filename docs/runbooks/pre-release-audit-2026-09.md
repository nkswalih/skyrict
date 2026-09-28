# Pre-Release Audit — Findings & Fix Plan

Status: **16 commits landed on `fix/remove-obsolete-skyrict-com-domain`,
unpushed.** The evidence below is the state *before* those commits and is left
as written, because it is what the findings were measured against. Per-finding
outcome is in "Fix status" below. No commit has been pushed and no PR is open.

Evidence base: 3,582 unit tests, 443 live endpoints probed against a full
docker-compose stack, a complete authenticated flow (login -> MFA enroll ->
MFA verify -> privileged reads on both services), 3 production Dockerfiles
built and booted, a config-vs-IaC coverage diff, the Playwright `ai` project
and all 10 orphaned E2E specs executed for the first time, and a manual
signed-in pass over every workspace surface (18 pages, 15 API reads, the AI
chat SSE stream, logout) with a container log scan for 5xx and tracebacks.

---

## Verified healthy (no action)

| Area | Result |
|---|---|
| Unit tests | identity 750, core 1457, ai-agent 1375 = **3582 pass** |
| `ruff check` / `ruff format --check` | **clean** (1364 files) |
| `mypy` identity / core / ai-agent | **no issues** (147 / 337 / 326 files) |
| Web unit tests | 52 files, 503 tests pass |
| Endpoint sweep | 443 endpoint/method pairs, **0 unexpected 5xx**, 0 connection failures |
| Container health | all 7 E2E containers healthy |
| Public endpoints | `/health` and `/ready` correct on identity + core |
| Auth flow | login -> MFA setup -> MFA enroll -> MFA verify -> privileged token, all 200 |
| Identity protected reads | 11/11 return real data (`/users/me`, `/roles/me` = `["*"]`, `/permissions`, `/sessions`, `/members`, billing, invitations) |
| Core protected reads | 12/12 return real data (sales, inventory, crm, reports, finance, hr, payroll, approvals, documents, ai) |
| Tenant isolation | mismatched hint -> **401 tenant-mismatch**; JWT-only -> 200; tampered token -> 401; no token -> 401 |
| **Playwright CI main phase** | **6/6 pass** (setup, dashboard-smoke, reports-workspace, crm-pipeline, finance-journeys, perf cold-start) |
| Error contract | RFC 7807 problem+json throughout |
| Passkeys | 3 endpoints return an intentional, correctly-formatted **501** |
| **Manual signed-in pass** | 18/18 workspace pages render 200, 15/15 BFF API reads 200, logout revokes the session |
| **AI chat SSE** | streams real frames end to end through core and through the BFF (`classification`, `agent_start`, `token`) |
| Four-surface vhost model | signin -> MFA -> single-use handoff -> workspace all work; unauthenticated workspace is 307-gated |

**Fixed as part of the fix series:** tenant source of truth moved
from Host to the verified JWT claim, with the client-asserted
`X-Tenant-Slug` demoted to a non-authoritative routing hint that must agree
with the token. Covers all 3 services + 14 new tests. Without this, every
business request would 400 on `api.skyrict.in` (and on the default ACA FQDN),
because `api` is in `RESERVED_SLUGS`.

---

## Fix status

| # | Finding | Outcome |
|---|---|---|
| 1 | Dockerfiles cannot boot | **Fixed** — sources copied before `uv sync`, boot gated on import |
| 2 | Worker counts OOM | **Fixed** — `--workers 1` in all 3 production images; replicas scale horizontally |
| 3 | No email delivered | **Open** — needs SMTP relay credentials |
| 4 | Billing dead (503) | **Open** — needs Stripe keys |
| 5 | No AI provider | **Open** — needs provider key + model |
| 6 | No API host exists | **Fixed** — nginx gateway is the single public origin, ACA managed cert bound to `api.skyrict.in` |
| 7 | CORS blocks chat SSE | **Open — see below** |
| 8 | `jwksIssuer` wrong host | **Fixed** — issuer and audience both `api.skyrict.in`; Preflight enforces |
| 9 | Readiness probe shallow | **Fixed** — `/api/v1/ready` for readiness, `/api/v1/health` kept for liveness |
| 10 | Redis override trap | **Fixed** — empty `REDIS_URL` rejected at startup; Preflight guards the swap |
| 11 | Budget alerts notify nobody | **Fixed** — budget skipped when no contacts, `$200` amount, loud warning |
| 12 | `minReplicas: 0` | **Fixed** — backends warm at 1 via `keepBackendsWarm` |
| 13 | DB ceiling exceeds SKU | **Open** — `dbMaxOverflow` still 0 vs B1ms `max_connections` 50 |
| 14 | `environmentMaxNodes: 2` | **Open** — unchanged |
| 15 | `concurrentRequests: 100` | **Partial** — gateway has its own 500; backends unchanged |
| 16 | Problem URIs wrong domain | **Fixed** — one shared `PROBLEM_BASE_URL`, 58 dead constants deleted |
| 17 | 20 config vars never injected | **Open** — needs SMTP, Stripe, AI, Sentry, S3 credentials |
| 18 | AI E2E project broken | **Open** |
| 19 | 10 orphaned E2E specs | **Open** |
| 20 | Stale TOTP breaks E2E | **Open** |
| 21 | Documentation stale | **Partial** — this record + module docs updated; runbooks still open |
| 22 | `_template` propagates #1 | **Fixed** |
| 23 | Signup blocked, UI says "Verified" | **Fixed structurally** — Key Vault secretRef + Preflight hard-fail. **Blocked on real Turnstile keys** |
| 24 | E2E shares one admin identity | **Open** |
| 25 | L3 no-data 404 shown as outage | **Fixed** |
| 26 | BFF cookie-only gap on chat | **Fixed** — cookie session resolved on the BFF route |

### #7 is the one that blocks a demo

`apps/web/src/lib/chat/sse-client.ts` calls
`https://api.skyrict.in/ai/agents/chat/stream` **directly from the browser**,
so it is cross-origin from `https://skyrict.in`. The three services do have CORS
middleware, but the request no longer reaches them directly — it goes through
the nginx gateway, and `infra/nginx/gateway.conf.template` currently contains
**no** `Access-Control-*` header and no `OPTIONS` handling at all. `corsOrigins`
is correctly set to `["https://skyrict.in"]` in the beta parameters, so the
allow-list exists; nothing is emitting the headers for it.

This is not cosmetic: the agent chat is the flagship demo surface, and a
preflight failure there fails the whole showcase. It is called out separately
rather than folded into the table because the fix changes the gateway's
request-handling contract, not just a config value.

---

## P0 — Release blockers

### 1. All 3 production Dockerfiles produce images that cannot boot
**Evidence: reproduced on all three.**

`RUN uv sync` executes when only `pyproject.toml` + `README.md` are present —
no `src/`. uv builds project metadata anyway, producing
`identity-0.1.0.dist-info` with **no `.pth` hook**. The source is copied in a
later stage, but nothing tells Python where to find it.

```
ModuleNotFoundError: No module named 'identity'
INFO: Child process [2527] died
INFO: Child process [2528] died
```

The uvicorn **master never exits** — the container sits `Up (unhealthy)`
forever. On ACA that is a silent infinite restart loop: the portal shows the
app as running while it serves nothing.

Second, independent break: **identity and core never copy
`libs/skyrict-events/src`**, yet both import it at runtime
(`identity/events/producers/billing_events.py`,
`tenant_events.py`). ai-agent is the only one that copies its full dep set.

`_template/Dockerfile` has the identical flaw, so every future service
inherits it.

**Fix — already prototyped and verified green:**
1. `uv sync --frozen --no-dev --no-install-project` — third-party deps only, so
   no project metadata is ever built against a missing `src/`.
2. Copy `libs/skyrict-events/src` in identity + core.
3. Write one `.pth` listing the three src roots, so no `PYTHONPATH` is needed.

Verified in a real build: `import identity, skyrict_common, skyrict_events`
passes. Side benefit: the deps layer stops being invalidated on every source
change, so CI rebuilds get faster.

### 2. Worker counts will OOM-kill every replica
**Evidence: measured, not estimated.** Container memory with 1 worker:
identity **129 MiB**, core **172 MiB**, ai-agent **260 MiB**. Marginal cost
per extra worker ~105-235 MiB. The IaC gives every replica **0.25 vCPU /
0.5Gi (512 MiB)**.

| App | workers | projected | limit | verdict |
|---|---|---|---|---|
| identity | 4 | ~445 MiB | 512 MiB | 87% — OOM under load |
| core | 4 | ~625 MiB | 512 MiB | **over budget** |
| ai-agent | 2 | ~495 MiB | 512 MiB | ~97% — effectively certain OOM |

0.25 vCPU also means 4 processes time-sharing a quarter core. ACA
OOM-kills and restarts, so this crash-loops *even after fix #1 lands*.

**Fix:** 1 worker per replica on Consumption (scale horizontally via
`maxReplicas`, not with processes), or raise `containerCpu`/`containerMemory`.
This also cuts the DB connection ceiling from 60 to 30 (see #13).

### 3. No email is ever delivered in production
`IDENTITY_EMAIL_SMTP_HOST`, `CORE_EMAIL_SMTP_HOST` and the `AI_EMAIL_SMTP_*`
set are **never injected by the IaC**. The config documents the consequence
verbatim: *"Empty selects the log-only transport."*

So password resets, email verification, invitations, notifications and
anomaly alerts are written to logs and **silently discarded** — no exception,
no non-200, nothing to alert on. The system looks perfectly healthy.

### 4. Billing is dead in production (503)
`IDENTITY_BILLING_APP_URL`, `IDENTITY_SIGNUP_APP_URL`,
`IDENTITY_BILLING_STRIPE_SECRET_KEY` and
`IDENTITY_BILLING_STRIPE_WEBHOOK_SECRET` are never injected, and these do
**not** auto-derive — `_billing_app_url()` raises `ServiceUnavailableError`:

```python
if not base:
    raise ServiceUnavailableError(
        "Billing is not configured - set BILLING_APP_URL to enable Stripe redirects")
```

Every checkout session, billing portal session and signup-with-payment call
returns **503**. `BILLING_APP_URL` should be
`https://{slug}.skyrict.in` (the code substitutes the slug).

### 5. No AI provider in production
`AI_MODEL`, `AI_BASE_URL`, `AI_API_KEY` are never injected. The service boots
(it is designed to) and every AI call returns a typed **503
`ai_unavailable`**. Chat streaming, NL inventory query, report builder,
finance advisor, anomaly detection and HR copilot are all non-functional.

### 6. The single API host does not exist at all
identity and core are both `external: true` on **separate** ACA FQDNs. There
is no gateway container, no `infra/nginx/gateway.conf`, no gateway Dockerfile,
no `apiHostname` parameter, no `ingress.customDomains`, and no
`managedCertificates` resource. The central requirement is entirely
unimplemented.

Once the gateway is in place, **flip identity and core to `external: false`**
(they stay reachable from the gateway over internal ingress). That leaves
exactly one public entry point and removes two directly-reachable origins —
a real security gain, not just tidiness. ai-agent is already internal.

### 7. CORS will block the browser-direct chat SSE
`allow_origins=settings.CORS_ORIGINS` is an **exact-match list** with no
`allow_origin_regex`, and `corsOrigins` is `["https://skyrict.in"]`. A page
served from `https://{tenant}.skyrict.in` calling
`https://api.skyrict.in/api/v1/ai/agents/chat/stream` is cross-origin and will
be blocked. `allow_credentials=True` rules out `*`, but an anchored regex
(`^https://[a-z0-9-]+\.skyrict\.in$`) is safe and required, since tenant
subdomains are dynamic.

### 8. `jwksIssuer` points at the wrong host
`beta.parameters.json` sets `jwksIssuer: "https://auth.skyrict.in"`, but the
target origin is `https://api.skyrict.in`. The issuer is derived from the
request Host at runtime (confirmed in E2E: `iss=http://default.localhost:3000`).
This must be corrected **before the first real login**, or every issued token
carries the wrong issuer.

---

## P1 — Reliability & correctness

### 9. Readiness probe uses the shallow endpoint
Both Readiness and Liveness point at `/api/v1/health`, which returns
`{"status":"healthy"}` without touching a dependency. `/api/v1/ready` already
exists and correctly reports `{"checks":{"database":"ok","redis":"ok"}}`. As
configured, a replica whose DB pool is exhausted or whose Redis is down stays
in the load balancer and serves 500s instead of being pulled from rotation.
**Fix:** Readiness -> `/api/v1/ready`, Liveness -> `/api/v1/health`.

### 10. `deployManagedRedis=false` + empty override is a silent trap
`redisUrlOverride` defaults to `''`, and `REDIS_URL: str = Field(...)`
**accepted an empty string as valid**. Nothing in the IaC enforces the
documented "Required when deployManagedRedis=false".

**Correction — the originally stated mechanism was wrong.** This finding claimed
the app *boots* and *then* rate limiting fails *open*, "with no startup error to
explain it". Verified against redis-py 5.3.1, the reverse is true on all three
counts:

- `identity.core.redis` builds its client at **module import**
  (`redis_client: Redis = Redis.from_url(settings.REDIS_URL)`, module scope),
  and the startup import chain is `main` → `api.lifespan` → `api.readiness`
  → `core.redis`.
- redis-py raises `ValueError: Redis URL must specify one of the following
  schemes (redis://, rediss://, unix://)` **at construction**, for both the
  sync and `redis.asyncio` clients.
- So `import identity.main` fails outright: the container **crash-loops** behind
  a loud traceback and never serves a request. Rate limiting is never reached.

The impact of an empty URL is therefore **availability, not security** — it
fails *stop*, which is the safe direction. The IaC gap above still needs
closing, and the empty-string acceptance is now rejected by `NonEmptyStr`, but
this was never a silent security downgrade.

**The fail-open that does exist is a different, real issue.**
`RATE_LIMIT_FAIL_CLOSED` defaults to `false` in both identity and ai-agent, and
no `infra/` or `.github/` value overrides it, so production runs fail-open. Once
a client *is* built, a failing Redis command (connection drop, timeout, OOM) is
caught by `is_allowed`, which returns `True` — rate limiting silently lapses for
that request, logged only as `rate_limit_fail_open`. That default is
deliberate (registration and CI must not be blocked by infra), but it is an
**undeclared production posture** and should be an explicit decision rather
than an inherited default.

**Resolution — IaC trap closed, posture decided.** `REDIS_URL` is now
`NonEmptyStr` in identity and ai-agent, so an empty value fails config
validation with a field-named error instead of a cryptic import-time
`ValueError`. `RateLimiter._get_client()` moved *inside* the `try`, so an
unbuildable client now honours `RATE_LIMIT_FAIL_CLOSED` instead of escaping as
an unhandled 500. The CD Preflight step fails the deploy when
`deployManagedRedis=false` and `AZURE_REDIS_URL_OVERRIDE` is empty.

On the fail-open default: **deliberately retained, and now declared.** A Redis
blip must not lock every user out of login mid-demo, and registration/CI must
not be held hostage by infra, so `RATE_LIMIT_FAIL_CLOSED` stays `false`.
Preflight emits a `::warning::` naming the posture on every deploy, so it is a
stated, visible decision rather than an inherited default nobody chose.

### 11. Budget alerts notify nobody, and the threshold is below real cost
`budgetContactEmails: []`, so the 50/80/90% alerts email no one. And
`budgetAmount: 10` is below actual spend: enabling the vnet adds a Standard
Load Balancer plus 2 static public IPs (~$25/mo) on top of compute.

### 12. `minReplicas: 0` blocks managed-certificate validation
ACA needs a running replica to complete (and renew) domain validation. With
scale-to-zero there may be no replica to validate against.

### 13. DB connection ceiling exceeds the SKU
`dbPoolSize=3`, `dbMaxOverflow=0`, `maxReplicas=2`, with the current worker
counts: identity 24 + core 24 + ai-agent 12 = **60** at full scale, against
B1ms `max_connections` = 50. Fix #2 (1 worker) drops this to 30.

### 14. `environmentMaxNodes: 2` caps everything
The ceiling covers 3 service apps, the new gateway, and 4 job apps.

### 15. `concurrentRequests: 100` on 0.25 vCPU
Far too high — requests queue and time out instead of triggering scale-out.

---

## P2 — Polish & debt

### 16. Problem-type URIs use the wrong domain
`PROBLEM_BASE_URL` / `_PROBLEM_BASE` are hardcoded to
`https://api.skyrict.io/problems` in 4 files, while the API is
`api.skyrict.in`. A third domain, `.io`, was never migrated (the earlier pass
handled `.com`). Cosmetic — RFC 7807 `type` is an identifier — but wrong in a
public API contract. 27 occurrences across 11 production files; the rest are
`Field(description=...)` docs and seed fixtures (the `.io` seed emails are
intentional — the E2E workflow uses them too).

**Resolution — fixed, and the duplication removed.** Changing the domain in place
would have fixed the symptom for the third time, so the cause went instead.

The audit's "4 files" understated it. There were **eight** definitions of the
same published base: `PROBLEM_BASE_URL` in each of the four `core/constants.py`
modules, `_PROBLEM_BASE` in each of the four `core/exceptions.py` modules, plus
the web app's own `PROBLEM_BASE` in `(auth)/invite/page.tsx` — a third copy, in a
different language.

The `constants.py` copies were also **entirely dead**. 58 derived `PROBLEM_*`
constants (identity 21, core 12, ai-agent 16, template 9) were declared; 54 had
no reference anywhere outside the file that declared them. `exceptions.py` never
imported them. They were a second, unread copy of a live contract, which is
exactly why the base could drift. The 4 exceptions were ai-agent's
`PROBLEM_AI_*`, imported by its own `exceptions.py` — those are now inline
f-strings like every other entry, so all four services end with none.
`PROBLEM_INVITATION_NOT_FOUND` was worse than dead: it named a problem type that
no exception in identity produces.

What changed:

- `libs/skyrict-common/src/skyrict_common/problems.py` holds the one literal.
  All three services and the template already imported
  `skyrict_common.exceptions`, so the dependency direction needed no change.
- The 58 derived constants are deleted, not re-pointed. A `# NOTE:` at each
  former location records why, so the next service does not reintroduce them.
- `_template` no longer hardcodes 14 full URIs inline; it uses the same
  `_PROBLEM_BASE` pattern as the three real services, so new services inherit
  the right shape.
- The web app stopped duplicating the contract at all.
  `classifyInviteProblem()` in `src/lib/invitation-problem-types.ts` matches the
  trailing slug, so the page is independent of which host publishes it. This
  matches the convention the repo already used — `test_concurrency_atomicity.py`
  has asserted `type.endsWith("/duplicate-record")` all along; the invite page
  was the outlier. It is a separate `.ts` module because vitest runs on
  `src` test files in a node environment and cannot import a `.tsx` page (same
  reason as `risk-gate.ts`).
- `*_JWKS_AUDIENCE` examples, the four `config.py` field descriptions, five
  `.env.example` files, `README.md` and two nightly workflows moved to `.in`.
  Those descriptions are how `.io` kept getting copy-pasted in the first place.

**Test structure.** The ~20 service assertions now build expectations from
`PROBLEM_BASE_URL` — they test the *status/slug mapping*, which is what they
were always actually testing. The *domain* is pinned once, in
`libs/skyrict-common/tests/test_problems.py`, which also asserts the value
matches no retired TLD. That is the assertion that was missing, and its absence
is why three domain migrations went unnoticed.

Mutation-verified: hardcoding a retired domain back into identity fails 42 of
its exception tests; regressing the shared base fails the lib's pin *and* the
retired-TLD guard; and making the web policy exact-match one host again fails the
domain-independence test.

**One left deliberately:** `docs/incidents/2026-08-…md:88` still quotes
`api.skyrict.io`. It is a dated postmortem of what the API returned at the
time; rewriting a historical record to match today's deployment is worse than a
stale line in it. Tracked under #21.

### 17. 20 further config vars default-empty and are never injected
Grouped by consequence:
- **S3** (`IDENTITY_AVATAR_S3_BUCKET`, `CORE_DOCS_*`, `AI_ATTACHMENT_*`) ->
  avatar, document and attachment upload are disabled.
- **`IDENTITY_TURNSTILE_SITE_KEY` / `_SECRET_KEY`** -> no CAPTCHA on signup.
- **`*_SENTRY_DSN` (all 3)** -> **no error tracking at all in production.**
- **`AI_ANOMALY_NOTIFY_EMAILS`** -> nobody receives anomaly alerts.
- **`IDENTITY_SECURITY_CONSOLE_BASE_URL`, `IDENTITY_EMAIL_VERIFICATION_BASE_URL`,
  `AI_ANOMALY_REVIEW_BASE_URL`** -> those emails go out with no action link.

### 18. The AI E2E project is broken — 3 of its 11 tests fail
**Evidence: `--project=ai` run for the first time. 8 passed, 3 failed** (every
attempt, including both retries — not flakes).

**a) `fallback-degradation.spec.ts:51` and `:63` contradict the UI.**
Both fail on `expectAnsweringAgent(page, "Supervisor")`:

```
Expected substring: "Supervisor"
Received string: "Hey! I'm the Skyrict assistant. I can help with Inventory
Monitor, HR Copilot, CRM Assistant, ... what would you like to know?"
```

`chat-message-list.tsx:365-371` **deliberately suppresses** the module label
when the answering agent is the supervisor:

```tsx
{message.agentName && !isUser &&
 message.agentName.toLowerCase() !== "supervisor" ? (<p ...>{message.agentName}</p>) : null}
```

So the component's intent is "no label for the supervisor"; the spec asserts
the label is present. `"Supervisor"` appears **nowhere** in `apps/web/src`, so
this is spec-vs-implementation drift, not a product regression. The spec needs
a different assertion for the supervisor case (e.g. that no module label is
rendered, or a `data-agent` attribute), and the product decision — should a
supervisor answer be labelled? — should be made explicitly rather than settled
by whichever code shipped last.

**b) `approval-interrupt.spec.ts:61` expects a button the UI gates off.**
```
element(s) not found - waiting for getByRole('button', { name: 'Post' })
```

`journal-entry-detail.tsx:175` renders the button only when
`canPost = entry.status === "draft" && canApprove`. The spec's own comment
says *"the engine took over instead of posting; the Post action is still offered
because the entry is still a draft"* — but taking over posting is precisely
what moves the entry out of `draft`, which is what removes the button. Either
the interrupt is meant to leave the entry draftable (in which case the gating
is wrong), or the spec's expectation is wrong. **This one needs a product
decision, not just a test edit** — it is the only one of the three that could
be a genuine behavioural gap.

**Fix:** decide (a) and (b) deliberately, repair the specs, then add
`--project=ai` to the CI main phase so the next drift is caught.

### 19. Ten E2E spec files are orphaned and never execute
**Evidence: `playwright test --list` reports "29 tests in 18 files" while the
repo contains 27 spec files.** Ten are matched by **no** project's
`testMatch`, so they are silently skipped in every CI phase (the workflow runs
`--project=setup --project=reports-smoke --project=crm-finance --project=perf`
and then `--project=security`; nothing else is ever selected, and the `ai`
project is never invoked at all):

| Orphaned spec | Area |
|---|---|
| `auth/rbac.spec.ts` | role-based access control |
| `auth/signin.spec.ts` | sign-in |
| `auth/mfa.spec.ts` | MFA enrolment / challenge |
| `auth/invite.spec.ts` | invitation acceptance |
| `auth/signup-captcha.spec.ts` | signup CAPTCHA |
| `isolation.spec.ts` | **tenant isolation** |
| `billing.spec.ts` | **billing / checkout** |
| `inventory.spec.ts` | inventory |
| `hr-leave.spec.ts` | HR leave |
| `payroll.spec.ts` | payroll |

Two compounding gaps:
- **`--project=ai` is never run in CI.** The whole SKY-107 AI surface (chat
  streaming, NL inventory, report builder, finance advisor, approval
  interrupts, fallback degradation) has an E2E project and a wired
  `AI_PROVIDER=mock` stack, but the workflow never selects it.
- The orphaned set overlaps almost exactly with the defects found in this
  audit — CAPTCHA, billing and tenant isolation are all broken *and* untested.
  Those suites would very likely have caught #4 and #7.

**Fix:** add a project (or broaden `testMatch`) that owns these files, and add
`--project=ai` to the CI main phase. Then run them once locally to see what
they actually report.

**First-ever run, via an audit-only config that owns the 10 files: 6 failed, 6
passed.** So half of the never-executed suite is already red:

| Spec | Result | Root cause |
|---|---|---|
| `auth/signin.spec.ts` (x2) | pass | — |
| `auth/invite.spec.ts` | pass | — |
| `inventory.spec.ts` | pass | — |
| `hr-leave.spec.ts` | pass | — |
| `auth/mfa.spec.ts` | **fail** | #23 — signup captcha checkbox never renders |
| `auth/signup-captcha.spec.ts` | **fail** | #23 (same line) |
| `billing.spec.ts` | **fail** | #23 (same line) |
| `isolation.spec.ts` | **fail** | #23 (same line) |
| `auth/rbac.spec.ts` | **fail** | test bug — `getByRole('heading', {name:'Business Operations'})` matches **2** elements (banner `h1` + main `h1`), strict-mode violation |
| `payroll.spec.ts` | **fail** | #24 — passes in isolation (17s), fails in a batch |

`auth/rbac.spec.ts` is purely a spec defect and needs only a scoped locator
(`getByRole('main').getByRole('heading', ...)`). Note what it was *meant* to
prove — that a finance viewer is denied payroll — and that this assertion never
ran in CI.

### 20. The E2E auth harness breaks on a stale TOTP secret
**Reproduced during this audit.** The harness reads the admin's TOTP secret from
the gitignored `e2e/.auth/totp-secret`. If the database has MFA enrolled but
that file is absent or left over from an earlier enrollment, `auth.setup.ts:91`
takes the *challenge* path, submits codes derived from the wrong secret, and
fails with the far-from-obvious:

```
MFA handoff did not reach the workspace.
Final URL: http://default.signin.localhost:3000/signin
```

The guard at `auth.setup.ts:93` only checks that the secret is *truthy* — it
cannot detect that the secret is *wrong*. Every downstream spec then reports
"did not run", which reads like an application failure rather than harness
state drift. In CI the database is wiped between phases so this stays hidden;
locally, `docker compose up` over existing volumes plus a fresh checkout
reproduces it immediately.

**Fix:** verify the persisted secret against the server before the challenge
round and self-heal (e.g. drive the owner `POST /api/v1/mfa/reset` then fall
back to enrollment), or fail with a message naming the stale-secret cause.
Whichever is chosen, any API-level test that enrolls MFA must restore the
account to un-enrolled state.

### 21. Documentation is stale
- `docs/runbooks/azure-iac.md` §11 and `docs/architecture/adr/0010-azure-hosting.md`
  both state "No custom domains/TLS yet" — false once #6 lands.
- `azure-iac.md` cost table omits the load balancer and public IPs, making the
  "$0/month" definition-of-done untrue.
- `docs/architecture/auth-production-model.md` still says `skyrict.com`.
- `docs/runbooks/staging-deployment.md` and ADR-003 describe cert-manager +
  Route 53 + k8s, which the ACA design replaced.

### 22. `_template/Dockerfile` propagates P0 #1
Any new service scaffolds with the same broken pattern.

### 23. **P0 — Signup is completely blocked in production, while the UI says "Verified"**

Found by running the 10 orphaned specs for the first time. Five of the six
failures die on the same line, `onboarding.ts:93`, waiting for the signup
"I\'m not a robot" checkbox that never appears. The chain:

**The client captcha is theatre.** `apps/web/src/lib/api/auth-api.ts:236-247`
never calls a server at all:

```ts
export async function assessRisk(): Promise<RiskAssessment> {
    return { requiresCaptcha: true, requiresChallenge: false, signals: [] };
}
export async function solveCaptcha(): Promise<{ status: "ok" }> {
    return { status: "ok" };
}
```

There is no risk-assessment endpoint anywhere in `services/identity` — grepping
for `requires_captcha` / `assess_risk` returns nothing. So the "Skyrict Shield"
panel always shows, and checking the box always "verifies", with a server call
never made. `risk-challenge.tsx:169-174` then paints the `AiGlyph` and flips the
footer to "Verified".

**The backend then fails closed.** `identity/core/turnstile.py:23-27`:

```python
async def verify(self, token: str | None) -> bool:
    if not self._secret_key:
        return settings.ENVIRONMENT in (Environment.DEV, Environment.TEST)
    if not token:
        return False
```

`auth/service.py:376-378` turns that into
`ValidationError("Unable to verify you are not a robot. Try again.")`.

So the production outcomes are:

| `TURNSTILE_SECRET_KEY` | `NEXT_PUBLIC_TURNSTILE_SITE_KEY` | Result |
|---|---|---|
| unset | unset | backend returns `False` -> **every signup 422s** |
| unset | set | client sends a token, backend ignores it -> **every signup 422s** |
| set | unset | client sends no token -> `if not token: return False` -> **every signup 422s** |
| set | set | works |

Three of four combinations brick signup, and `beta.parameters.json` currently
sets **neither** — this is a hard launch blocker, not a nice-to-have. Good news:
it fails *closed*, so there is no silent bot-protection hole. The real defects
are (a) it is unconfigured, and (b) the client lies to the user by showing
"Verified" for a check that verifies nothing.

**Fix:** supply both keys before launch; then either delete the two stub
functions and have `RiskChallenge` ask the server, or make `solveCaptcha`
actually call a real endpoint. The current middle state — a fake client
verification paired with a strict server gate — cannot be made safe by
configuration alone.

**Why the checkbox never rendered locally:** `apps/web/.env.local` (gitignored,
so **CI never sees it**) sets Cloudflare's always-pass test key
`NEXT_PUBLIC_TURNSTILE_SITE_KEY=1x00000000000000000000AA`. Because
`NEXT_PUBLIC_*` is inlined at build time, `risk-challenge.tsx:32`
`Boolean(env.turnstileSiteKey)` is true, so the component takes the Turnstile
branch and renders a full-viewport overlay instead of the checkbox the harness
expects. This is a local-only trap, not a CI failure — but it is why 5 specs
failed locally while the harness comment at `onboarding.ts:90-92` still reads
"Without a Turnstile site key (ENVIRONMENT=test) the risk challenge is a plain
checkbox".

### 24. P1 — The E2E harness degrades as admin sign-ins accumulate in one process

`payroll.spec.ts` failed in the orphan batch with

```
BFF session probe to /api/v1/users/me did not authenticate:
HTTP 401 {"detail":"Missing Authorization header"}
```

`assertSessionReachesBff` (`auth-flow.ts:451`) fetches `/api/v1/users/me`
through the BFF with cookies only; "Missing Authorization header" is the
*identity* service complaining that the **BFF** sent it no token, so the BFF
resolved no access token from the session cookie.

Re-run alone on the same stack: **2 passed in 17.0s.** So this is not a product
bug — it is state accumulating across specs. It is the same class of hazard the
harness already documents in its own docstrings ("closing the page mid-flight
aborts the Set-Cookie response while the backend has already advanced the hash —
the next context then presents a stale token"), where refresh-token rotation and
reuse detection bite. Every spec that signs in as the *same* seeded admin from a
fresh context runs the same rotation chain.

CI never sees it because the curated main phase is only 6 tests. The moment
`--project=ai` and the orphans are wired in, this will start failing
intermittently and be misread as a product regression. Same fix family as #20:
give the harness a per-worker (or per-spec) admin identity instead of sharing
one token family, and make the fixture report the rotation state when it fails.

### 25. P2 — A "not enough data yet" 404 is reported to users as "AI service is down"

Found by the manual pass: `GET /api/v1/ai/l3/payroll_cost` returns
**503 `AiUnavailableError` "Core service is temporarily unavailable"**.

The actual cause is a perfectly normal business condition. Probing core's
endpoint directly with the same token:

```
core /api/v1/ai/hr/l3/payroll-cost
  -> 404 {"detail": "Insufficient payroll history for cost movement
                  (need 2+ completed runs)"}
```

`ai_agent/features/l3/gateway.py:56-59` treats any non-2xx as a transport
failure:

```python
response.raise_for_status()
except httpx.HTTPError as exc:
    logger.warning("l3_gateway_unreachable", path="/ai/hr/l3/payroll-cost")
    raise AiUnavailableError("Core service is temporarily unavailable") from exc
```

So a legitimate "this tenant has not run payroll twice yet" is laundered into
"the AI service is temporarily unavailable" — which tells the operator to go
look at an outage that does not exist, and tells the user nothing actionable.
The other two L3 kinds on the same gateway (`leave-pay-correlation`,
`compliance`) return 200, so this is specific to the one endpoint whose data
requirement is unmet.

**Fix:** in the gateway, treat 404 (and 422) from core as "insufficient source
data" and return an abstained narrative with the real reason, as the other two
kinds already do. Only 5xx/connection failures should become
`AiUnavailableError`. Worth a regression test with a fake gateway returning
404.

Note: this was the **only** 5xx produced anywhere in the entire sweep, so once
it is fixed the stack is 5xx-clean end to end.

### 26. P2 — The BFF's documented cookie-only fallback has a hole on the chat stream path

`apps/web/src/app/api/v1/[...path]/route.ts:20-24` documents that a raw
same-origin fetch carrying only the httpOnly session cookie authenticates,
because the BFF mints an access token server-side. Isolated behaviour:

| Request | Result |
|---|---|
| `GET /api/v1/users/me`, cookie only | **200** |
| `POST /api/v1/crm/customers`, cookie only | **422** (auth passed) |
| `POST /api/v1/documents`, cookie only | **422** (auth passed) |
| `POST /api/v1/ai/agents/chat/stream`, cookie only | **401** |
| `POST /api/v1/ai/agents/chat/stream`, explicit bearer | **200 + real SSE frames** |

So the fallback is not broken for unsafe methods in general — it is broken on
this one route. `nginx` logged the 401 and **no backend logged any request at
all**, so the 401 is produced by the BFF itself, not relayed from identity,
core or ai-agent. I could not pin the exact internal branch from the outside;
the observable contract above is what is proven.

**Impact is low in the product** because `fetchWithSession`
(`lib/api/http.ts`) always attaches a bearer from the in-memory session store,
which is why all 8 passing AI specs work. But two things make it worth fixing:

1. The harness's own gate `assertSessionReachesBff` (`auth-flow.ts:451`) is
   **cookie-only by design** — so this is a live candidate for the 401s in #24.
2. A documented contract that silently does not hold is the kind of thing that
   breaks later, silently, when someone adds a cookie-only call to this path.

**Fix:** make the cookie-mint path behave identically on every route, and add a
test that walks the cookie-only path across a representative sample of GET,
POST and streaming routes rather than asserting it once on `/users/me`.

**Resolution — fixed.** The probe found one route; the defect was on three.
Re-reading all five BFF handlers showed the token-resolution block had been
copy-pasted into each one, and **three** had dropped the cookie fallback:

| Route | Before | After |
|---|---|---|
| `/api/v1/[...path]` (catch-all) | had the fallback | unchanged |
| `/api/v1/reports/[...path]` | had the fallback | unchanged |
| `/api/v1/ai/agents/chat/stream` | `token: null` | fixed |
| `/api/v1/finance/ai/docs/[docId]/download` | `token: null` | fixed |
| `/api/v1/agents/conversations/[id]/attachments/[attachmentId]` | `token: null` | fixed |

Patching one instance would have left two. The fix removes the duplication
class instead:

- New `apps/web/src/lib/server/bff-auth.ts` owns the policy as
  `resolveBffAuth(request)`. All five routes call it.
- It is deliberately **not** in `auth.ts`. `resolveBffAuth` has to reach
  `sessionAccessToken` across a module boundary, because vitest cannot intercept
  a same-module function reference — had it stayed in `auth.ts`, the only way to
  test it would have been to re-implement it as a mock mirror inside each route
  test, i.e. the same duplication that caused the bug. A useful side effect: the
  two pre-existing route test suites needed **zero** changes.
- The three streaming relays now return `NextResponse` instead of a bare
  `Response`, so the rotated refresh cookie is written back on the same
  responses that mint a token. Without the write-back a cookie-only session
  works exactly once.
- `bff-auth-parity.test.ts` drives all six route shapes (JSON GET, JSON POST,
  CSV relay, SSE, two binary relays) through the same four assertions.
  `bff-auth.test.ts` pins the policy's header parsing.

Both layers are mutation-verified: removing the fallback from the SSE relay
alone fails 3 parity rows, and removing the policy's empty-token guard fails its
unit test. The empty-token guard is subtle and is documented as load-bearing —
`Headers` strips trailing ASCII whitespace, so a bare `Bearer ` is rejected by
the scheme check, but `Bearer<U+00A0>` survives that stripping and is removed by
`trim()`, so the guard is the only thing handling it.

---

## What is left, in order

1. **P0 #7** - CORS on the gateway. Blocks the agent chat demo end to end.
2. **P0 #23** - real Turnstile site + secret keys. Structurally wired, but the
   Preflight hard-fails without them, so this gates the first deploy.
3. **P0 #3, #4, #5, #17** - inject the missing env vars. Needs real SMTP,
   Stripe and AI provider credentials.
4. **P1 #18, #19, #20, #24** - un-orphan the 10 dead E2E specs, wire
   `--project=ai` into CI, detect a stale TOTP secret, and give specs
   independent admin identities. Worth doing early: it is the mechanism that
   would have caught #4 and #7.
5. **P1 #13, #14, #15** - pool math, node cap, backend scale rule.
6. **P2 #21** - the remaining stale runbooks and ADRs.

Findings #1, #2, #6, #8, #9, #10, #11, #12, #16, #22, #25 and #26 are closed and
covered by the fix series; #23 is closed in structure and waiting only on
credentials.

## Blocked on you

- `az` CLI is not installed - `az login` is a device-code flow only you can
  complete. Once logged in the token persists and I can drive every Azure step.
  `scripts/azure/bootstrap-azure.ps1` has therefore never run, so **no Azure
  resources exist yet**: no resource group, service principal, ACR, Log
  Analytics workspace or Container Apps environment.
- The repository has **zero GitHub secrets** (`gh secret list` returns `[]`) and
  **no `azure-beta` environment** (only `Preview` and `Production` exist),
  although both deploy jobs declare `environment: azure-beta`. Both must be in
  place before the workflow will run.
- SMTP relay, Stripe keys, AI provider key + model, Sentry DSN, S3 buckets,
  Turnstile site + secret keys - all need real values.
- `AZURE_BUDGET_CONTACT_EMAILS` - the budget is skipped without it and the
  Preflight warns. Non-blocking, but until it is set nothing alerts before the
  free-trial allotment is spent.
- GoDaddy DNS records and Vercel production env vars.

## Deploy-day ordering note

The `api.skyrict.in` name does not answer until the GoDaddy CNAME exists and
ACA has issued the managed certificate, so the workflow deliberately smoke-tests
the gateway's generated FQDN rather than the custom domain. The custom domain is
proven afterwards, per `docs/runbooks/azure-iac.md` section 11.