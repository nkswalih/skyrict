/**
 * Documents API client (SKY-87).
 *
 * All calls go through the same-origin /api/v1/* BFF proxy, which derives the
 * tenant slug from the Host header and forwards the in-memory access token (see
 * lib/api/http.ts). The core module is under `/documents` and returns the
 * shared envelope: lists are `{ data, meta }`, mutations wrap `data` in a
 * `message`. Uploads/version-adds are multipart `FormData`. Server-side
 * permissions gate each call: `erp.documents.read` (list/detail/download),
 * `.write` (upload/meta/tag/version), `.delete` (hard delete).
 *
 * A document may be linked to a domain entity (module_ref ∈ inventory, sales,
 * crm, finance, hr, payroll) - entity-linked reads additionally require the
 * owning module's read key (e.g. `erp.inventory.read`), enforced in core.
 */

import {
    apiDelete,
    apiFetch,
    apiFetchEnvelope,
    apiFetchRaw,
    apiPatch,
    apiPost,
    fetchWithSession,
} from "@/lib/api/http";

export interface PaginationMeta {
    total: number;
    page: number;
    pageSize: number;
    totalPages: number;
}

export interface ListResponse<T> {
    data: T[];
    meta: PaginationMeta;
}

export type OcrStatus = "pending" | "processing" | "ready" | "failed";

export interface DocumentVersion {
    id: string;
    documentId: string;
    versionNumber: number;
    filename: string;
    mimeType: string;
    sizeBytes: number;
    checksumSha256: string;
    storageBackend: string;
    storageKey: string;
    createdBy: string | null;
    createdAt: string;
    downloadUrl: string | null;
}

export interface Document {
    id: string;
    tenantId: string;
    filename: string;
    mimeType: string;
    sizeBytes: number;
    checksumSha256: string;
    storageBackend: string;
    storageKey: string;
    moduleRef: string | null;
    entityType: string | null;
    entityId: string | null;
    tags: string[];
    ocrStatus: OcrStatus;
    ocrError: string | null;
    extractedText: string | null;
    aiTags: string[];
    tagsConfirmed: boolean;
    versionCount: number;
    createdBy: string | null;
    createdAt: string;
    updatedAt: string;
    latestVersion: DocumentVersion | null;
}

export interface UploadDocumentInput {
    file: File;
    /** Optional domain link (module_ref ∈ inventory/sales/crm/finance/hr/payroll). */
    moduleRef?: string;
    entityType?: string;
    entityId?: string;
    tags?: string[];
}

export interface UpdateDocumentMetaInput {
    moduleRef?: string;
    entityType?: string | null;
    entityId?: string | null;
    tags?: string[];
    filename?: string;
}

export interface ListDocumentsFilters {
    page?: number;
    pageSize?: number;
    ocrStatus?: OcrStatus;
    moduleRef?: string;
}

// ---------------------------------------------------------------------------
// Payload shapes (snake_case, as served by core)
// ---------------------------------------------------------------------------

interface MetaPayload {
    total?: unknown;
    page?: unknown;
    page_size?: unknown;
    total_pages?: unknown;
}

interface ListPayload {
    data?: unknown;
    meta?: unknown;
}

interface DocumentVersionPayload {
    id?: unknown;
    document_id?: unknown;
    version_number?: unknown;
    filename?: unknown;
    mime_type?: unknown;
    size_bytes?: unknown;
    checksum_sha256?: unknown;
    storage_backend?: unknown;
    storage_key?: unknown;
    created_by?: unknown;
    created_at?: unknown;
    download_url?: unknown;
}

interface DocumentPayload {
    id?: unknown;
    tenant_id?: unknown;
    filename?: unknown;
    mime_type?: unknown;
    size_bytes?: unknown;
    checksum_sha256?: unknown;
    storage_backend?: unknown;
    storage_key?: unknown;
    module_ref?: unknown;
    entity_type?: unknown;
    entity_id?: unknown;
    tags?: unknown;
    ocr_status?: unknown;
    ocr_error?: unknown;
    extracted_text?: unknown;
    ai_tags?: unknown;
    tags_confirmed?: unknown;
    version_count?: unknown;
    created_by?: unknown;
    created_at?: unknown;
    updated_at?: unknown;
    latest_version?: unknown;
}

// ---------------------------------------------------------------------------
// Mappers
// ---------------------------------------------------------------------------

function toStrings(value: unknown): string[] {
    return Array.isArray(value) ? value.map((item) => String(item)) : [];
}

function toStringOrNull(value: unknown): string | null {
    return typeof value === "string" && value ? value : null;
}

function mapVersion(raw: DocumentVersionPayload): DocumentVersion {
    return {
        id: String(raw.id ?? ""),
        documentId: String(raw.document_id ?? ""),
        versionNumber: Number(raw.version_number ?? 0),
        filename: String(raw.filename ?? ""),
        mimeType: String(raw.mime_type ?? "application/octet-stream"),
        sizeBytes: Number(raw.size_bytes ?? 0),
        checksumSha256: String(raw.checksum_sha256 ?? ""),
        storageBackend: String(raw.storage_backend ?? "local"),
        storageKey: String(raw.storage_key ?? ""),
        createdBy: toStringOrNull(raw.created_by),
        createdAt: String(raw.created_at ?? ""),
        downloadUrl: toStringOrNull(raw.download_url),
    };
}

function mapDocument(raw: DocumentPayload): Document {
    return {
        id: String(raw.id ?? ""),
        tenantId: String(raw.tenant_id ?? ""),
        filename: String(raw.filename ?? ""),
        mimeType: String(raw.mime_type ?? "application/octet-stream"),
        sizeBytes: Number(raw.size_bytes ?? 0),
        checksumSha256: String(raw.checksum_sha256 ?? ""),
        storageBackend: String(raw.storage_backend ?? "local"),
        storageKey: String(raw.storage_key ?? ""),
        moduleRef: toStringOrNull(raw.module_ref),
        entityType: toStringOrNull(raw.entity_type),
        entityId: toStringOrNull(raw.entity_id),
        tags: toStrings(raw.tags),
        ocrStatus: (toStringOrNull(raw.ocr_status) as OcrStatus) ?? "pending",
        ocrError: toStringOrNull(raw.ocr_error),
        extractedText: toStringOrNull(raw.extracted_text),
        aiTags: toStrings(raw.ai_tags),
        tagsConfirmed: raw.tags_confirmed === true,
        versionCount: Number(raw.version_count ?? 1),
        createdBy: toStringOrNull(raw.created_by),
        createdAt: String(raw.created_at ?? ""),
        updatedAt: String(raw.updated_at ?? ""),
        latestVersion: raw.latest_version
            ? mapVersion(raw.latest_version as DocumentVersionPayload)
            : null,
    };
}

function mapMeta(raw: MetaPayload | undefined | null): PaginationMeta {
    return {
        total: Number(raw?.total ?? 0),
        page: Number(raw?.page ?? 1),
        pageSize: Number(raw?.page_size ?? 0),
        totalPages: Number(raw?.total_pages ?? 0),
    };
}

function mapList<T, R>(
    raw: ListPayload | null | undefined,
    mapper: (item: T) => R,
): ListResponse<R> {
    const items = Array.isArray(raw?.data) ? raw.data.map(mapper) : [];
    return { data: items, meta: mapMeta(raw?.meta as MetaPayload | undefined) };
}

function buildListParams(
    options: { page?: number; pageSize?: number },
    extra?: Record<string, string | undefined>,
): string {
    const params = new URLSearchParams();
    params.set("page", String(options.page ?? 1));
    params.set("page_size", String(options.pageSize ?? 20));
    if (extra) {
        for (const [key, value] of Object.entries(extra)) {
            if (value) params.set(key, value);
        }
    }
    return params.toString();
}

// ---------------------------------------------------------------------------
// Documents
// ---------------------------------------------------------------------------

/** List documents with optional OCR-status / module filters (erp.documents.read). */
export async function listDocuments(
    options: ListDocumentsFilters = {},
    fetchOptions: RequestInit = {},
): Promise<ListResponse<Document>> {
    const query = buildListParams(options, {
        ocr_status: options.ocrStatus,
        module_ref: options.moduleRef,
    });
    const raw = await apiFetchEnvelope<ListPayload>(
        `/api/v1/documents?${query}`,
        fetchOptions,
    );
    return mapList(raw, mapDocument);
}

/** Fetch one document with its latest version embedded (erp.documents.read). */
export async function getDocument(
    id: string,
    fetchOptions: RequestInit = {},
): Promise<Document | null> {
    const raw = await apiFetch<DocumentPayload | null>(
        `/api/v1/documents/${id}`,
        fetchOptions,
    );
    return raw ? mapDocument(raw) : null;
}

/** Upload a document (multipart). Requires erp.documents.write. */
export async function uploadDocument(
    input: UploadDocumentInput,
): Promise<Document | null> {
    const form = new FormData();
    form.append("file", input.file);
    if (input.moduleRef) form.append("module_ref", input.moduleRef);
    if (input.entityType) form.append("entity_type", input.entityType);
    if (input.entityId) form.append("entity_id", input.entityId);
    if (input.tags && input.tags.length > 0) form.append("tags", input.tags.join(","));

    const response = await fetchWithSession("/api/v1/documents", {
        method: "POST",
        body: form,
    });
    if (!response.ok) {
        throw new Error("Upload failed. Please try again.");
    }
    const payload = (await response.json().catch(() => ({}))) as {
        data?: DocumentPayload;
    };
    return payload.data ? mapDocument(payload.data) : null;
}

/** Patch link + tags + display filename (version history untouched). erp.documents.write. */
export async function updateDocumentMeta(
    id: string,
    input: UpdateDocumentMetaInput,
): Promise<Document | null> {
    const body: Record<string, unknown> = {};
    if (input.moduleRef !== undefined) body.module_ref = input.moduleRef;
    if (input.entityType !== undefined)
        body.entity_type = input.entityType === null ? null : input.entityType;
    if (input.entityId !== undefined)
        body.entity_id = input.entityId === null ? null : input.entityId;
    if (input.tags !== undefined) body.tags = input.tags;
    if (input.filename !== undefined) body.filename = input.filename;

    const raw = await apiPatch<DocumentPayload | null>(
        `/api/v1/documents/${id}`,
        body,
    );
    return raw ? mapDocument(raw) : null;
}

/** Hard-delete a document (blob + row + version cascade). Requires erp.documents.delete. */
export async function deleteDocument(id: string): Promise<Document | null> {
    const raw = await apiDelete<DocumentPayload | null>(`/api/v1/documents/${id}`);
    return raw ? mapDocument(raw) : null;
}

/** Confirm AI-suggested tags as authoritative (idempotent). erp.documents.write. */
export async function confirmDocumentTags(
    id: string,
    aiTags: string[],
): Promise<Document | null> {
    const raw = await apiPost<DocumentPayload | null>(
        `/api/v1/documents/${id}/tags/confirm`,
        { ai_tags: aiTags },
    );
    return raw ? mapDocument(raw) : null;
}

/** List the immutable version history of a document (erp.documents.read). */
export async function listDocumentVersions(
    id: string,
): Promise<DocumentVersion[]> {
    const raw = await apiFetchEnvelope<DocumentVersionPayload[]>(
        `/api/v1/documents/${id}/versions`,
    );
    const items = raw?.data ?? [];
    return items.map((item) => mapVersion(item));
}

// ---------------------------------------------------------------------------
// Versions / download
// ---------------------------------------------------------------------------

/**
 * Stream the current byte stream of a document.
 *
 * The BFF returns the raw stream as an octet-stream response; we read the blob
 * and hand it to the browser's download machinery. Download is audited by core
 * before streaming (erp.documents.read required).
 */
export async function downloadDocument(
    id: string,
): Promise<{ blob: Blob; filename: string } | null> {
    const response = await apiFetchRaw(`/api/v1/documents/${id}/download`, {
        method: "GET",
    });
    if (!response.ok) return null;
    const disposition = response.headers.get("content-disposition") ?? "";
    const match = /filename="?([^"]+)"?/.exec(disposition);
    const filename = match?.[1] ?? "document";
    const blob = await response.blob();
    return { blob, filename };
}

/** Append a new immutable version to a document (multipart). erp.documents.write. */
export async function addDocumentVersion(
    id: string,
    file: File,
): Promise<Document | null> {
    const form = new FormData();
    form.append("file", file);
    const response = await fetchWithSession(`/api/v1/documents/${id}/versions`, {
        method: "POST",
        body: form,
    });
    if (!response.ok) {
        throw new Error("Version upload failed. Please try again.");
    }
    const payload = (await response.json().catch(() => ({}))) as {
        data?: DocumentPayload;
    };
    return payload.data ? mapDocument(payload.data) : null;
}

/** Re-enqueue OCR for documents in a state (`failed` or `ready`). erp.documents.write. */
export async function reindexDocuments(
    ocrStatus: OcrStatus = "failed",
): Promise<{ enqueued: number; message?: string } | null> {
    const raw = await apiPost<{ enqueued?: unknown; message?: string }>(
        "/api/v1/documents/reindex",
        { ocr_status: ocrStatus },
    );
    if (!raw) return null;
    return { enqueued: Number(raw.enqueued ?? 0), message: raw.message };
}

// ---------------------------------------------------------------------------
// Display helpers
// ---------------------------------------------------------------------------

export const OCR_STATUS_LABELS: Record<OcrStatus, string> = {
    pending: "Pending",
    processing: "Processing",
    ready: "Ready",
    failed: "Failed",
};

export const MODULE_REF_LABELS: Record<string, string> = {
    inventory: "Inventory",
    sales: "Sales",
    crm: "CRM",
    finance: "Finance",
    hr: "HR",
    payroll: "Payroll",
};

/** Human-readable label for a module_ref (empty = general / unlinked). */
export function moduleRefLabel(value: string | null | undefined): string {
    if (!value) return "General";
    return MODULE_REF_LABELS[value] ?? value.charAt(0).toUpperCase() + value.slice(1);
}

/** Short, locale-aware date for document timestamps. */
export function formatDate(value: string | null | undefined): string {
    if (!value) return "-";
    const parsed = new Date(value);
    if (Number.isNaN(parsed.getTime())) return "-";
    return parsed.toLocaleDateString(undefined, {
        month: "short",
        day: "numeric",
        year: "numeric",
    });
}

/** Human-readable file size. */
export function formatBytes(bytes: number): string {
    if (!bytes || bytes <= 0) return "0 B";
    const units = ["B", "KB", "MB", "GB"];
    const power = Math.min(
        Math.floor(Math.log(bytes) / Math.log(1024)),
        units.length - 1,
    );
    const value = bytes / 1024 ** power;
    return `${value.toFixed(value >= 10 || power === 0 ? 0 : 1)} ${units[power]}`;
}
