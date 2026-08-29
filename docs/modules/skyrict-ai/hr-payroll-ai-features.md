# HR/Payroll AI Features — Technical Specification

This document specifies the AI-powered HR & Payroll slice delivered by ticket
**HR-AI-001**. It is the scoped, reviewable implementation plan for the first
L1–L2 portion of the broader *AI Implementation in HR & Payroll Module*
proposal (`ai-hr-payroll-proposal.md`). Every feature is an **advisor** — it
suggests, flags, and explains; it never executes a human-gated decision on its
own.

> **Status:** Implemented (HR-AI-001).
> **Security posture:** Read-only aggregates by default; individual indicators
> gated by `erp.hr.ai.individual`; every outbound LLM payload passes through the
> PII redaction pipeline.
> **Scope note:** This doc covers only the L1–L2 slice. The full 45-opportunity
> proposal (salary benchmarking, pay equity, budget forecasting, org
> optimization, etc.) is future work and is **not** part of this ticket.

---

## Table of contents

1. [Overview](#1-overview)
2. [Data-scope model (L1 vs L2)](#2-data-scope-model-l1-vs-l2)
3. [Permission matrix](#3-permission-matrix)
4. [PII redaction pipeline (prereq gate)](#4-pii-redaction-pipeline-prereq-gate)
5. [Feature 1 — L1 aggregates & narratives](#5-feature-1--l1-aggregates--narratives)
6. [Feature 2 — Attrition model & factors](#6-feature-2--attrition-model--factors)
7. [Feature 3 — Payroll anomaly detection](#7-feature-3--payroll-anomaly-detection)
8. [Feature 4 — Compliance engine v1](#8-feature-4--compliance-engine-v1)
9. [Feature 5 — HR Copilot agent](#9-feature-5--hr-copilot-agent)
10. [Security architecture](#10-security-architecture)
11. [Database design](#11-database-design)
12. [Model eval harness (HR-AI-002 / SKY-72)](#12-model-eval-harness-hr-ai-002--sky-72)
13. [HR-AI wave 2 — Leave anomaly inbox, calendar-aware suggestions & pattern data](#13-hr-ai-wave-2--leave-anomaly-inbox-calendar-aware-suggestions--pattern-data)
14. [Test strategy](#14-test-strategy)

---

## 1. Overview

### 1.1 What we are adding

| Feature | Purpose | Data scope |
|---------|---------|-----------|
| PII redaction pipeline | Mask/strip names, IDs, bank fragments, salaries in every outbound LLM payload | Cross-cutting gate |
| L1 aggregates + narratives | Headcount trend, department distribution, tenure-band summaries — **zero individual rows leave the service** | L1 (aggregate) |
| Attrition model + factors | Per-employee risk score + top-3 SHAP-style factor explanations | L2 (individual) |
| Payroll anomaly detection | Net-pay delta MoM, duplicate accounts, ghost-employee signals | L3 (financial) |
| Compliance engine v1 | Document expiry, required training overdue, missing contract fields | L3 (financial) |
| HR Copilot agent | Aggregate HR reads + draft leave-policy answers via RAG; refuses out-of-permission PII | L1 / L2-gated |

### 1.2 Why

HR & Payroll are manual CRUD today. This slice adds *intelligent* surfaces:
managers see which teams carry attrition risk (with *why*), payroll admins are
warned before anomalies are finalized, and HR conversations become natural
language — all without ever leaking an individual's personal data to a model
or to an unauthorized user.

### 1.3 Architecture summary

```
apps/web (BFF /api/v1/ai/hr/*, ModuleAccessBoundary + L1/L2 scope labels)
   │
   ▼
services/core  ── features/ai_hr/
   │              ├─ router (authz: erp.hr.ai.* + erp.ai.invoke)
   │              ├─ L1 aggregates  (SQL GROUP BY only — zero rows leave)
   │              ├─ L2 individual  (requires erp.hr.ai.individual; else 403 + L1 body)
   │              └─ proxy /ai/hr/copilot → ai-agent
   ▼
services/ai-agent
   ├── redaction/          (PII gate on EVERY outbound provider call)
   ├── features/attrition/ (GradientBoosted model + SHAP factors, model card)
   └── features/hr_copilot/(registered via agent_registry, SKY-59)
```

### 1.4 Design principles

1. **AI is a proxy, not a bypass.** Every AI path passes the same JWT, RBAC,
   RLS, and audit checks as a human user.
2. **Suggest, don't execute.** Anomalies and compliance findings are alerts;
   the acknowledge flow records human review. No AI decision mutates payroll.
3. **PII never reaches a provider.** The redaction pipeline gates every
   outbound LLM payload, fails closed, and is corpus-tested.
4. **Scope is explicit.** Every AI panel is labeled L1 (aggregate) or
   L2 (individual). Individual data requires `erp.hr.ai.individual` and is
   refused server-side otherwise.
5. **Full audit trail.** Every score view, acknowledge, anomaly, compliance
   finding, and Copilot exchange is logged with tenant, user, timestamp, and
   (for model output) model version.

---

## 2. Data-scope model (L1 vs L2)

The task's **L1/L2 data-scope levels** govern how much of a tenant's data a
consumer may see. They are orthogonal to (but map onto) the proposal's
"Security Levels 1–4":

- **L1 — Aggregate (public/internal):** counted, grouped, narrative summaries.
  No employee identifier, name, or per-person figure is returned. Examples:
  `overview`, `tenure`, the **team-risk list** (counts per band per department —
  **not** per-employee rows).
- **L2 — Individual (sensitive):** per-employee attrition score + top-3 factor
  explanations. The proposal classifies retention/attrition scoring as
  **Security Level 4** ("Organization owners, Executive leadership only"), so
  L2 access requires `erp.hr.ai.individual`, granted to the owner role plus a
  dedicated executive role only — **not** blanket `organization_admin`.
- **L3 — Financial:** compensation/payroll data underlying anomaly and
  compliance findings. Access aligns with existing `erp.payroll.read`.

**Scope labels:** every AI panel in the UI carries an **L1** or **L2** badge so
the consumer knows at a glance whether they are looking at aggregate or
individual data.

---

## 3. Permission matrix

All keys under `erp.hr.ai.*`, added to **both** the identity and core catalogs,
seeded via identity migration, and enforced at the core edge before any AI work
`erp.ai.invoke` base gate also applies to every AI path.

| Key | Scope | Meaning | Granted to |
|-----|-------|---------|-----------|
| `erp.hr.ai.read` | L1 | View aggregate HR AI panels | owner, organization_admin, department_manager, auditor |
| `erp.hr.ai.individual` | L2 | View individual attrition + factor explanations | **owner + dedicated executive role only** |
| `erp.hr.ai.acknowledge` | L2 | Acknowledge a team-risk item (audited) | owner, organization_admin, department_manager |
| `erp.hr.ai.copilot` | L1 | Use the HR Copilot | owner, organization_admin, department_manager |
| `erp.hr.ai.eval` | ops | Record ai-agent model-eval precision results (SKY-72) | operator / owner wildcard |
| `erp.ai.invoke` | base | Existing gate; every AI path requires it | existing |

**Gate semantics (Gherkin: permission gate on predictions):** a manager with
`erp.hr.ai.read` but **without** `erp.hr.ai.individual` requesting a
direct-report's attrition detail receives **403 with an aggregates-only body**
(the endpoint downgrades to the L1 shape when the L2 key is absent) — never a
has-the-row-then-censors response, and never an empty body.

---

## 4. PII redaction pipeline (prereq gate)

**Location:** `services/ai-agent/src/ai_agent/redaction/`. This is the **prereq
gate** — nothing that touches an LLM is implemented until it exists.

**Gate point:** the redactor is applied inside `LlmRouter.complete()` to every
`LlmRequest` (system + user prompt) **before** the request reaches any provider
adapter. Because the router is the ONLY path to an LLM in ai-agent, one
injection point gates **every** outbound provider payload. It **fails closed**:
anything that matches a sensitive pattern is masked; the original value is never
forwarded.

**Patterns masked (v1):**

| Pattern | Token |
|---------|-------|
| Malaysian MyKad / NRIC (`000101-10-1234`, `010203-04-5678`) | `[NRIC]` |
| Phone numbers | `[PHONE]` |
| Email addresses | `[EMAIL]` |
| Employee numbers (`EMP-*`) | `[EMPLOYEE_NO]` |
| Bank / account digit-group fragments | `[ACCOUNT]` |
| Salary figures (`RM 8,500`, `MYR 8,500`, `8,500.00`, `RM12,345`) | `[SALARY]` |
| Person names (given/family heuristics on labelled fields) | `[NAME]` |

**Corpus test (Gherkin: redaction protects providers):** free text containing a
MyKad fragment **and** a salary figure, including **mixed Malay/English** text,
is passed through the pipeline pre-LLM. The assertion checks that masked tokens
are present and raw values are **absent** from the (simulated) outbound payload.

Example corpus entry (mixed language):
```
"Gaji Wong Kar Wai RM 8,500 sebulan, kad pengenalan 000101-10-1234"
→ "Gaji [NAME] [SALARY] sebulan, kad pengenalan [NRIC]"
```

---

## 5. Feature 1 — L1 aggregates & narratives

**Location:** `services/core/src/core/features/ai_hr/`.

Endpoints (require `erp.ai.invoke` + `erp.hr.ai.read`):

| Endpoint | Output |
|----------|--------|
| `GET /api/v1/ai/hr/overview` | headcount trend by month, department distribution, tenure-band counts + rule-based narrative strings |
| `GET /api/v1/ai/hr/tenure` | tenure-band aggregate summary + narrative |

**Guarantee:** all computation is SQL `GROUP BY`/aggregate in the repository —
no employee row is ever selected and serialized. A test asserts the serialized
response contains no `employee_id`, `first_name`/`last_name`/`EMPLOYEE_NO`/
email/phone values.

Narratives are deterministic rule-based templates over the aggregate numbers
(e.g. "Headcount grew 4.2% MoM, led by Engineering (+3); tenure is
concentrated at 1–3 years (58%).") No LLM is involved in these — they are fast,
deterministic, and unit-testable.

---

## 6. Feature 2 — Attrition model & factors

**Location:** `services/ai-agent/src/ai_agent/features/attrition/`.

- **Model:** `GradientBoostingClassifier` (scikit-learn) scoring
  `risk = P(attrition)` on features derived from HR/payroll data:
  - tenure (years from `hire_date`),
  - compa-ratio band (current salary vs its department baseline),
  - promotion gap (months since last compensation `effective_from` change),
  - activity (count of recent leave movements / attendance).
- **Explanations:** `shap.TreeExplainer` yields the top-3 feature
  contributions stored per score (`factors JSONB`):
  `[{feature, contribution, direction}]`, where direction is
  `increases|decreases` risk.
- **Abstention rule (business-wide):** `confidence < 0.75` → no score is
  returned/stored (abstain) rather than exposing a low-confidence number.
- **Model card (`model_card.json`, committed):** features, training cadence
  (manual/explicit `cli.py`), known limitations, and the staleness window.
- **Refresh (lazy-on-read TTL):** the platform has **no scheduler** (matching
  the leave-accrual precedent, which uses a lazy Jan-1 reset). Scores are
  re-generated for a tenant when the attrition endpoint is read and the latest
  `generated_at` is older than `AI_HR_REFRESH_INTERVAL_DAYS` (default 7).
  Re-scoring is idempotent per `(employee, model_version)`.

> **Staleness disclosure:** because scores refresh on a lazy TTL, a displayed
> score reflects the model run whose `generated_at` is shown and may be up to
> 7 days stale — it is **not** necessarily "as of today." Every score-bearing
> response includes `generated_at`, and the UI renders an "as of <date>" label.

Endpoints (core):

| Endpoint | Permission | Output |
|----------|-----------|--------|
| `GET /api/v1/ai/hr/attrition` | `erp.hr.ai.read` (L1 shape) or `erp.hr.ai.individual` (L2) | **L1:** team-risk list grouped by department (band counts, dept-level summaries). **L2:** per-employee score + factors. Without the L2 key → **403 + L1 body** |
| `POST /api/v1/ai/hr/attrition/{employee_id}/acknowledge` | `erp.hr.ai.acknowledge` | Record human acknowledgement (audited, `hr.ai.risk.acknowledged`) |

---

## 7. Feature 3 — Payroll anomaly detection

**Location:** `services/core/src/core/features/ai_hr/`; rows in
`ai_payroll_anomaly_log`. The scan runs on payroll-run **approve** and via an
explicit CLI command.

### 7.1 Anomaly types & severity map

| Anomaly | Detection | Severity | Evidence |
|---------|-----------|----------|----------|
| `net_pay_delta` | \|Δ net MoM\| per employee > threshold | `low` < 10%, `medium` < 25%, `high` otherwise | run/entry ids, before/after net |
| `duplicate_account` | same account number across entries in a run | `high` | run id, affected entry ids, account fragment |
| `ghost_employee` | active pay + zero activity (no attendance/leave movements) | `medium` | run id, entry id, activity query link |

> **Gherkin: ghost employee flagged.** Given an employee with active pay and
> zero recorded activity is seeded, when the anomaly scan runs, a `ghost_employee`
> signal is logged at **medium** severity with evidence links.

### 7.2 Lifecycle

`open → acknowledged | dismissed | resolved`. Acknowledge records
`acknowledged_by`/`acknowledged_at` for audit. Auto-close after 30 days.

---

## 8. Feature 4 — Compliance engine v1

**Location:** `services/core/src/core/features/ai_hr/`; rows in
`ai_compliance_checks` from the v1 `rule_pack.py`.

### 8.1 Rule pack v1

| Check | Signal source | Severity |
|-------|---------------|----------|
| `document_expiry` | `erp_employee_documents` where `doc_type` in (`work_permit`,`visa`,`passport`,`national_id`) and `expiry_date` is within 30 days or past | `high` (past) / `medium` (30 days) |
| `training_overdue` | required `certification` document missing **or** expired (`erp_employee_documents`) | `medium` |
| `contract_missing_field` | existing employee fields missing (`email`, `department_id`, `job_title`, `phone`) | `low` |

Each check carries `severity`, `owner_rule` routing, and `evidence JSONB`.
`owner_rule` names the routing owner key (e.g. `hr_admin`, `compliance_officer`)
for owner assignment.

---

## 9. Feature 5 — HR Copilot agent

**Location:** `services/ai-agent/src/ai_agent/features/hr_copilot/`. Registered
in `agent_registry` (the SKY-59 table) as
`{name: "hr_copilot", module: "ai_agent.features.hr_copilot.engine", enabled: true}`.

**Tool surface (deliberately narrow):**
- **Aggregate HR reads** (the L1 endpoints' results only) — never individual rows.
- **Draft leave-policy answers via RAG** over `erp_leave_policies` (tenant leave
  policy documents).

**Guardrails:**
- **Refuses PII / individual queries beyond caller permission.** Permission is
  resolved **server-side**; the Copilot never queries individual data for a
  caller lacking `erp.hr.ai.individual`, and never emits individual data into a
  prompt. All exchanges pass through the redaction gate.
- Aggregate-only reads return L1 shapes; an out-of-scope request returns a
  refusal rather than a downgraded individual leak.

**Core proxy:** `POST /api/v1/ai/hr/copilot/chat` requiring `erp.ai.invoke` +
`erp.hr.ai.copilot`, forwarding to ai-agent (same pattern as the inventory AI
proxy).

---

## 10. Security architecture

- **Authentication/authorization:** JWT + DB-resolved `require_permission` at
  the core edge before any proxy/forward; `erp.ai.invoke` + the relevant
  `erp.hr.ai.*` key.
- **Data isolation:** RLS on every new tenant-scoped table; repository-layer
  `tenant_id` filter as defense in depth.
- **PII:** redaction gate on every outbound LLM payload; fails closed; corpus
  tested incl. mixed-language text.
- **No individual data in prompts without L2 permission, verified
  server-side** (guardrail, §9).
- **Audit:** every score view / acknowledge / anomaly / compliance finding /
  Copilot exchange audited via `AuditService`.
- **Rate limiting:** existing per-user/per-tenant limiter applies to Copilot
  chat and AI endpoints.

---

## 11. Database design

Conventions: `tenant_id` (composite partial PK), `id UUID` PK, `created_at`
(and `updated_at` where mutable), RLS enabled + tenant policy, composite FKs to
`erp_employees`/`erp_payroll_runs`. AI tables use the `ai_` prefix.

**`erp_employee_documents`** (enables document/training rules)
- `employee_id` (composite FK), `doc_type` (**enum `erp_document_type`**:
  `work_permit, visa, national_id, passport, contract, certification, medical, other`),
  `expiry_date DATE NULL`, `is_required BOOLEAN`, `status`.

**`ai_hr_attrition_scores`**
- `employee_id` (composite FK), `department_id` (denormalized for L1 grouping),
  `score NUMERIC(5,4)`, `risk_band` (`low|medium|high`), `confidence NUMERIC(3,2)`,
  `factors JSONB` (top-3), `model_version TEXT`, `generated_at`.
- idx `(tenant_id, department_id, risk_band)`, `(tenant_id, generated_at)`.

**`ai_payroll_anomaly_log`**
- `anomaly_type` (`net_pay_delta|duplicate_account|ghost_employee`),
  `severity` (`low|medium|high|critical`), `run_id`/`employee_id` (composite FK,
  nullable), `evidence JSONB`, `status`
  (`open|acknowledged|dismissed|resolved`), `acknowledged_by`, `acknowledged_at`,
  `created_at`.

**`ai_compliance_checks`**
- `check_type` (`document_expiry|training_overdue|contract_missing_field`),
  `severity`, `owner_rule TEXT`, `owner_user_id` (nullable), `employee_id`
  (nullable), `status` (`open|acknowledged|resolved`), `evidence JSONB`,
  `created_at`.

**Migration chain:** core `0020_hr_ai_tables` off `0019_leave_type_rework`;
ai-agent `0002_hr_copilot` off `0001_ai_foundation_tables` (seeds the
`agent_registry` row). The HR-AI-002 wave-2 additions (HR-AI-002, Commit 1-5):
core `0022_hr_ai_wave2` creates `ai_hr_quality_scores`, `ai_hr_utilization_alerts`,
`ai_hr_leave_anomalies`, `ai_hr_leave_suggestions` and `hr_eval_runs`; core
`0023_hr_ai_eval_permission` seeds the `erp.hr.ai.eval` catalog key.

---

## 12. Model eval harness (HR-AI-002 / SKY-72)

**Location:** `services/ai-agent/src/ai_agent/eval/` + CLI command
`ai-agent eval-hr-models`; recording endpoint in core
`POST /api/v1/ai/hr/eval-runs`.

The harness is the model-quality check for the deterministic HR models: it runs
each labeled seed set from
`services/ai-agent/tests/eval/hr_models.yaml` through the **same scorer the
runtime uses** and computes per-metric precision. Two model kinds are graded:

- **attrition** (`attrition_precision`): the bundled GBC model via
  `score_employee` incl. its abstention rule.
- **anomaly** (`anomaly_precision`): the leave rules engine ran by core's
  `ai_hr_leave_anomalies` inbox — `skyrict_common.ai_hr_rules.
  detect_leave_pattern_anomalies` (the literal deployed code, imported from the
  workspace `skyrict-common` lib). Feature/request vectors in `hr_models.yaml`
  pin `today` and the 2026 holiday calendar, so runs are reproducible.

It is non-LLM and reproducible (bundled fixed-seed model + stable seed sets).
Seed rows carry feature arrays + labels only — never employee PII.

**Warn-not-fail contract:** precision below the documented `0.70` minimum
prints a `WARN` line (exit code 0) — an eval regression is an operator alert,
not a hard deploy gate. For `anomaly_precision` the report also records recall
(TP/(TP+FN)) in `details`; the anomaly seed mix is two recall probes (the
`short_notice_monday_friday` and `pre_holiday_spike` patterns MUST fire) and
two near-miss guards (the same patterns MUST NOT fire just outside their
window/threshold). Results are recorded append-only in core's
`hr_eval_runs` (`metric`, `precision`, `considered`, `threshold`,
`met_threshold`, `details JSONB`; RLS tenant-scoped; index
`(tenant_id, model_name, generated_at)`) via the core API, gated by the seeded
`erp.hr.ai.eval` permission (owner wildcard passes). Precision/threshold
bounds are re-validated at the core edge.

**Operate:**
```
uv run --directory services/ai-agent ai-agent eval-hr-models \
  --core-url http://localhost:8000 --token <jwt> --tenant-slug <slug>
```
Drop `--core-url/--token/--tenant-slug` for a local-only dry-run
(`--dry-run` forces the same).

---

## 13. HR-AI wave 2 — Leave anomaly inbox, calendar-aware suggestions & pattern data

Wave 2 turns the HR leave records into two low-fiend, deterministic surfaces:
a **leave-pattern anomaly inbox** (managers see teams abusing leave patterns)
and **calendar-aware use-it-or-lose-it suggestions** (the portal tells an
employee *when* a window is actually sensible before it forfeits). Both are fed
by **pattern data** — org/department public holidays and leave blackouts.

**Locations:** core feature `core/features/ai_hr/` (anomaly, suggestion,
pattern-data modules), shared pure engine `libs/skyrict-common/skyrict_common/
ai_hr_rules.py`, migrations `0022_hr_ai_wave2` (anomaly + suggestion tables),
`0023_hr_ai_eval_permission`, `0024_hr_ai_pattern_data`.

### 13.1 Leave anomaly inbox (`ai_hr_leave_anomalies`)

Detection runs in pure code (`skyrict_common.ai_hr_rules
.detect_leave_pattern_anomalies`) — the SAME code the eval harness grades, so
what the inbox flags is exactly what the `anomaly_precision` metric measures.
Every rule is gated: teams with fewer than **4 active members abstain**, and
the median-comparison rules need the team median to be measurable (>= 1 day).

| Anomaly type | Detection | Severity |
|--------------|-----------|----------|
| `leave_overuse` | trailing leave days >= 3x team median | ratio bands: >=5 critical, >=4 high, else medium |
| `frequent_absence` | request count >= 3x team median | ratio bands as above |
| `short_notice_monday_friday` | a Mon/Fri-touching block filed < 14 days ahead AND >= 3x team median days | high if filed <= 3 days ahead, else medium |
| `pre_holiday_spike` | span within 2 days of an org/department holiday AND >= 3x team median days | high if it overlaps the holiday date, else medium |

**Inputs / lifecycle:** approved + pending requests in the trailing 90 days,
holidays from `ai_hr_public_holidays` (org-wide + department-scoped), all
resolved as of run time. Findings are persisted append-only with the 7-day
stale refresh and the open/acknowledged/dismissed/resolved lifecycle from wave
1; narratives explain the evidence (ratio, median, advance, holiday).

### 13.2 Calendar-aware leave suggestions (`ai_hr_leave_suggestions`)

Suggestions are generated only for employees with a **forfeit-risk utilization
alert** and are prefill-only (the employee still files the request; nothing is
auto-booked). Wave 2 replaced the fixed "last N days" block with a
**calendar-aware planner** (`AiHrSuggestionRepository._plan_best_block`):

1. Candidate 14-day windows run from today to the year end (respecting the
   employee's annual balance for the planned chunk).
2. Windows that overlap the employee's **own** approved/pending requests, an
   **org-wide blackout**, or their **department's blackout** are excluded.
3. Remaining windows are ranked by **(a) lowest teammate leave overlap**, then
   **(b) alignment with a public holiday within 2 days** (same adjacency the
   anomaly engine uses), then **(c) latest start** (recency).
4. If every window is blocked, the suggestion **falls back to the loss-mitigation
   window with an explicit conflict reason** (never silently books into a
   blackout). Suggested block = min(balance, 14, days until year end).

The reason list surfaces the ranking: teammate overlap count for the chosen
window, the aligned holiday name when present, and blackout clearance.

### 13.3 Pattern data (`public holidays` + `leave blackouts`)

`ai_hr_public_holidays` (unique per tenant+department+date; org-wide when
department is NULL) and `ai_hr_leave_blackout_periods` (enforced end >= start)
are managed via CRUD endpoints under `/api/v1/ai/hr/pattern-data/*`, gated
read by `erp.hr.read` and write by `erp.hr.write`. Seed carries a Malaysia
2026 holiday calendar and a Finance year-end-close blackout
(2026-12-20..12-31) so the calendar-aware suggestion is demoable out of the
box.

### 13.4 Coverage matrix (Gherkin scenarios)

**HR-AI-002 wave-2 delivery — shipped:**

| Ticket scope | Status | Where |
|--------------|--------|-------|
| 8.1.3 data quality scoring + org KPI + weekly recalc | shipped | `core/features/ai_hr/quality*`, quality panel, `POST /quality/refresh`, `.github/workflows/weekly-quality-recalc.yml` |
| 8.1.4 balance utilization alerts (forfeit + negative accrual) | shipped | `core/features/ai_hr/utilization*`, seeded 18/55 fixture, severity bands §13.6 |
| 8.2.1 leave pattern anomaly detection + inbox | shipped | `skyrict_common.ai_hr_rules`, table §13.1, team-size gate, eval `anomaly_precision` |
| 8.2.4 smart leave suggestions (prefill-only) | shipped | calendar-aware `_plan_best_block`, chips in leave-portal + log-leave-dialog |
| Eval harness + nightly runner (`hr_eval_runs`) | shipped | §12, `tests/eval/hr_models.yaml`, `.github/workflows/nightly-hr-eval.yml` |

| Scenario (feature file) | Engine | Covered by |
|-------------------------|--------|------------|
| short-notice Monday/Friday request, filed < 14 days ahead, >= 3x median | rules | lib test + eval case 1 (`anomaly_precision`) |
| pre-holiday request within 2 days of a public holiday, >= 3x median | rules | lib test + eval case 2 + seeded National Day |
| **near-miss: holiday 3+ days away must NOT fire** | rules | eval case 3 |
| **near-miss: filed 14+ days ahead must NOT fire** | rules | eval case 4 |
| thin team (< 4 active) abstains entirely | rules | lib test `test_team_size_gate_abstains_for_three_members` |
| suggestion: empty load/blackouts -> latest loss-mitigation window (Dec 18..31) | planner | unit `test_plan_best_block_defaults_to_latest_calm_window` |
| suggestion: department blackout pulls the window ahead | planner | unit `test_plan_best_block_avoids_department_blackout` |
| suggestion: picks lowest teammate-overlap window | planner | unit `test_plan_best_block_prefers_lowest_team_load` |
| suggestion: ties break toward holiday alignment | planner | unit `test_plan_best_block_breaks_load_ties_toward_holiday_alignment` |
| suggestion: own-request windows skipped | planner | unit `test_plan_best_block_skips_windows_blocked_by_own_requests` |
| suggestion: fully blacked-out -> forfeit window + conflict reason | planner | unit `test_plan_best_block_falls_back_to_forfeit_window_when_fully_blacked_out` |

> **Demo seed — live vs pre-seeded.** The `core seed-demo --force` scenario
> mix deliberately splits determinism from end-to-end "first read" freshness:
>
> | Sample | Provisioning | Why |
> |--------|--------------|-----|
> | `leave_overuse` (Grace, EMP-0007) | **live-computed** — anomaly table left empty after force-reseed, so the portal/admin's first read runs the scan and materializes the finding | demo shows the compute path, not just a table read |
> | `short_notice_monday_friday` (EMP-0007) | **live-computed** — approved block filed+starting today (advance 0), ending on the next Friday (Fri fringe), 7 days vs 2.0 team median | end-on-Friday is the only construction that fires for *any* seed weekday (proven over all 7) |
> | `pre_holiday_spike` (EMP-0007) | **live-computed** — the 2026 demo calendar seeds National Day (08-31) inside the block (distance 0 -> high) | high requires overlap; a non-overlapping holiday can only reach medium |
> | forfeit utilization alert (emp 1, 18/55) | **pre-seeded** fixture row (`ai_hr_utilization_alerts`, `created_at=now-0.5d` so the 1-day refresh keeps it fresh) | the forfeit scan only fires when < 60 days remain — mid-year (124 left on 08-29) it physically cannot fire live |
> | thin-team abstention | **unit-tested only** | `>= 4` active members are required to scan; seed teams are all >= 4 so the live demo cannot produce it |
>
> Freshness mechanics: anomaly/quality feeds refresh after 7 days,
> utilization after 1 day (`max(created_at)` + elapsed >= refresh window).
> The quality feed also has an explicit **weekly recalc** — the ops cron in
> §13.5 calls `POST /api/v1/ai/hr/quality/refresh` (force re-score; L1
> maintenance response) every Sunday 03:17 UTC so the panel always has a
> current run regardless of TTL.
> The team-size gate and the four rule near-miss cases are pinned by the lib
> tests and the `anomaly_precision` eval seed (rows above).

### 13.5 Nightly / CI model-quality hook

The eval harness is deterministic and cheap; wire the same command to a
nightly job so a rules/model regression is caught within a day and the metric
history lands in `hr_eval_runs`. This repository ships the job at
`.github/workflows/nightly-hr-eval.yml` — runs at **02:17 UTC** and on
`workflow_dispatch`, installs with `uv sync --all-packages --frozen`, then runs
`uv run --project services/ai-agent ai-agent eval-hr-models` with
`SKYRICT_CORE_URL` / `SKYRICT_CORE_TOKEN` / `SKYRICT_TENANT_SLUG` supplied from
Actions secrets.

The quality feed's **weekly recalc** ships as `.github/workflows/
weekly-quality-recalc.yml` — Sunday **03:17 UTC** + `workflow_dispatch`, a
dependency-free `curl` POST to `POST /api/v1/ai/hr/quality/refresh` reusing the
same three secrets. Local equivalent:

```
uv run --directory services/ai-agent ai-agent eval-hr-models --dry-run
```

Webhook alerting on a WARN line can fan out to the on-call channel (the metric
row is already persisted). Same pattern already powers the CI `ci-core.yml`
gates for ruff/mypy; this hook extends CI to model quality.

### 13.6 Audit reconciliation

Two accepted deviations from the ticket's literal wording (reasoned, tested,
and documented here so the DoD surface matches reality):

| Bulk-of-ticket wording | Delivered | Reason |
|------------------------|-----------|--------|
| data-quality scores over "company data incl. banking" | quality engine scores from **compensation** + **work-documents** proxies in this schema (no banking `erp_*` table exists) | proxies are the populated substitutes; contribution weights and issue codes are still per-rule and tested |
| use-it-or-lose-it forfeit "urgency" by time-to-forfeit | forfeit fires only within `FORFEIT_WINDOW_DAYS = 60` of year end, severity by **balance magnitude** (`>= 20` high, `>= 10` medium, else low) | a mid-year 18-days/55-remaining case satisfies the demo's *medium severity* intent without inventing a nonexistent near-year-end trigger |

The demo seed's forfeit fixture row literally materializes that second row
(balance 18, 55 remaining, medium). Everything else in §13.4 is either live
computed or unit-pinned as marked.

---

## 14. Test strategy

| Area | Coverage |
|------|----------|
| Redaction (unit) | corpus incl. Malay/English mixed — raw absent, tokens present; fails closed |
| Permission gate (integration) | L2 request w/o `individual` → 403 + L1 body |
| Ghost employee (integration) | active pay + zero activity → medium severity + evidence links |
| Anomalies (integration) | all three types on seed data with correct severity |
| Acknowledge (integration) | audited via `hr.ai.risk.acknowledged` |
| Aggregates (integration) | L1 shapes only; no employee identifiers in serialized body |
| RLS (integration) | new tables cross-tenant read filtered / write blocked |
| Eval harness (unit) | seed-set precision ≥ threshold on the bundled model; abstentions excluded; unknown model fails fast |
| Eval recording (integration) | migration round-trip includes 0022/0023/0024 + `hr_eval_runs` / `erp.hr.ai.eval` sentinels |
| Leave rule engine (unit) | `skyrict_common.ai_hr_rules` — 13 tests: each pattern fires, near-misses abstain, thin teams abstain, ratio severity bands |
| Anomaly eval (unit) | `anomaly_precision` seed (4 cases) = 1.0 precision/recall; missing-label case registers a recall miss |
| Leave anomaly inbox (unit) | 12 tests over all four types incl. the two wave-2 patterns at high severity |
| Suggestion planner (unit) | calendar-aware `_plan_best_block`: load/blackout/own-request windows, holiday ties, forfeit fallback; legacy `_plan_block` kept |
| Pattern data (integration) | round-trip sentinels 0024 + endpoint read/write via `erp.hr.read`/`erp.hr.write` |
