# ADR-0011: Project identity's RBAC grants into core out of band

## Status

Accepted

## Date

2026-10-03

## Context

Identity and core share one Postgres database. Identity owns the authoritative
RBAC tables — `roles` (role catalog) and `user_roles` (user→role grants) — and
core resolves authorization from its own mirror of them, `core_roles` and
`core_user_roles`, in `RbacRepository.resolve_user_permissions`. `require_permission`
reads the mirror at request time and never the JWT.

`resolve_user_permissions` grants a `tenant_owner` holder full access only if the
row is in core's mirror. That is deliberate and correct: identity treats a
`tenant_owner` holder as unrestricted regardless of the stored array, while core
resolves strictly from what it can see. The two services agree only because core's
mirror is complete.

The mirror had exactly one writer. `sync_rbac_from_identity()` was called from
exactly one place — the core application lifespan, at boot. Signup emits
`identity.tenant.provisioned`, and nothing consumes it: identity's `publish_event`
is a logging-only stub, and `core/events/consumers/rbac.py` states in its own
docstring that no broker loop is wired. So the event was a no-op, and the boot
call was the whole mechanism.

A tenant provisioned between two core restarts therefore had identity grants and
no core projection, and its owner received 403 from every permission check. On
beta this was not theoretical: a tenant created at 07:50:49 UTC was locked out
for roughly 29 minutes, until core restarted at 08:19:33 for unrelated reasons.

Two structural facts made a second writer necessary rather than merely desirable:

- `user_roles` has three single-column foreign keys and **no composite
  `(tenant_id, role_id) → roles(tenant_id, id)`**. A row whose denormalised
  `tenant_id` disagrees with its role's tenant is legal and is reachable.
- Step 2 of the sync resolves core's role id through a correlated subquery on
  `roles`. Without a tenant predicate that subquery was correct only because role
  UUIDs are globally unique — an assumption nothing in the schema enforces.

## Decision

**A background reconciler projects missing grants, and nothing else does.** Each
tick runs one indexed anti-join for tenants that hold identity grants but no
`core_roles` rows, and repairs only those, one transaction per tenant, by calling
the `sync_rbac_from_identity(tenant_id)` the boot path already uses. There is no
second projection implementation to drift from the first.

### No writes in the authorization path

The tempting fix is to reconcile lazily inside `resolve_user_permissions`: find
the gap, write it, return permissions. Rejected — see below. Keeping writes out of
the read path is what makes authorization deterministic: a check either sees the
projection or it does not, and never triggers one.

### The scoped form cannot delete

`sync_rbac_from_identity` gains an optional `tenant_id`. `None` is the boot path
and is unchanged — same statements, same text, same log line, all three steps,
every tenant. A tenant id runs the two `INSERT` steps alone and **skips step 3**,
the `DELETE` that propagates IAM revocations.

That makes the scoped form additive by construction: a tick can restore missing
access and can never remove any. A tenant with no projection has no rows to
revoke, so nothing is lost by leaving revocation to the boot path, where it is
already reconciled on every deploy. It also keeps this change out of the
IAM-edit-staleness problem described under Consequences.

### The query is chosen by measurement

`EXPLAIN (ANALYZE, BUFFERS)` against a throwaway `postgres:16` with pgvector, at
10,000 tenants / 50,000 grants / 40,000 roles, mean of five runs after warm-up:

| Form | Healthy | Partial gaps | Total outage |
|---|---|---|---|
| `user_roles`-driven anti-join | 36.1 ms | 34.6 ms | 11.0 ms |
| ...also testing for missing `core_user_roles` | 205.0 ms | 217.8 ms | 68.9 ms |
| **`tenants`-driven (chosen)** | **25.6 ms** | **18.5 ms** | **41.7 ms** |

The chosen form is driven from `tenants`, so its cost tracks tenant count rather
than total grant count, and it is gated on an existing grant so a tenant that
legitimately has no grants yet is never selected. Its plan is a Nested Loop Semi
Join over a Hash Anti Join whose `user_roles` Index Only Scan reports
`never executed` when healthy — the steady-state tick never reads the grants
table at all. The variant that also tested for missing grants was rejected on
cost: 205 ms is eight times the chosen query for a rarer case.

This also corrected an assumption worth recording, because the intuitive version
is wrong: the tick cost does **not** scale with the number of gaps. The
`user_roles`-driven anti-join hash-builds the entire `core_roles` side on every
tick, so it is O(total roles) whether or not anything is broken. Only the chosen
`tenants`-driven form has the better growth shape, and even it is O(tenants).

### Bounded on three axes

Beta runs `minReplicas=1` / `maxReplicas=2`, so two ticks cost at most ~83 ms of
database time per period: 1.7% duty against the active interval and 0.07% against
the idle cap at the 41.7 ms worst case.

- **A 200-tenant per-tick cap.** Without it, a total outage reconciles 10,000
  tenants as 10,000 transactions inside a single tick on a 0.25-CPU container.
- **±20% jitter.** Two replicas would otherwise tick on the same boundary.
- **A 900 s cooldown for any tenant whose reconcile writes nothing.** This is the
  no-progress case enabled by the missing composite FK: a grant whose `tenant_id`
  disagrees with its role's tenant can never match, so the tick would otherwise
  re-select it forever. It is a cooldown, not a blacklist — if the underlying row
  is repaired, the tenant converges on its own.

### The idle cap sets the latency, and it was measured rather than guessed

An earlier draft of this ADR claimed a new tenant's owner "resolves full
permissions within seconds". That was wrong, and measuring it on a booted
service showed why: sign-ups are rare, so the loop spends nearly all its time
at the idle cap, and a tenant created just after a tick waits one whole period.
The cap is therefore the worst case, not the 5 s active interval.

Measured on core booted against this schema, with the cap at 300 s:

| Loop state | Convergence |
|---|---|
| Already active | 4.9 s |
| Mid-ramp | 13.4 s, 70.2 s |
| Fully backed off | 323.6 s |

The cap is therefore 60 s rather than 300 s. That bounds the worst case near
64 s for 0.07% duty instead of 0.014% — five minutes of a tenant owner meeting
403s is a poor trade for 14 ms of extra database time per minute. The incident
being fixed ran ~29 minutes, so even the 300 s cap was a 5.4× improvement, but
a locked-out owner is precisely the failure this change exists to remove, and
the extra polling is noise against a 0.25-CPU container.

### The worker refuses to start if RLS would hide the gap

`core_roles` is protected by `tenant_id = current_tenant_id()`, and
`current_tenant_id()` returns NULL when `app.current_tenant_id` is unset. That
GUC is set transaction-locally per request (`core/db/session.py`), so a background
task has no tenant context. The tick therefore depends on the database role
bypassing RLS; core's role carries `BYPASSRLS` and owns `core_roles`, verified on
beta.

If that capability were ever revoked, the anti-join would match nothing, every
tick would report healthy, and the worker would repair nothing indefinitely while
looking perfectly correct. So the capability is checked once at start, and the
worker logs an error and does not start if it is absent. This is a real
configuration dependency of the design, not a theoretical one.

## Alternatives rejected

**Reconcile lazily inside `resolve_user_permissions`.** Writing inside an
authorization read makes authorization non-deterministic — the same request can
succeed or fail depending on whether a repair happened to run — and a per-process
lock cannot close a cross-pod race, because with two replicas both would observe
the same gap and both write. It also puts RLS-scoped write logic in the one code
path that must never widen access.

**Run the full unscoped `sync_rbac_from_identity()` periodically.** The obvious
minimal change, and it does converge. Rejected on cost and on blast radius: at
10,000 tenants the full-table form measured 205 ms per tick, and step 3 would
hand a background loop the power to strip access based on a mirror that a partial
sync could have left temporarily wrong. Steady-state cost would also be paid for
every tenant on every tick to discover that nothing is broken.

**Have identity write core's tables.** Identity already writes the authoritative
rows and already emits `identity.tenant.provisioned`, so this removes the
duplicate representation rather than syncing it. Rejected as a much larger change
than the defect warrants: it makes one service write another service's private
tables, and it needs an outbox plus a consumer loop — infrastructure that does not
exist yet, since `publish_event` is a stub and no broker consumer is wired.
Worth revisiting when that infrastructure lands for other reasons.

**Take an advisory lock around each tick.** The `ON CONFLICT` SQL is already
idempotent, and the benign race — replica B sees no `core_roles` yet and also
reconciles — converges on the next tick. A lock has the worse failure mode: if it
is held, the tick *skips*, so a crashed or partitioned holder starves
reconciliation instead of merely duplicating it.

## Consequences

- A signup tenant's owner resolves full permissions without waiting for a deploy
  or restart: measured 4.9 s while the loop was active and ~64 s worst case at the
  60 s idle cap, against ~29 minutes before.
- **No user's access is widened beyond what identity grants.** The reconciler
  copies exactly identity's rows using the same SQL as the boot path, and the
  scoped form cannot delete. `test_reconcile_never_widens_beyond_identity_grants`
  asserts the resolved permission set equals identity's grants key for key, and
  that a user identity granted nothing stays at zero permissions.
- Reconciliation cannot widen scope through a mismatched role: the scoped
  lookup pins the role name to the grant's own tenant, so a grant naming another
  tenant's role resolves to nothing instead of matching a same-named role in the
  target tenant. The unscoped boot path keeps its original form and still relies
  on role UUIDs being globally unique — a latent assumption this change
  deliberately does not alter.
- **Two different anomalies, two different defences.** Mutation checking
  established that they are not interchangeable, and conflating them hides a
  bug. A grant naming another tenant's role is dangerous only when the target
  *owns* a same-named role: that is what the pin above defends against, and
  without it the user is handed `*`. A tenant with grants but no catalog of its
  own is a separate case — Step 1 writes nothing, so nothing lands and the
  no-progress cooldown applies. A test fixture built on the second anomaly does
  not exercise the first, because with no catalog the join alone already blocks
  the row; that gap was found only by removing the pin and watching a test stay
  green.
- **The step-2 tenant predicate is a scoping contract, not a safety guard.** It
  bounds the insert set to the tenant actually asked for, so a partly projected
  tenant is not finished as a side effect of reconciling an unrelated one. With
  the pin in place, removing it changes nothing observable for safety: every
  other row it would also consider resolves to that row's own tenant's role.
  `test_scoped_run_projects_only_the_named_tenants_pending_grant` pins the
  contract, and says in its docstring that it is not a second copy of the pin's
  test.
- `RBAC_PROJECTION_ENABLED` is the kill switch. Default true, declared in
  `apps.bicep` as `CORE_RBAC_PROJECTION_ENABLED` so it is changed declaratively
  and delivered by CD. Hand-editing the live app drifts from the declarative
  source and is reverted by the next deploy. Turning it off stops the loop; the
  boot-path sync still runs, so existing tenants are unaffected. Rolling back the
  change entirely is also safe — the boot path was never broken.
- **IAM-edit staleness is not fixed by this.** A role permission edited in IAM,
  or a grant revoked there, still reaches core only at the next boot. That is a
  different failure mode — staleness rather than absence — with the same root
  cause, and it is tracked separately rather than folded in here.
- **Unproven until it runs on beta:** end-to-end convergence timing on the real
  stack, whether the adaptive intervals hold at production tenant counts, and
  whether the tenant/role mismatch no-progress case ever occurs in practice. The
  interval numbers come from a local container with a warm page cache, which is
  optimistic relative to a managed instance.
- Existing workers' enable flags are not declared in Bicep and rely on their
  pydantic defaults; this flag is declared. That inconsistency is pre-existing and
  tracked separately.