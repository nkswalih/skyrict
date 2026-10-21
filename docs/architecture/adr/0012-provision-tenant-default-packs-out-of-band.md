# ADR-0012: Provision per-tenant default packs out of band

## Status

Accepted

## Date

2026-10-21

## Context

A tenant created by self-service signup had a row in `tenants`, a role catalog and
the owner's grant in identity, and **no core packs at all**. Every
`/api/v1/reports/{slug}/run` call for it returned 404 `Report '<slug>' was not
found`, and its HR, finance-chart and approval surfaces were empty. Observed on
a production tenant.

The packs are the per-tenant reference data every tenant is supposed to start
with:

| Pack | Table | Writer |
| --- | --- | --- |
| Leave types + payroll settings | `erp_leave_types`, `erp_payroll_settings` | `seed_tenant_hr_defaults` |
| Chart of accounts | `erp_chart_of_accounts` | `seed_tenant_finance_defaults` |
| Phase-1 report definitions | `erp_report_definitions` | `seed_reporting_defaults` |
| Approval definitions | `erp_approval_workflow_definitions` | `seed_approval_workflow_defaults` |

There was no provisioning path. Every one of those functions was reachable from
exactly two places: the manual `core seed --tenant-id` command and tests that
call them **directly**. Migrations 0036, 0039 and 0063 seeded tenants that
already existed when they ran, so tenants created afterwards fell through the
gap. `features/reporting/seeds.py` documented a hook that did not exist ("core.seed
applies the same pack when a new tenant is provisioned"), and the test suite
stayed green because it invoked the seed functions itself rather than a
provisioning path. That is the same wiring blind spot that produced ADR-0011.

Identity does not call core, and `identity.tenant.provisioned` has no consumer:
identity's `publish_event` is a logging-only stub and core's RBAC consumer states
in its docstring that no broker loop is wired. Identity and core share one
Postgres database, so core can see a new tenant directly without an event.

Two constraints shape the fix:

- **RBAC must not be re-seeded.** `seed_core_roles_for_tenant` unions core's
  static `CORE_SYSTEM_ROLES` permissions into existing `core_roles` rows
  (`seed.py`). Running it as a provisioning step would widen access beyond what
  identity granted, breaking the guarantee `RbacProjectionReconciler` exists to
  provide (ADR-0011). `core_roles`/`core_user_roles` remain a projection of
  identity, never of core's own catalog.
- **A request path must not write.** Seeding inside `get_report` or
  `require_permission` would make reads and authorization non-deterministic and
  would race across replicas.

## Decision

Add `core.seed.provision_tenant_defaults(tenant_id)`: the four non-RBAC seed
functions in one idempotent entry point. It deliberately excludes RBAC.

Add `TenantProvisioningReconciler`, an in-process background loop owned by the
application lifespan, modelled on `RbacProjectionReconciler`:

- each tick runs one anti-join for **active tenants missing any pack** and
  provisions only those tenants, one pack at a time;
- the first pass runs immediately at startup, so deploying the fix repairs every
  existing gap without an operator command;
- the interval is adaptive - 5 s after a pass that provisioned something, backing
  off to a 60 s cap when there was nothing to do - with +/-20% jitter so replicas
  do not tick on the same boundary;
- a per-tick cap (50 tenants) keeps a tick short; the loop resets to 5 s while a
  backlog remains, so a large catch-up drains without a stampede;
- a failed tenant is logged with its `tenant_id` and retried after a 300 s
  cooldown instead of on every tick; the per-tick query is widened by the
  number of cooling tenants, so a tenant that keeps failing can never hold a
  tick slot and starve the tenants ordered behind it;
- the RLS capability is checked once at startup. The provisioned tables are
  protected by `tenant_id = current_tenant_id()` and a background task has no
  request tenant, so the tick needs a role that bypasses RLS - `BYPASSRLS` /
  superuser, or ownership of all five tables (no migration sets
  `FORCE ROW LEVEL SECURITY`). Without it the anti-join would treat every tenant
  as a gap and every write would fail its `WITH CHECK`; the worker refuses to
  start and logs `provisioning.rls_not_bypassable`.

Kill switch: `CORE_TENANT_PROVISIONING_ENABLED` (default on), declared in
`infra/azure/modules/apps.bicep`. Disabled under the test environment so
integration tests drive `run_once()` directly.

Detection is presence-based: a tenant is a gap when any of the five tables has no
row for it. That is sound because each seed function commits its whole pack in
one transaction, so a crash leaves the pack either entirely present or entirely
absent. A soft-deleted report keeps its row and is therefore not resurrected -
the same behaviour as re-running `seed_reporting_defaults`.

## Measurements

`EXPLAIN (ANALYZE, BUFFERS)` on a 10,000-tenant dataset with production-shaped
packs (100,000 leave types, 10,000 payroll-settings rows, 90,000 accounts,
120,000 report definitions, 20,000 approval definitions), warm cache, three runs:

| State | Execution |
| --- | --- |
| 10 gaps | 59 / 89 / 106 ms (1 row per pack) |
| 0 gaps, 1 row per pack | 62 / 92 / 104 ms |
| 0 gaps, production-shaped packs | 213 / 420 / 254 ms |

The plan is a hash anti-join per pack over a `tenants_pkey` index scan ordered by
`id`; when a gap exists the scan stops after `LIMIT` tenants. Cost is therefore
linear in the total number of pack rows, not in the number of gaps, and the
steady state is not cheaper than the catch-up. At the 60 s idle cap that is
0.35-0.7% of one core at 10,000 tenants. During a backlog the loop runs every 5 s,
i.e. 4-8% of one core, for as long as the catch-up lasts. The query is
sub-millisecond at the tenant counts this incident was observed at.

If the tenant population grows an order of magnitude, the escalation path is a
watermark on `tenants.created_at` (measured 24 ms at 10,000 tenants when no
tenant is new) plus a slower full sweep, or a partial index on the pack tables.
Neither is justified yet.

## Alternatives rejected

- **Seed lazily in the request path.** Writes inside `get_report`/`list_reports`
  (or worse, `resolve_user_permissions`) make reads non-deterministic, put a write
  on the authorization path and race across replicas. Rejected for the same
  reason ADR-0011 rejected it.
- **Consume `identity.tenant.provisioned` over Kafka.** The broker loop is not
  wired in either service; building it is a much larger change than the defect
  and would still need a backfill for tenants already missing packs.
- **An authenticated internal core endpoint called by identity at signup.** The
  correct long-term contract, but it adds a new service-to-service auth surface,
  couples identity's signup to core's availability and still needs a backfill.
  Because the services share a database, core can detect the tenant without it.
- **A one-off backfill migration.** Fixes today's tenants and nothing else;
  migration 0039 already had to duplicate the seed SQL to do it. The reconciler's
  first pass is the backfill and also covers every future tenant.
- **`core seed --tenant-id` as the remediation.** It also calls
  `seed_core_roles_for_tenant`, which unions core's static permissions into
  existing rows and can widen access. It remains a manual tool, not the
  provisioning contract.
- **Seed RBAC from core's static catalog in the reconciler.** Contradicts
  ADR-0011 and the `tenant_owner` invariant.

## Consequences

Positive:

- A tenant created by signup gets every non-RBAC default pack within the idle
  interval, with no operator action. Existing gaps are repaired by the first
  pass after deploy.
- No new infrastructure, no new service-to-service contract, no second
  provisioning implementation to drift from the CLI.
- RBAC is untouched: `core_roles`/`core_user_roles` still contain only what
  identity granted. The regression test asserts the reconciler writes zero rows
  to them.
- Every write is additive and idempotent, so a retry, a replica restart or two
  replicas racing all converge on the same state.

Negative / accepted:

- A background write path exists. It is bounded by the per-tick cap, the failure
  cooldown and the kill switch.
- New-tenant worst-case latency is the idle cap (60 s). A user who reaches the
  reports page within that window can still see an empty list; the next request
  after the pass succeeds. The boot pass means this only applies to tenants
  created after the process started.
- The steady-state query re-reads the pack tables every tick (measured above)
  rather than tracking a watermark. Accepted for simplicity at current scale.
- Inactive tenants are skipped until they are active. A tenant deactivated at the
  moment of a pass is provisioned on a later pass after reactivation.
- A partially seeded pack that still has at least one row is not re-selected.
  Unreachable through a crash (packs commit atomically) and not created by the
  defect; a manual `core seed --tenant-id` remains the repair.

Rollback: set `CORE_TENANT_PROVISIONING_ENABLED=false` in `apps.bicep` and
deploy. Rows already written are additive reference data and are left in place;
nothing needs to be unwound. The reconciler's absence restores the pre-ADR state
(manual seeding only).

## Verification

`services/core/tests/integration/database/test_tenant_provisioning_reconciler.py`:
a bare tenant has no packs; the entry point fills all five; the twelve Phase-1
reports become listable and `get_report` stops raising `NotFoundError`; the entry
point is idempotent; it writes zero `core_roles`/`core_user_roles` rows; a
partially deleted pack is repaired; `run_once` detects and provisions a gap; a
failing tenant is isolated and cooled down; a cooling tenant does not starve a
due tenant behind it; the loop refuses to start without the RLS capability; the
loop provisions and stops cleanly.

A real boot against Postgres confirmed `provisioning.started`, and a tenant
inserted while the process was running was provisioned on the next tick (4 leave
types, 1 payroll-settings row, 9 accounts, 12 report definitions, 2 approval
definitions) with no operator action. The ownership branch of the RLS probe was
verified against non-superuser roles: a role owning all five tables passed, a
role owning four failed.
