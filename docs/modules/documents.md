# M-DOC - Documents Module (SKY-87)

> **Status:** Implemented (core + ai-agent) / web UI (Task 7) - see build checklist §9.
> **Owner:** Abhinav
> **Dependencies:** identity service (JWT verification, permissions, tenant context), `services/core` (ERP spine), `services/ai-agent` (OCR + tagging + embeddings).

This document is the specification for the SKY-87 document management platform. It combines a **core** document authority (spine) in `services/core` with an **ai-agent** worker that extracts text, tags, and embeddings. The web workspace surfaces Documents under `apps/web`.

---

## 1. Overview

The documents module is the **central document authority (spine)** for the ERP: it stores files immutably, tracks version history, and co-ordinates AI enrichment. Two services collaborate:

- **Core (`services/core/src/core/features/documents`)** owns the document of record: `erp_documents` rows, immutable `erp_document_versions`, storage blobs, permissions, and the API surface. It is the single source of truth clients and other modules read from.
- **AI agent (`services/ai-agent/src/ai_agent/features/documents`)** consumes new documents (pulled via OCR callback/queue), extracts text (pypdf, python-docx, openpyxl, CSV, plain text) and image bytes, suggests tags via an LLM router, and writes embeddings to `ai_document_embeddings` for semantic search. It POSTs results back to core's OCR callback.

**The one idea to internalize:** a document has *two* stores. The **blob** (immutable bytes per version) lives in core's storage backend (local or S3). The **derived knowledge** (extracted text, tags, vector) lives in ai-agent's `ai_document_embeddings`. They are joined by `(tenant_id, document_id)` and reconciled only through the documented endpoints - never by poking the other's database.

**Consumers built in this phase:**
- **Web** (`apps/web`, Task 7): overview, list (with OCR-status/module filters), upload, detail with version history, download, confirm-AI-tags, delete, reindex.
- **ai-agent** (already done): OCR extraction + tagging + embeddings round-trip.

---

## 2. Scope

### 2.1 In scope
- Immutable document storage with checksum + version history (`erp_documents`, `erp_document_versions`).
- Upload, download, metadata patch, delete, list/detail with filters.
- **Entity linking** (`module_ref` ∈ `inventory|sales|crm|finance|hr|payroll`) with cross-module read guard.
- OCR dispatch to ai-agent on `POST /documents`; ai-agent returns extracted text + AI tag suggestions via the OCR callback.
- User-facing tag **confirmation** (`POST /documents/{id}/tags/confirm`) - ai-agent never overwrites confirmed tags.
- Embeddings for semantic search (`ai_document_embeddings`).
- Admin **reindex** to re-enqueue `failed` / force-rerun `ready`.

### 2.2 Out of scope
- Native viewers / annotation overlays (web streams the raw blob).
- Compliance retention policy engine (can be layered on version/checksum guarantees).
- Secure document sharing outside the workspace.

---

## 3. Data model (core spine)

Every `erp_*` table carries `tenant_id` (UUID, NOT NULL, indexed, RLS key) plus the shared base-mixin columns (`id` PK uuid4, `created_at`, `updated_at`).

### 3.1 `erp_documents` - the document of record
| Column | Type / Constraint | Why it exists |
|---|---|---|
| `tenant_id` | UUID, NOT NULL, indexed | Ownership + RLS key |
| `filename` | String, NOT NULL | Display name (never "a write to bytes") |
| `mime_type` | String, nullable | Original content type |
| `size_bytes` | BigInteger, NOT NULL | Blob byte length |
| `checksum_sha256` | String, NOT NULL | Content hash - dedupe + integrity |
| `storage_backend` | String, NOT NULL | `local` \| `s3` |
| `storage_key` | String, NOT NULL | Object key within the backend |
| `module_ref` | String(32), nullable | Optional link (`""` = general) |
| `entity_type` / `entity_id` | String / UUID, nullable | Optional link to a domain entity |
| `tags` | ARRAY(String), NOT NULL default `{}` | Authoritative tags |
| `ai_tags` | ARRAY(String), NOT NULL default `{}` | Suggested tags from ai-agent |
| `tags_confirmed` | Boolean, NOT NULL default `false` | Locks `ai_tags` as authoritative |
| `ocr_status` | Enum, NOT NULL default `pending` | `pending \| processing \| ready \| failed` |
| `ocr_error` | String, nullable | Reason when `failed` |
| `extracted_text` | Text, nullable | Text splice from ai-agent |
| `version_count` | Integer, NOT NULL default 1 | Mantra: latest version is `erp_document_versions[version_count]` |
| `created_by` | UUID, nullable | Actor who uploaded |

### 3.2 `erp_document_versions` - immutable history
| Column | Type / Constraint | Why it exists |
|---|---|---|
| `document_id` | UUID, NOT NULL, FK → `erp_documents.id` | Parent |
| `version_number` | Integer, NOT NULL, `>= 1` | Monotonic per document (`UNIQUE(document_id, version_number)`) |
| `filename`, `mime_type`, `size_bytes`, `checksum_sha256`, `storage_backend`, `storage_key` | as above | **Per-version** blob pointer + integrity |
| `created_by` | UUID, nullable | Actor who added this version |

**Rule: versions are immutable.** No UPDATE, no DELETE on a version; adding a new blob creates a *new* version and bumps `version_count`. The blob pointer (`storage_key`) is never rewritten.

### 3.3 `ai_document_embeddings` (ai-agent side)
| Column | Type / Constraint | Why it exists |
|---|---|---|
| `tenant_id` | UUID, NOT NULL, RLS key / ownership | Scopes vectors to the tenant |
| `document_id` | UUID, NOT NULL | Joins to core's `erp_documents.id` (opaque) |
| `embedding` | `pgvector `Vector(768), nullable | Semantic vector from `DOCUMENT_EMBEDDING_MODEL` |
| `status` | String/`processed`-ish | Worker state (`pending/processed/failed`) |

---

## 4. Business rules (core)

All rules are enforced in `features/documents/service.py` inside a single DB transaction.

1. **Immutable blob + version bump.** Upload creates document (v1) and stores bytes first; a new upload via `POST /documents/{id}/versions` stores a new immutably-keyed blob and appends vN+1. Never mutate bytes in place.
2. **Checksum integrity.** `checksum_sha256` is computed at upload; download reads the stored blob and serves the same header contract. (Optional side-channel verify.)
3. **Entity-link read mirror.** A document linked to `(module_ref, entity_id)` is only *readable* if the caller also holds the owning module's read key (e.g. `erp.inventory.read`) - enforced by `get_entity_link_guard` before serving bytes/detail/versions.
4. **OCR lifecycle.** Upload → `pending` → (dispatch) → `processing` → `ready` (with `extracted_text` + `ai_tags`) or `failed` (with `ocr_error`). `ocr_status` transitions are applied only by the ai-agent callback (`/ocr/result`) or admin reindex.
5. **Tag confirmation wins.** Letting ai-agent's suggestions overwrite confirmed tags would lose editorial control. Confirm endpoint sets `tags=ai_tags` and `tags_confirmed=true`; reindexed/refetched suggestions never clobber a confirmed set.
6. **Delete is a hard delete** (blob + row + version cascade) - gated by `erp.documents.delete`.

---

## 5. Architecture

### 5.1 Core feature package (`services/core/src/core/features/documents`)
```
__init__.py
ports.py       # DocumentRepositoryPort, DocumentStoragePort (+ _UNSET sentinel)
repository.py  # SQLAlchemy persistence for erp_documents / erp_document_versions
storage.py     # blob access (local or s3)
service.py     # upload/download/delete/tags/versions/reindex business logic
schemas.py     # Pydantic request/response shapes
router.py      # FastAPI router + permission deps + /documents endpoints
events/dispatch.py  # posts {document_id} to ai-agent's /ai/documents/process
```

### 5.2 ai-agent feature package (`services/ai-agent/src/ai_agent/features/documents`)
```
__init__.py
schemas.py
processor.py  # text extraction (pypdf / python-docx / openpyxl / csv / plain) + image passthrough
gateway.py    # HttpDocumentGateway - GET core /documents/{id}/download, POST /ocr/result
service.py    # orchestrates extraction, LLM tag suggestion, embedding write
```
`service.py` uses a `DocumentEmbeddingStorePort` Protocol (no direct `db` import, so import-linter stays clean) and guards `LlmRouter | None` for unconfigured providers.

### 5.3 Web (Task 7)
- BFF proxy `apps/web/src/app/api/v1/[...path]/route.ts` now routes segment `documents` → `core`.
- Client `apps/web/src/lib/api/documents-api.ts` (envelope/camelCase mappers).
- Pages under `apps/web/src/app/dashboard/erp/documents/`.
- Sidebar `erpNavGroups` "Operations" gains **Documents** (`erp.documents.read`); overview gains a quick-link card.

---

## 6. Auth & permissions (3 new keys)

Added to identity's `permissions` catalog (migration using `ON CONFLICT (key) DO NOTHING`) and mirrored in core's `core/permissions.py`:

| Key | Grants |
|---|---|
| `erp.documents.read` | list, detail, download, versions |
| `erp.documents.write` | upload, metadata patch, add version, tag confirm, reindex |
| `erp.documents.delete` | hard delete |

Entity-linked reads additionally require the owning module's read key (rule 3).

**ai-agent m2m:** core's OCR callback `POST /documents/{id}/ocr/result` is authenticated by the shared `DOCUMENT_SYNC_TOKEN` (matches core's `CORE_AI_SYNC_TOKEN`) via HMAC-safe compare and fails closed (503) when unset - mirroring the existing `erp.inventory` ingest pattern.

---

## 7. API surface (core, prefix `/api/v1/documents`)

All require a valid access JWT + tenant context; check the listed permission.

| # | Method & Path | Permission | Notes |
|---|---|---|---|
| 1 | `GET /documents` | `read` | `?page=&page_size=&ocr_status=&module_ref=&entity_type=&entity_id=&tags=` → `ListResponse[DocumentResponse]` |
| 2 | `POST /documents` | `write` | multipart `file` + optional `module_ref/entity_type/entity_id/tags/mime_type`; **dispatches OCR** |
| 3 | `GET /documents/{id}` | `read` | latest version embedded |
| 4 | `PATCH /documents/{id}` | `write` | patch link + tags + filename |
| 5 | `DELETE /documents/{id}` | `delete` | hard delete (blob + row + cascade) |
| 6 | `GET /documents/{id}/download` | `read` | streams current bytes (audited) |
| 7 | `POST /documents/{id}/versions` | `write` | multipart `file` → new immutable version |
| 8 | `GET /documents/{id}/versions` | `read` | newest-first history |
| 9 | `POST /documents/{id}/tags/confirm` | `write` | body `{ai_tags}`; sets `tags=ai_tags`, `tags_confirmed=true` |
| 10 | `POST /documents/{id}/ocr/result` | m2m (`DOCUMENT_SYNC_TOKEN`) | ai-agent callback: `{ocr_status, extracted_text, ai_tags, error_message}` |
| 11 | `POST /documents/reindex` | `write` | body `{ocr_status}` (`failed`\|`ready`) - re-enqueue |

`DocumentResponse` fields (JSON snake_case, camelCase in web): `id, tenant_id, filename, mime_type, size_bytes, checksum_sha256, storage_backend, storage_key, module_ref, entity_type, entity_id, tags, ocr_status, ocr_error, extracted_text, ai_tags, tags_confirmed, version_count, created_by, created_at, updated_at, latest_version`.

---

## 8. Configuration

| Env var | Service | Purpose |
|---|---|---|
| `CORE_AI_SYNC_TOKEN` | core | Shared secret core dispatches on OCR / must match `DOCUMENT_SYNC_TOKEN` |
| `AI_DOCUMENT_SYNC_TOKEN` (ai-agent `DOCUMENT_SYNC_TOKEN`) | ai-agent | m2m bearer the ai-agent presents on `/ocr/result` |
| `CORE_AI_AGENT_URL` | core | Base of ai-agent (`http://localhost:8002`) |
| `CORE_AI_AGENT_TIMEOUT_SECONDS` | core | OCR dispatch timeout |
| `CORE_DOCUMENT_URL` | ai-agent | Base of core the gateway pulls download from |
| `CORE_DOCUMENT_TIMEOUT_SECONDS` | ai-agent | Gateway timeout |
| `DOCUMENT_EMBEDDING_MODEL` | ai-agent | Embedding model id (dimension 768) |
| `DOCS_STORAGE_BACKEND` / `DOCS_STORAGE_LOCAL_DIR` / `DOCS_S3_*` | core | blob backend (`local` default; S3 optional) |
| `DOCS_MAX_UPLOAD_BYTES` / `DOCS_VIRUS_SCAN_HOOK_URL` | core | upload cap + optional scan hook |

Add to root `.env.example` and `apps/web/.env.example` as documented in §9.

---

## 9. Build checklist / current status

- [x] Core feature package, router, OCR callback, dispatch, models/migration
- [x] ai-agent processor/gateway/service, `ai_document_embeddings`, CLI `documents reindex`
- [x] 3 permission keys (`erp.documents.read/write/delete`) in core + identity catalog
- [x] Web BFF `documents` segment routing (Task 6)
- [x] Web client `documents-api.ts` (Task 6)
- [x] Web pages + sidebar + quick-link (Task 7)
- [x] Docs + `.env.example` (Task 8)
- [x] Final gates: web tsc/eslint clean (0 errors; 4 pre-existing warnings), `next build` OK, vitest 135/135, ai-agent ruff/mypy clean, ai-agent 798/798, core 893/893, identity 548/548

---

## 10. Out-of-package notes

- Core `documents/router.py` imports `_UNSET` from `ports` (may be unused - kept for port symmetry; not flagged by gates).
- ai-agent unit suite: `tests/unit/features/test_documents_service.py` (5 cases: success+callback, no-text, no-LLM skip, gateway-failure, llm-failure).
