# Runbook: Azure beta deployment (SKY-114)

The Skyrict **beta** environment runs on Azure Container Apps (Consumption
profile, scale-to-zero) with Flexible Postgres, conditional Azure Cache for
Redis, ACR, Key Vault, and Log Analytics — all provisioned with Bicep in
`infra/azure/` and rolled out by `.github/workflows/cd-azure-beta.yml`.

Acceptance criteria (DoD for SKY-114):

1. `bicep validate` and `bicep what-if` are clean (no unexpected changes).
2. Applying the same parameters twice is a **no-op** (idempotency gate in CD).
3. Secrets exist only in Key Vault and the ACA secret store — never in the
   repo, Bicep, CI logs, or app env.
4. Apps scale to zero (`minReplicas: 0`) and only scale on HTTP concurrency.
5. Log Analytics retention is capped (30 days).
6. Steady-state cost is **$0/month** on the Azure free account (see
   `azure-cost-estimate.md`).

---

## 1. Topology

| Resource        | Name                              | Notes                                              |
| --------------- | --------------------------------- | -------------------------------------------------- |
| Resource group  | `skyrict-beta`                    | All resources live here                            |
| VNet            | `vnet-skyrict-beta`               | 10.16.0.0/16, three subnets (infra / postgres / pe)|
| CAE             | `cae-skyrict-beta`                | Consumption, vnet-integrated, scale-to-zero        |
| Log Analytics   | `log-skyrict-beta`                | 30-day retention                                   |
| Key Vault       | `kv-skyrict-beta`                 | RBAC, soft delete + purge protection               |
| UAMI            | `id-skyrict-beta`                 | ACR pull + KV secret references                    |
| ACR             | `skyrictbeta.azurecr.io`          | Standard SKU, admin **disabled**                   |
| Postgres        | `pg-skyrict-beta`                 | B1ms / PG16 / 32 GB, private + `vector`,`pg_trgm`  |
| Redis            | Upstash Serverless (external)     | `rediss://` via `AZURE_REDIS_URL_OVERRIDE`, free tier  |
| App identity    | `app-identity-skyrict-beta`       | External ingress :8000                             |
| App core        | `app-core-skyrict-beta`           | External ingress :8001                             |
| App ai-agent    | `app-ai-agent-skyrict-beta`       | **Internal-only** ingress :8000                    |
| Job db-init     | `job-db-init-skyrict-beta`        | Creates DB + extensions, `postgres:16-alpine`      |
| Jobs migration  | `job-{identity,core,ai-agent}-skyrict-beta` | Alembic `upgrade head` per service      |

Internal calls use the CAE short-name URLs (`http://app-core-skyrict-beta`,
`http://app-ai-agent-skyrict-beta`) which resolve inside the environment and
avoid Bicep cycles.

Externally, identity and core resolve as
`https://app-identity-skyrict-beta.<env>.<region>.azurecontainerapps.io` /
`.../app-core-...` — the FQDNs are printed as deployment outputs. The region
segment is whatever `beta.parameters.json` sets; it is `westus`, not
`eastus` (see section 11).

## 2. Two-phase rollout

The apps reference Key Vault secrets (`jwt-public-key`, `sync-token`, …) that
must **exist** before their revisions are created. CD therefore enforces:

1. **Phase 1** — `deployWorkloads=false`: environment, security, registry,
   data, budgets. Grants AcrPush to the deploy principal, then CD sets
   `azure.extensions=vector,pg_trgm` and seeds the KV secrets.
2. **Phase 2** — `deployWorkloads=true` + `imageTag`: the 3 apps and 4 jobs,
   pinned to the immutable git-SHA image tag; then CD applies the same
   parameters a second time and asserts **zero real changes** (idempotency).
3. **Migrations** — CD runs `db-init` → identity → core → ai-agent jobs in
   dependency order (identity owns `tenants`/`current_tenant_id()`).

## 3. Prerequisites

- Azure free trial subscription (12-month free allotments).
- `az` CLI (logged in once, or the OIDC identity handles CI).
- `gh` CLI (authenticated to `nkswalih/skyrict`).
- Bicep CLI **v0.47.16** (pinned). CI installs it via
  `Azure/bicep-setup-action`; locally, keep the binary at
  `.dev/tools/bicep.exe` (gitignored).
- GitHub Actions OIDC must be enabled for the repo
  (Settings → Actions → General → Workload permissions → **Allow GitHub
  Actions to create and approve pull requests** is not required; the
  **OIDC** federated credential is created by the bootstrap script).

## 4. Bootstrap (one-time)

```powershell
./scripts/azure/bootstrap-azure.ps1
```

This is idempotent for identity/RBAC and:

1. Creates the resource group (if missing).
2. Creates/reuses the Azure AD app registration + service principal and the
   GitHub Actions OIDC federated credential for the `azure-beta` environment.
3. Assigns RBAC to the CD principal: RG **Contributor**, RG **Key Vault
   Administrator** (covers the vault once Bicep creates it), subscription
   **Contributor** (nested subscription-scoped `Microsoft.Consumption/budgets`
   deployments require `deployments/write` at subscription scope).
4. Generates operational secrets and writes them as **`azure-beta`**
   environment secrets (see table below). Values are never printed.
5. Sets `CD_AZURE_BETA_ENABLED=true` as a **repository** variable so pushes to
   `dev` trigger the rollout, and seeds Key Vault directly if it already
   exists. Repository scope, not the environment: the gate is a job-level
   `if`, evaluated before the job enters its environment, so it can only see
   repository and organisation variables. See §5.1 and §8.

> **Re-running the script rotates all secrets.** Running services keep the
> old KV values until the next phase-2 apply, so rotate during a change
> window and re-deploy.

### 4.1 GitHub environment secrets (created by bootstrap)

| Secret | Purpose | Format |
| --- | --- | --- |
| `AZURE_CLIENT_ID` / `AZURE_TENANT_ID` / `AZURE_SUBSCRIPTION_ID` | OIDC login | Azure AD |
| `AZURE_DEPLOY_PRINCIPAL_ID` | Principal granted AcrPush (Bicep) | object id |
| `AZURE_POSTGRES_ADMIN_PASSWORD` | Flexible Server admin password | URL-safe alnum (no `@ ? # &`) |
| `AZURE_JWT_PRIVATE_KEY` / `AZURE_JWT_PUBLIC_KEY` | JWT RS256 keypair | RSA-2048 PKCS#8 / SPKI PEM |
| `AZURE_MFA_ENCRYPTION_KEY` | TOTP-at-rest encryption | Fernet key (`Fernet.generate_key()`) |
| `AZURE_SYNC_TOKEN` | Shared sync token (core ↔ ai-agent) | URL-safe token |
| `AZURE_INGEST_TOKEN` | Shared ingest token (core → ai-agent) | URL-safe token |
| `AZURE_REDIS_URL_OVERRIDE` | Upstash `rediss://` URL — **required**, not optional | `rediss://…:6379`. Must be `rediss://`: with `deployManagedRedis=false` this is the only Redis, and an empty value hands the apps `REDIS_URL=''`, which crash-loops them at startup |

### 4.2 Key Vault secrets (seeded by CD / bootstrap)

| Secret | Consumed by | Maps to |
| --- | --- | --- |
| `jwt-private-key` | identity (signing) | `JWT_PRIVATE_KEY_PATH` secret volume |
| `jwt-public-key` | identity/core/ai-agent (verify) | `JWT_PUBLIC_KEY_PATH` secret volume |
| `mfa-encryption-key` | identity | `MFA_ENCRYPTION_KEY` |
| `sync-token` | core + ai-agent | `CORE_AI_SYNC_TOKEN` = `AI_INVENTORY_SYNC_TOKEN` + `AI_DOCUMENT_SYNC_TOKEN` |
| `ingest-token` | core + ai-agent | `CORE_AI_INGEST_TOKEN` = `AI_INGEST_TOKEN` |

Postgres/Redis credentials are **computed at deploy time** from
`postgresPassword` and Redis `listKeys()` — they never enter Key Vault or the
repo.

## 5. Deploying

### 5.1 Via CD (required for migrations + verification)

```bash
git switch dev && git pull --ff-only origin dev
# push touches services/** libs/** infra/azure/** -> cd-azure-beta.yml
git push origin dev
```

The workflow runs `provision-infra` → `build-push-images` →
`deploy-workloads` → `migrate` → `verify` and is gated by
`CD_AZURE_BETA_ENABLED` (repository variable, see §3 step 5). Watch the run;
the final `verify` job curls the gateway's generated FQDN for health and
`/readyz`, asserts a 401 from a core route to prove the gateway routes to
it, and checks the identity/core/ai-agent revision states.

> **A run that reports `completed / skipped` in ~2s is not "nothing to
> deploy" — it is the gate evaluating false.** That is the signature of
> `CD_AZURE_BETA_ENABLED` being unset at repository scope, which is the only
> scope the job-level `if` can read. Check with `gh variable list` (no
> `--env`) before assuming there is nothing to do.

### 5.2 Manual/debug deploy (no migrations, apps only)

```powershell
$params = @(
  "infra/azure/parameters/beta.parameters.json",
  "deployWorkloads=false",
  "deployPrincipalId=$env:AZURE_DEPLOY_PRINCIPAL_ID",
  "postgresPassword=`"$env:AZURE_POSTGRES_ADMIN_PASSWORD`"",
  "redisUrlOverride=`"$env:AZURE_REDIS_URL_OVERRIDE`""
)
az deployment group validate    -g skyrict-beta -f infra/azure/main.bicep -p $params
az deployment group what-if     -g skyrict-beta -f infra/azure/main.bicep -p $params
az deployment group create      -g skyrict-beta -f infra/azure/main.bicep -p $params
```

Then repeat with `deployWorkloads=true` after KV secrets exist and run the
jobs manually per section 7.

## 6. Operational notes

- **Logs**: per-app diagnostic settings (console + system + all metrics) go
  to `log-skyrict-beta`. Job logs are fetched with
  `az containerapp job execution logs show`.
- **Scale**: apps run `minReplicas: 0`, scale out at 100 concurrent requests
  to `maxReplicas: 2`. That per-app cap is the only node cap: the Consumption
  workload profile accepts neither `minimumCount` nor `maximumCount`, so
  `Microsoft.App/managedEnvironments` rejects the deployment with
  `WorkloadProfilePropertyNotSupported` if either is set.
- **Budgets**: subscription budgets alert at 50/80/90% of `$10` (CD passes
  the first-of-month as `budgetStartDate` so re-applies stay idempotent).
- **Cost**: see `azure-cost-estimate.md`.

## 7. Jobs (db-init + migrations)

Run through the job CLI (CD does this automatically):

```bash
exec=$(az containerapp job start -n job-db-init-skyrict-beta -g skyrict-beta --query name -o tsv)
az containerapp job execution show -g skyrict-beta --job-name job-db-init-skyrict-beta --execution-name "$exec" \
  --query properties.status -o tsv   # wait for Succeeded
```

Order is **always** `db-init` → identity → core → ai-agent. db-init
creates `skyrict_identity` and enables `vector` + `pg_trgm` idempotently;
each migration job runs `alembic upgrade head` with an explicit
`-c /app/services/<svc>/alembic.ini` config so each service writes to its
own version table (`alembic_version` / `alembic_version_core` /
`alembic_version_ai`).

## 8. Rollback

Because every deploy is a tagged immutable image and an idempotent apply,
rollback = re-deploy the previous SHA with the same pipeline:

1. Find the previous green run's SHA: `git log --oneline -5 dev`.
2. Re-run the CD manually from that SHA (or `workflow_dispatch` after a
   revert), keeping `deployWorkloads=true`.

For an **infrastructure** rollback:

1. `az deployment group what-if` with the target commit's parameters.
2. If the what-if matches the target state and is clean, apply it — Bicep
   diffs declaratively against the live resource group, so a previous state
   can be restored by re-applying its template snapshot.
3. Migration rollbacks are Alembic downgrades run through the same job
   pattern (`alembic downgrade -1`); do **not** hand-edit schema.

If a release is actively breaking: set `CD_AZURE_BETA_ENABLED=false` on the
**repository** — `gh variable set CD_AZURE_BETA_ENABLED --body false`, with
no `--env`. That blocks new push-deploys. Setting it on the `azure-beta`
environment instead does nothing at all: the gate is a job-level `if` and
cannot read environment variables. Investigate from logs, then re-enable with
the same command and `--body true`.

Note that a `workflow_dispatch` run is **not** gated by this flag — the
condition is `github.event_name == 'workflow_dispatch' || <flag>`, so a
manual dispatch always proceeds regardless. It is a switch against
*accidental* deploys, not a kill switch.

## 9. Destroy

```powershell
az deployment group create -g skyrict-beta -f infra/azure/main.bicep -p infra/azure/parameters/beta.parameters.json -p deployWorkloads=false -p postgresPassword="$env:AZURE_POSTGRES_ADMIN_PASSWORD" --mode Complete
az group delete -n skyrict-beta --yes --no-wait
# subscription-scoped budgets are not in the RG - delete by name
$sub = az account show --query id -o tsv
az consumption budget delete --budget-name "skyrict-beta-budget-50pct" --subscription $sub
az consumption budget delete --budget-name "skyrict-beta-budget-80pct" --subscription $sub
az consumption budget delete --budget-name "skyrict-beta-budget-90pct" --subscription $sub
```

> Complete-mode removes everything in Bicep from the RG, then the RG delete
> removes the rest. The vault is purge-protected for 90 days after deletion
> (by design). The OIDC app registration / environment secrets are removed
> separately (`az ad app delete`, then delete the `azure-beta` environment).

## 10. Month-2 → $0/month transition (after the trial month)

Skyrict-114 is designed so the **steady state after month 1 is $0/month**
within the Azure free account's 12-month + always-free allotments:

1. **Upgrade to PAYG** within 30 days of signing up so the free tier
   continues into months 2–12.
2. **Redis is Upstash Serverless, and that is no longer optional** (free
   tier, no Azure spend):
   - Azure has **retired Azure Cache for Redis**, so this swap moved from
     month 2 to day 1. Verified on this subscription: creating
     `Microsoft.Cache/redis` returns *"Azure Cache for Redis is retiring"*,
     and the `Standard_C0` SKU the template used is now rejected as an
     invalid SKU name. The successor `Microsoft.Cache/managedRedis` is not
     available here either - `InvalidResourceType`. Neither is recoverable
     with credits, so `deployManagedRedis=true` can no longer deploy.
   - Set GitHub secret `AZURE_REDIS_URL_OVERRIDE` to the Upstash
     `rediss://<user>:<pass>@<host>:6379` URL. It must be the `rediss://`
     (TLS) form: Upstash rejects a plaintext `redis://` connection.
   - `beta.parameters.json` ships `deployManagedRedis=false`, so the `data`
     module skips Redis and `apps.bicep` computes the connection URL from
     the override. No application code change, TLS throughout.
   - Enabling eviction on the Upstash database is required. Without it a full
     database rejects writes instead of evicting, and identity and ai-agent
     both hard-depend on this cache.
3. **Scale ACR to Basic** (`registrySku=Basic`) — the free account covers
   one Standard ACR for 12 months; Basic keeps the same auth model cheaper
   later.
4. **Keep Postgres B1ms** (always-free 32 GB / 750 compute hours) and the
   Consumption profile at `minReplicas: 0` — identity and core may sit at
   zero replicas between requests; workflow/approval spikes scale up then
   back down.
5. **Budgets stay live** — 50/80/90% of a low amount are the tripwire if
   anything escapes the free allotments.

## 11. Beta limitations (documented)

- **The Key Vault is `kv-skyrict-beta-2`, and `kv-skyrict-beta` is
  permanently unusable.** `kv-skyrict-beta` was deleted and is now
  soft-deleted *with purge protection enabled*, so Azure refuses to purge it
  and the name can never be reused. `keyVaultName` in `beta.parameters.json`
  therefore sets the new name. If this beta is ever torn down and recreated,
  check whether purge protection is on before deleting: a purged-name is
  unrecoverable, and the fix is another rename.

- **The region is `westus`, and it is not a free choice.** This subscription
  cannot create a PostgreSQL Flexible Server in `eastus` at all: every SKU
  (B1ms, B1s, B2ms, D2s_v3), every major version (11-17) and every supported
  API version is rejected with `ParameterOutOfRange: The value of the 'Version'
  should be in: []` - an empty list, because the service resolves no version
  for that region on this account. `westus`, `centralus`, `northeurope`,
  `southeastasia` and `japaneast` were all confirmed to reach `Ready` with the
  identical B1ms/v16 configuration. `westeurope` fails separately, with
  `RequestDisallowedByAzure` (region not accepting new customers). Do not
  "restore" `eastus` without re-running that check first.
- `ai-agent` is internal-only: no public FQDN; verified via revision state.
- **The idempotency gate tolerates `Modify` on five resource types, and it has
  to.** Applying phase 1 twice and diffing the what-ifs shows the same five
  reporting `Modify` both times with both applies `Succeeded`, because ARM's GET
  cannot round-trip what the template declares:
  `DBforPostgreSQL/flexibleServers` never returns
  `administratorLoginPassword`, `Network/virtualNetworks` returns subnet
  delegations with server-generated `actions`/`id`/`etag`/`type`/
  `provisioningState`/`resourceGroup`, and the other three normalise
  server-defaulted properties. The list lives in `NON_CONVERGENT_MODIFY` in
  `cd-azure-beta.yml`. `Create` and `Delete` are still failures for every type,
  so a resource vanishing out of band is still caught. A `Modify` on a type not
  in that list is a real finding - fix the template or add the type with
  evidence.
- **A failed deployment used to be reported as a success.** Both Apply steps
  ended in `az deployment group create ... | tee`, and the step shell is
  `bash -e` with no `pipefail`, so a failure returned `tee`'s exit code, every
  output was consumed as an empty string, and the real error surfaced a step or
  two later as something unrelated. They now redirect, assert
  `provisioningState`, print the nested error, and verify each output they
  consume is non-empty. `pipefail` was deliberately not added instead: the
  `verify` job's `curl | tee /dev/stderr | grep -q` assertions would fail on
  SIGPIPE even when the assertion matched.
- **The custom domain is off until DNS exists, and turning it on takes two
  deploys.** `apiHostname` is set to `api.skyrict.in`, but `bindCustomDomain`
  is `false`, so the gateway serves only its generated
  `*.azurecontainerapps.io` FQDN and no certificate is requested. This is not
  a precaution - the certificate cannot be created in one pass:

  - ACA refuses a managed certificate for a hostname that is not already
    registered on a container app (`RequireCustomHostnameInEnvironment`),
    while the `customDomains` entry references that same certificate. So the
    hostname must be bound first, with no `certificateId`.
  - `api.skyrict.in` has no DNS record at all, so validation cannot succeed
    regardless.

  To activate it, in order, with a deploy between each step:

  1. Add the registrar CNAME `api.skyrict.in` pointing **directly** at
     `app-gateway-skyrict-beta.cae-skyrict-beta.westus.azurecontainerapps.io`
     (an intermediate CNAME permanently blocks certificate issuance), TTL 600.
  2. Set `bindCustomDomain: true` and deploy. This registers the hostname on
     the gateway with no certificate yet, which is what step 3 requires.
  3. Set the `validationMethod: 'CNAME'` record ACA asks for, at
     `_acme-challenge.api.skyrict.in`, and deploy again. The certificate is
     created and the binding picks it up.

  Until step 3 completes, only the generated FQDN answers. The CD's `verify`
  job probes that FQDN on purpose, so the first deploy never depends on a DNS
  record that is an operator task rather than a deploy task. `BASE_DOMAIN`,
  `JWKS_ISSUER` and `JWKS_AUDIENCE` are already configured for
  `api.skyrict.in` and match as soon as the name resolves.
- The observability module requires subscription-level deploy permissions.
- Jobs and apps share the KV secret store; rotation requires a redeploy.
- Free-trial scale knobs are conservative (max 2 replicas, pooled DB
  connections of 3). See ADR-010 for sizing rationale and
  `azure-cost-estimate.md` for numbers.