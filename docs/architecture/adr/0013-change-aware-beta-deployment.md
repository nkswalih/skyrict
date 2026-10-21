# ADR-0013: Change-aware deployment to Azure beta

## Status

Accepted

## Date

2026-10-21

## Context

`cd-azure-beta.yml` deployed the whole environment on every matching push to
`dev`: it built the identity, core, ai-agent and gateway images, applied the
full Bicep in phase 1 and again in phase 2, ran db-init and all three Alembic
jobs, and rolled all four Container App revisions. A one-file change in
`services/core` therefore rebuilt and restarted identity and ai-agent as well,
and a change that could not affect the deployment at all still paid for the
full rollout.

The trigger list had two concrete gaps in the other direction:

- `infra/docker/gateway/**` was not a trigger path, so a gateway Dockerfile
  or entrypoint change did not deploy at all.
- `.github/workflows/ci-infra.yml` was a trigger path, so a CI-only change
  deployed beta.

`cd-staging.yml` deploys identity only, but watched `services/**`, `apps/**`,
`libs/**` and `infra/**`. A web-only change or a core/ai-agent change rebuilt
and redeployed staging for nothing.

The four images do not share one dependency set. From the service
`pyproject.toml` files and the Dockerfiles' `COPY` lists:

| component | sources that can change its image |
| --- | --- |
| identity | `services/identity/**`, `libs/skyrict-common/**`, `libs/skyrict-events/**`, `uv.lock`, root `pyproject.toml` |
| core | `services/core/**`, `libs/skyrict-common/**`, `libs/skyrict-events/**`, `uv.lock`, root `pyproject.toml` |
| ai-agent | `services/ai-agent/**`, `libs/skyrict-common/**`, `uv.lock`, root `pyproject.toml` |
| gateway | `infra/docker/gateway/**`, `infra/nginx/gateway.conf.template` |

`libs/skyrict-testing` and `libs/skyrict-fabric` are not runtime dependencies
of any deployed image, and `services/_template` is not in the workspace.

There is a second, less obvious fan-out: `main.bicep` passes outputs from
`data.bicep`, `environment.bicep` and `security.bicep` into the apps module
(`redisName`, the CAE default domain, the Key Vault URI, the ACR login
server). An "infra-only" change to one of those modules can therefore change
an app's environment without changing any file under `services/`.

## Decision

Add a `changes` job to `cd-azure-beta.yml` that diffs the pushed range
(`github.event.before..github.sha`) and maps the changed paths to
`identity`/`core`/`ai-agent`/`gateway`. The same mapping drives four
independent decisions:

1. which `docker/build-push-action` steps run;
2. which Bicep apps and migration jobs are evaluated
   (`deployIdentity`/`deployCore`/`deployAiAgent`/`deployGateway`,
   defaulting `true`);
3. which migration jobs are started;
4. which image tags the apps reference (`identityImageTag` and friends,
   each defaulting to the existing `imageTag`).

Fan-out rules:

- **Any path under `infra/azure/**`, `scripts/azure/**`, or this workflow,
  or the root `.dockerignore`**, maps to all four components. Broad on
  purpose: a data/environment/security module can change an app's
  environment, and the build context for every image is the repo root, so a
  dockerignore change can alter any image. Infra and deploy-policy changes
  are rare, so they keep the previous full-rollout behaviour.
- **`workflow_dispatch`** maps to all four. A manual run is the operator
  asking for a full rollout.
- **No usable base commit** (first push on a branch, or a force-push whose
  `before` is no longer in the clone) maps to all four. A filter that
  silently matches nothing would skip the deployment, which is the one
  failure mode this job must not have.
- A push that maps to no component still runs phase 1 and verification.
  Phase 1 is the environment's convergence pass and is intentionally not
  conditioned on a code change; no image is built and no app revision is
  rolled.

Safety rails that make a partial rollout safe:

- **ACR presence check.** Before phase 2a, every component whose deploy flag
  is true is checked with `az acr repository show --image repo:tag`. A flag
  that refers to a tag this run did not push fails there with the repository
  and tag, instead of later as a ContainerApp image-pull error.
- **Migration gating.** db-init starts only when a backend service changed,
  and each Alembic job starts only when its service was redeployed. An
  unchanged service's job still points at the image it already ran.
- **FQDN fallback.** `apiFqdn` is only emitted when the gateway is evaluated.
  When the gateway is not rolled, the existing FQDN is read from the live app
  with `az containerapp show`; the gateway's name is emitted unconditionally.
- **Rollout-aware verification.** The revision checks always assert a
  Provisioned revision; a running replica is required only for components
  this run rolled. An unchanged app may legitimately sit at zero replicas when
  `keepBackendsWarm` is false, and requiring one there would fail a healthy
  no-op rollout.
- **Defaults preserve the old contract.** Every new Bicep parameter defaults
  to the previous behaviour (`imageTag`, `true`), so an invocation that sets
  only `imageTag` still deploys all four.

The staging filter is narrowed to identity's inputs (the service, its two
workspace libs, the lock, the k8s overlays and Terraform). `apps/**` is
removed from it; the web app deploys through Vercel.

## Alternatives rejected

- **`dorny/paths-filter` alone.** It expresses globs, not the dependency
  graph, so the common/events fan-out would still need a second mapping step.
  The explicit `case` keeps the policy in one readable place and adds no
  action dependency to pin and audit.
- **One workflow per service.** Four copies of the login, phase-1, migration,
  idempotency and verification logic, and the shared phase 1 would run four
  times or need a fifth orchestrator workflow.
- **Skipping phase 1 when no component changed.** It saves a convergence pass
  that is already idempotent, at the cost of a skip cascade through `needs`
  and a second definition of "nothing to do".
- **Live ACR tag resolution or moving tags.** The immutable git SHA is the
  deployment contract; resolving "latest" would make a partial rollout depend
  on registry state rather than on the commit.

## Consequences

- A service-only push builds one image, runs one migration job (plus
  db-init), and rolls one revision. The other three apps keep their current
  revisions.
- A shared-lib change still fans out to every service that imports it:
  `skyrict-common` to all three Python services, `skyrict-events` to identity
  and core only.
- Infra, script and workflow changes remain full rollouts.
- The change map is policy, not discovery: adding a workspace dependency to a
  service requires updating the `case` in `cd-azure-beta.yml` (and this ADR).
  The map is reviewed by that rule, not enforced by a test.

## Verification

- The mapping was exercised against real commit ranges: a core-only commit, a
  `skyrict-common`-only commit, a `skyrict-events`-only commit, an
  ai-agent-only commit, a gateway-template-only commit, a dockerignore-only
  commit, a Bicep commit, a no-change range, a manual dispatch and a zero
  `before`. Each produced the expected four flags.
- `actionlint` passes on `cd-azure-beta.yml` and `cd-staging.yml`; every
  `run:` block passes `bash -n` after masking GitHub expressions.
- The `ci-infra` guard that checks every deployment output the workflow reads
  against `main.bicep` still passes (12 consumed, all declared).
- Post-merge: one forced full rollout (the workflow file is in the fan-out
  set), then a `services/core/**`-only push asserting one image build, one
  migration job, and one new revision, with the identity/ai-agent/gateway
  revision names unchanged.
