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

1. **Phase 1** - `deployWorkloads=false deployApps=false`: environment,
   security, registry, data, budgets. Grants AcrPush to the deploy principal,
   then CD sets `azure.extensions=vector,pg_trgm,pgcrypto` and seeds the KV
   secrets. Setting it **replaces** Azure's default allow-list rather than
   adding to it, so every extension a migration needs must be named here.
2. **Phase 2a** - `deployWorkloads=true deployApps=false`: the 4 jobs only.
3. **Migrations** - CD runs `db-init` → identity → core → ai-agent in
   dependency order (identity owns `tenants`/`current_tenant_id()`).
4. **Phase 2b** - `deployWorkloads=true deployApps=true`: the 4 apps, pinned to
   the immutable git-SHA image tag; then CD applies the same parameters a second
   time and asserts **zero real changes** (idempotency).

**The apps come after the migrations, and the order is not negotiable.** All
three services call `verify_startup_dependencies()` in the FastAPI lifespan;
`check_database()` raises when the database is absent and the process exits.
Observed live when the apps were deployed before `db-init`:

```
asyncpg.exceptions.InvalidCatalogNameError: database "skyrict_identity" does not exist
  -> startup.verification_failed -> Application startup failed. Exiting.
```

An app deployed before `db-init` is not a slow-starting app, it is a
crash-looping one, and whether it recovers depends on how long ACA keeps
retrying the restart. `deployApps` is the parameter that makes the ordering
expressible; see `infra/azure/modules/apps.bicep`.

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

- **Logs**: there are **no per-app diagnostic settings**, and adding one fails
  the whole deployment. A `Microsoft.Insights/diagnosticSettings` resource
  pointed at a container app's `logCategories` is rejected with
  `BadRequest: Category 'ContainerAppConsoleLogs' is not supported.` Container
  apps expose no log categories at all - only metrics, via `:AllMetrics`. App
  console and system logs are already routed to `log-skyrict-beta` by the
  **environment's** `appLogsConfiguration` (see `environment.bicep`); query
  `ContainerAppConsoleLogs_CL` and `ContainerAppSystemLogs_CL`. Do not add
  diagnostic settings at the resource level, and do not add environment-level
  ones either - the environment already does this.
  Live job logs are read with `az containerapp job logs show -n <job> -g <rg>
  --execution <exec> --container <name>`; see §7 for why the timing matters.
  (`az containerapp job execution logs show` is not a command.)
- **Scale**: apps run `minReplicas: 0`, scale out at 100 concurrent requests
  to `maxReplicas: 2`. That per-app cap is the only node cap: the Consumption
  workload profile accepts neither `minimumCount` nor `maximumCount`, so
  `Microsoft.App/managedEnvironments` rejects the deployment with
  `WorkloadProfilePropertyNotSupported` if either is set.
- **Budgets**: subscription budgets alert at 50/80/90% of `$10` (CD passes
  the first-of-month as `budgetStartDate` so re-applies stay idempotent).
- **Cost**: see `azure-cost-estimate.md`.
- **`Succeeded` does not mean running.** A container app or job can report
  `provisioningState: Succeeded` and a revision `Provisioned` while every
  replica sits at `runningState: NotRunning`, because the process exits during
  startup and the revision was still created. Resource state reports the ARM
  write, not the container. Check
  `az containerapp replica list -n <app> -g <rg> --revision <rev> --query
  "[?properties.runningState=='Running'] | length"` and read the container log
  before believing a deployment is healthy. This has bitten this pipeline
  repeatedly: a swallowed exit code, a masked image tag, a probe pointing at a
  tag the image does not have, Bicep silently dropping `workingDir`, and now an
  app deployed before its database existed.
- **Internal addressing.** The three backends are `external: false` and are
  only resolvable inside the VNet, at
  `<app>.internal.<environmentDefaultDomain>` - for example
  `app-identity-skyrict-beta.internal.bluesky-957ace7a.westus.azurecontainerapps.io`.
  Short app names do **not** resolve in a VNet-integrated environment, so every
  service-URL env var carries the full internal FQDN. ACA's HTTP ingress always
  listens on **443** (plus 80 only when `allowInsecure: true`); `targetPort` is
  where ingress forwards *to*, never a port it listens on. The three backends
  therefore set `allowInsecure: true` and are addressed `http://<internal-fqdn>`
  with no port suffix - with `allowInsecure: false` ACA answers plain HTTP with
  a 301 to HTTPS, and neither nginx nor httpx follows an upstream redirect, so
  the gateway would hand the browser a redirect instead of an API response. The
  gateway itself is `external: true` and keeps `allowInsecure: false`; it is the
  only public app and must stay TLS-only.
- **nginx `map_hash_bucket_size`.** The gateway's `nginx -t` runs in the
  entrypoint, so a config error kills every replica at container start and the
  app never serves a request. The `skyrict_api_segment` map has enough keys to
  overflow the default 64 buckets, which nginx rejects with
  `[emerg] could not build map_hash, you should increase map_hash_bucket_size:
  64`. `gateway.conf.template` sets `map_hash_bucket_size 256;` and
  `map_hash_max_size 2048;` in the `http` block for this reason. Keep the map
  in sync with `apps/web/src/app/api/v1/[...path]/route.ts`, and re-run
  `nginx -t` on the rendered config whenever the map changes - a container that
  exits 1 at start leaves no trace in ARM state.

## 7. Jobs (db-init + migrations)

Run through the job CLI (CD does this automatically):

```bash
exec=$(az containerapp job start -n job-db-init-skyrict-beta -g skyrict-beta --query name -o tsv)
az containerapp job execution show -g skyrict-beta -n job-db-init-skyrict-beta \
  --job-execution-name "$exec" --query properties.status -o tsv   # wait for Succeeded
```

> The job is `-n` / `--name` and the **run** is `--job-execution-name`.
> `--job-name` and `--execution-name` are not accepted: every call exits
> non-zero with a usage error, and if a poll loop swallows that it spins for
> its full timeout and then reports "timed out" for a job that may well have
> succeeded. Verified against a real execution on `skyrict-beta`.

> **A finished execution's logs are unreadable.** Once the state is terminal
> the pod is reaped and `az containerapp job logs show` returns
> `No replicas found for execution`. Measured on this subscription:
>
> | execution state | `job logs show` |
> | --- | --- |
> | `Running` | the container's real output |
> | `Succeeded` | `No replicas found for execution` |
> | `Failed` | `No replicas found for execution` |
>
> **Succeeded is reaped too**, so this is not a failure-only quirk - there is
> no window in which to fetch after the fact. `--follow` is not a workaround:
> tested, it returned on its own after 17s with exit 0 while the execution was
> still `Running`, so it does not stream until the container exits.
>
> So sample on **every** iteration and keep the last one, which is what CD
> does. Sampling only on the iteration where the status flips to `Failed`
> captures nothing, because the replica is already gone by then:
>
> ```bash
> az containerapp job logs show -g skyrict-beta -n job-db-init-skyrict-beta \
>   --execution "$exec" --container db-init --tail 25
> ```
>
> On a fast-failing job this is still a race against the 15s poll interval.
> When you need logs that survive the execution, use Log Analytics instead -
> the environment routes job and app console output to `log-skyrict-beta`
> (§6), and that history is retained:
>
> ```kusto
> ContainerAppConsoleLogs_CL
> | where ContainerName == "job-identity-skyrict-beta"
> | order by _timestamp_desc
> ```
>
> That is the only source here that still has the reason once the replica is
> gone. Two real failures on this environment were unreadable retrospectively
> and looked like bare `Failed` statuses.
>
> The container names are `db-init` (the `postgres:16-alpine` job) and
> `migrate` (the three alembic jobs). The execution record itself carries only
> `startTime` / `status` / `template` - `properties.error` is not persisted, so
> the container log is the only place the reason appears. Two real failures on
> this environment were unreadable after the fact and looked like bare
> `Failed` statuses.

Order is **always** `db-init` → identity → core → ai-agent. db-init
creates `skyrict_identity` and enables `vector`, `pg_trgm` and `pgcrypto`
idempotently;
each migration job runs `alembic upgrade head` with an explicit
`-c /app/services/<svc>/alembic.ini` config so each service writes to its
own version table (`alembic_version` / `alembic_version_core` /
`alembic_version_ai`).

> The migration jobs also `cd /app/services/<svc>` first. alembic resolves a
> **relative** `script_location` against the process working directory, not
> against the `-c` config file, and these ini files say
> `script_location = alembic` with `prepend_sys_path = src`. With the image
> `WORKDIR` at `/app`, running alembic from there dies immediately with
> `Path doesn't exist: alembic` and applies nothing.
>
> `workingDir` is not the fix: it is not a member of the jobs `Container` type,
> so Bicep emits `BCP037` and silently drops it. The `sh -c 'cd … && alembic …'`
> form is.
>
> **Every extension a migration needs has to be in `azure.extensions`.**
> `pgcrypto` is not optional and not a leftover: it backs the tamper-evident
> audit hash chain, and the trigger computes `encode(digest(…, 'sha256'),'hex')`
> on every audit insert. Two of the three services create it -
> `identity/0001_initial_schema.py` and `core/0010_erp_sequences_and_audit_log.py`.
> Leaving it out fails as:
>
> ```
> asyncpg.exceptions.FeatureNotSupportedError: extension "pgcrypto" is not
>   allow-listed for users in Azure Database for PostgreSQL
> [SQL: CREATE EXTENSION IF NOT EXISTS pgcrypto]
> ```
>
> Adding it to the allow-list restarts the server, which is why CD does it
> between phase 1 and phase 2 rather than leaving it to the template.

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

  1. Add the registrar CNAME `api.skyrict.in` pointing **directly** at the
     gateway's **generated** FQDN, TTL 600. An intermediate CNAME permanently
     blocks certificate issuance.

     ```
     app-gateway-skyrict-beta.bluesky-957ace7a.westus.azurecontainerapps.io
     ```

     > The environment's default domain is whatever ACA generated -
     > `bluesky-957ace7a.westus.azurecontainerapps.io` today - **not** the
     > environment name. `cae-skyrict-beta.westus.azurecontainerapps.io` does
     > not resolve. Read the real value with
     > `az containerapp env show -g skyrict-beta -n cae-skyrict-beta --query
     > properties.defaultDomain -o tsv`, or take it from the CD's `api_fqdn`
     > output. It is also exported as the `environmentDefaultDomain` output for
     > exactly this reason.
  2. Set `bindCustomDomain: true` and deploy. This registers the hostname on
     the gateway with no certificate yet, which is what step 3 requires.
  3. Create the validation record ACA asks for at `_acme-challenge` under
     `api.skyrict.in`, and deploy again. The certificate is created and the
     binding picks it up. The Bicep property is
     `domainControlValidation: 'CNAME'` on the managed certificate.

     > `validationMethod` is not a real property. Bicep does not enum-check
     > it, so it compiles clean and ARM ignores it, leaving the certificate
     > with no validation method and the binding stuck. The resource is still
     > gated on `bindCustomDomain=false` by default, so it does not deploy
     > until step 2.

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