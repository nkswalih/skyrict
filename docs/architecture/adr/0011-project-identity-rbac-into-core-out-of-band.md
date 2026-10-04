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
`core_user_roles` rows, and repairs only those, one transaction per tenant, by
calling the `sync_rbac_from_identity(tenant_id)` the boot path already uses.
There is no second projection implementation to drift from the first.

`core_user_roles`, not `core_roles`, is the table tested — it is the one
`require_permission` reads, so it is the one whose absence means lockout. See
"What the anti-join must test" below; an earlier revision keyed the query off
`core_roles` and was blind to a tenant whose catalog had landed but whose grants
had not.

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

### What the anti-join must test

The query selects tenants holding identity grants but **no `core_user_roles`
rows**. An earlier revision tested `core_roles` instead, reasoning from the fact
that the catalog is what step 1 writes. That was wrong, and it failed silently.

Step 1 writes `core_roles`, step 2 writes `core_user_roles`, and both commit in
one transaction, so they cannot diverge through a crash. But they diverge in the
way that matters. A tenant whose grant names another tenant's role has its
catalog copied by step 1 while step 2's tenant-pinned role-name join matches
nothing. That tenant holds a complete role catalog and zero access.

Keyed off `core_roles`, the tick saw such a tenant as healthy, counted it as
reconciled, logged no warning, and never selected it again — the catalog step 1
had just written satisfied the anti-join. The one anomaly this design explicitly
defends against, the tenant pin on step 2, was thereby converted from a widening
bug into a lockout the reconciler could not see. `core_user_roles` is the table
`require_permission` reads, so it is the table whose absence means lockout, and
progress is measured against it for the same reason.

### The query is chosen by measurement

`EXPLAIN (ANALYZE, BUFFERS, TIMING OFF)` against a throwaway `postgres:16` with
pgvector, at 10,000 tenants / 40,000 roles / 50,000 grants, mean of five runs
after warm-up. Three candidates on one fixture, so the columns are comparable:

| Candidate | healthy | signup gap | catalog only | partial | outage |
|---|---|---|---|---|---|
| A — `core_roles` anti-join (superseded) | 44.67 ms | 27.00 ms | 33.80 ms | 42.87 ms | 45.90 ms |
| **B — `core_user_roles` anti-join (chosen)** | **44.90 ms** | **31.75 ms** | **54.46 ms** | **44.51 ms** | **33.21 ms** |
| C — grant-level, inverse of step 3's `DELETE` | 845.96 ms | 1104.20 ms | 841.31 ms | 814.04 ms | 6.89 ms |

Gaps each candidate actually **found**, same fixtures:

| Scenario | Gaps present | A | B | C |
|---|---|---|---|---|
| healthy | 0 | 0 | 0 | 0 |
| fresh signup — the incident | 109 | 109 | 109 | 109 |
| catalog landed, grants did not | 109 | **0** | 109 | 109 |
| some grants landed, some did not | 109 | **0** | **0** | 109 |
| total outage | 10,000 | 10,000 | 10,000 | 10,000 |

B is chosen because it costs what A cost and finds the case A missed. C finds
everything and is rejected on cost: 1104 ms is 22% duty at the active interval
and 44% across two replicas, on a 0.25-CPU container. C is cheaper only in a
total outage (6.89 ms against B's 33.21 ms), where `core_user_roles` is empty
and the per-grant anti-join short-circuits — which is the one scenario that does
not need detecting anyway.

This also corrected an assumption worth recording, because the intuitive version
is wrong: tick cost does **not** scale with the number of gaps. An earlier
`user_roles`-driven anti-join hash-built the whole `core_roles` side every tick,
so it was O(total roles) whether or not anything was broken. All three candidates
above are O(tenants) instead.

**What B still does not find.** A tenant with *some* grants projected and others
missing. Detecting that needs a per-grant anti-join — candidate C — at 15–35× the
cost wherever grants are projected. It is reachable only if identity holds a
grant whose role belongs to a different tenant, which is already a
privilege-escalation defect in identity: identity's own reconcile treats any
`tenant_owner` holder as full access regardless of tenant. Such a tenant keeps
partial access rather than none. Repairing that belongs with a fix to the
identity defect, not with a background loop guessing at which side of the row
is wrong.

### Bounded on three axes

Beta runs `minReplicas=1` / `maxReplicas=2`, so two ticks cost at most ~109 ms of
database time per period: 1.1% duty against the active interval and 0.09% against
the idle cap at the 54.46 ms worst case.

- **A 200-tenant per-tick cap.** Without it, a total outage reconciles 10,000
  tenants as 10,000 transactions inside a single tick on a 0.25-CPU container.
- **±20% jitter.** Two replicas would otherwise tick on the same boundary.
- **A 900 s cooldown for any tenant whose reconcile projects no grants.** Such a
  tenant stays selected — correctly, since it is still locked out — so the cooldown
  is what stops the tick re-attempting it every few seconds. It counts
  `core_user_roles`, not `core_roles`, because counting the catalog cannot tell a
  healthy repair from a failed one: step 1 populates it either way. It is a
  cooldown, not a blacklist — if the underlying row is repaired, the tenant
  converges on its own.

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

The cap is therefore 60 s rather than 300 s, and at that cap the same run measured
55.5 s. That bounds the worst case near a minute for 0.09% duty instead of
0.018% — five minutes of a tenant owner meeting 403s is a poor trade for 44 ms
of extra database time per minute. The incident being fixed ran ~29 minutes, so
even the 300 s cap was a 5.4× improvement, but a locked-out owner is precisely
the failure this change exists to remove, and the extra polling is noise
against a 0.25-CPU container.

### The worker refuses to start if RLS would hide the gap

`core_roles` and `core_user_roles` are both protected by
`tenant_id = current_tenant_id()`, and `current_tenant_id()` returns NULL when
`app.current_tenant_id` is unset. That GUC is set transaction-locally per
request (`core/db/session.py`), so a background task has no tenant context. The
tick therefore depends on the database role bypassing RLS; core's role carries
`BYPASSRLS` and owns both tables, verified on beta.

The capability probe checks **both** tables, not one. Ownership is per-table, so
a role owning only `core_roles` would satisfy a single-table probe while its
reads of `core_user_roles` were still filtered — which would make every tenant
look unprojected and every tick select every tenant.

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
idempotent, and the benign race — replica B sees no `core_user_roles` yet and
also reconciles — converges on the next tick. A lock has the worse failure mode:
if it is held, the tick *skips*, so a crashed or partitioned holder starves
reconciliation instead of merely duplicating it.

## Consequences

- A signup tenant's owner resolves full permissions without waiting for a deploy
  or restart: measured 4.9 s while the loop was active and 55.5 s worst case at the
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
- **Three different anomalies, three different defences.** Mutation checking
  established that they are not interchangeable, and conflating them hides a
  bug.
  1. *A grant naming another tenant's role, where the target owns a same-named
     role.* Dangerous: without the pin the user is handed `*`.
  2. *A tenant with grants but no catalog of its own.* Step 1 writes nothing, so
     nothing lands and the no-progress cooldown applies. A fixture built on this
     anomaly does **not** exercise the pin, because with no catalog the join
     alone already blocks the row — that gap was found only by removing the pin
     and watching a test stay green.
  3. *A tenant whose catalog landed but whose grants did not.* Step 1 succeeds
     and step 2 matches nothing. This is the case the anti-join originally
     could not see; `test_grants_absent_but_roles_present_is_repaired` and
     `test_unmatchable_grant_is_flagged_not_reported_as_repaired` pin both
     halves — that it is detected, and that an unrepairable one is warned about
     rather than reported as reconciled.
  The distinguishing signal is `core_user_roles`, not `core_roles`: step 1
  populates the catalog in all three cases, so only the grant table separates a
  healthy repair from a silent lockout.
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
  whether any of the three anomalies above occur in practice. The interval and
  query numbers come from a local container with a warm page cache, which is
  optimistic relative to a managed instance.
- **Known blind spot, by choice.** A tenant with *some* grants projected and
  others missing is not detected — that needs candidate C at 15–35× the query
  cost. It is reachable only through the identity cross-tenant grant defect,
  which is itself a privilege-escalation bug, and such a tenant retains partial
  access rather than none. Detecting it properly belongs with the fix to that
  identity defect.
- Existing workers' enable flags are not declared in Bicep and rely on their
  pydantic defaults; this flag is declared. That inconsistency is pre-existing and
  tracked separately.