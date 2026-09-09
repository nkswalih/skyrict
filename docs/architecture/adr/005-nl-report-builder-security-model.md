# ADR-005: NL report builder - LLM selects, Core endorses, no SQL ever leaves the catalog

## Status

Accepted

## Date

2026-09-08

## Context

SKY-80 (RPT-AI-001) adds a natural-language report builder: a user types "AR
aging as of last month" and receives a runnable report. The tempting shortcut
is "let the LLM write the SQL" - but that creates an SQL-injection and
data-leak surface (prompt-injected queries, cross-tenant reads, arbitrary
ad-hoc SQL in stored definitions), and it moves trust into a non-deterministic
model. The platform's existing constraint is also explicit: reports are
stored as reviewed, read-only, parameterized templates seeded by Core.

The builder therefore must offer the ergonomics of generative reporting
without ever weakening the review/persistence invariant that made the report
catalog trustworthy in the first place.

## Decision

The builder follows three rules:

1. **The LLM only selects from the live catalog.** The model's entire job is
   mapping free text onto one `ParsedReportSpec` whose values are chosen from
   the definitions returned by Core (`dataset`, `dimensions`, `measures`,
   `template_slug`, `confidence`). It never emits SQL, table names,
   parameter values, or arbitrary free text that reaches execution. Its
   system prompt is rebuilt from the real catalog on every request.

2. **Every LLM choice is re-validated deterministically server-side.**
   `ai_agent.features.report_builder.validator` re-checks unknown templates,
   unmatched datasets, and off-vocabulary dimensions/measures against the
   catalog fetched through the gateway; anything unrecognized becomes a
   clarification (never a guessed report), and confidence below 0.75 is an
   abstention. The unittest matrix - not the model - is the correctness gate.

3. **Core is the only authority on SQL.** The ai-agent never holds or carries
   SQL. Persisting a generated report (`POST /api/v1/reports` and the
   ai-agent's `/ai/report-builder/save`) submits `source_slug`, the chosen
   template's slug; Core resolves the reviewed template SQL server-side,
   requires any supplied `sql` to byte-match that template, requires declared
   params to equal the template's, and re-runs the read-only SQL validator as
   defense-in-depth. `default_params` (resolved dates) are pre-fill only and
   have no persistence column.

The ai-agent acts as a **proxy, never a bypass**: it forwards the caller's JWT
and `X-Tenant-Slug` to Core's read-only reports path (same permission
`erp.reports.read` as the manual UI) and to the create path (`erp.reports.create`,
seeded in `0040_report_create_permission`). The web save flow echoes only the
server-resolved `template_slug` + params; the save endpoint re-validates both.

## Consequences

### Positive

- No new injection surface: the model cannot produce SQL or arbitrary filter
  values; every vocabulary choice is bounded by the catalog.
- Stored definitions remain byte-for-byte the reviewed templates - the audit
  trail and validation story of the existing report catalog are unchanged.
- Tenant isolation is unchanged: every read/write is scoped by the forwarded
  caller identity and tenant slug, enforced by Core's proxy + RLS.

### Negative

- The builder can only produce reports the reviewed template set already
  covers; a genuinely new query shapes requires a new reviewed template
  (review cost moves to template authoring, which is the intended trade).
- Two-layer re-validation (validator vs save) duplicates some checking; this
  is deliberate defense-in-depth, not accidental coupling.

### Mitigations

- The saved report inherits its template's `dataset`/`dimensions`/`measures`
  vocabulary, so future NL refinements apply equally to user-created reports.
- The generate response carries the resolved params so the save echo is
  lossless and never re-guesses on a second LLM call.
- The uprightness of the pipeline is covered by deterministic unit tests
  (spec parse -> validator matrix -> params math -> engine pipeline) rather
  than by an LLM-scored eval; the RAGAS nightly gate remains purely about
  retrieval QA and is not polluted with non-retrieval cases.