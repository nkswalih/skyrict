"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
    Download,
    FileText,
    Sparkles,
    Trash2,
} from "lucide-react";
import Link from "next/link";

import { DocumentsEmpty } from "@/components/dashboard/erp/documents/documents-empty";
import { DocumentsUploadDialog } from "@/components/dashboard/erp/documents/upload-dialog";
import {
    DocumentsError,
    DocumentsSuccess,
} from "@/components/dashboard/erp/documents/documents-banners";
import {
    OCR_STATUS_LABELS,
    downloadDocument,
    formatBytes,
    formatDate,
    listDocuments,
    moduleRefLabel,
    type Document as ErpDocument,
    type OcrStatus,
    type PaginationMeta,
} from "@/lib/api/documents-api";
import { deleteDocument } from "@/lib/api/documents-api";
import { confirmDocumentTags } from "@/lib/api/documents-api";
import { Pagination } from "@/components/dashboard/erp/pagination";
import { DataTableSkeleton } from "@/components/dashboard/shared/data-table";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogFooter,
    DialogHeader,
    DialogTitle,
} from "@/components/ui/dialog";
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from "@/components/ui/select";
import { useModuleAccess } from "@/lib/access/modules";
import { ApiError } from "@/lib/api/http";

const PAGE_SIZE = 20;

type Status =
    | { state: "loading" }
    | { state: "error"; message: string }
    |       {
          state: "ready";
          documents: ErpDocument[];
          meta: PaginationMeta;
      };

function ocrBadgeClass(status: OcrStatus): string {
    switch (status) {
        case "ready":
            return "bg-emerald-500/15 text-emerald-700 ring-1 ring-emerald-500/30 dark:text-emerald-400";
        case "processing":
            return "bg-sky-500/15 text-sky-700 ring-1 ring-sky-500/30 dark:text-sky-400";
        case "failed":
            return "bg-red-500/15 text-red-700 ring-1 ring-red-500/30 dark:text-red-400";
        default:
            return "bg-amber-500/15 text-amber-700 ring-1 ring-amber-500/30 dark:text-amber-400";
    }
}

interface ConfirmTarget {
    document: ErpDocument;
    aiTags: string[];
}

export function DocumentsList() {
    const { status: accessStatus, permissions } = useModuleAccess();
    const canWrite =
        accessStatus === "ready" &&
        (permissions.includes("*") ||
            permissions.includes("erp.documents.write"));
    const canDelete =
        accessStatus === "ready" &&
        (permissions.includes("*") ||
            permissions.includes("erp.documents.delete"));

    const [status, setStatus] = useState<Status>({ state: "loading" });
    const [page, setPage] = useState(1);
    const [ocrStatus, setOcrStatus] = useState<string>("all");
    const [moduleRef, setModuleRef] = useState<string>("all");
    const [notice, setNotice] = useState<string | null>(null);

    const [confirming, setConfirming] = useState<ConfirmTarget | null>(null);
    const [confirmingBusy, setConfirmingBusy] = useState(false);
    const [confirmError, setConfirmError] = useState<string | null>(null);

    const [deleting, setDeleting] = useState<ErpDocument | null>(null);
    const [deletingBusy, setDeletingBusy] = useState(false);
    const [deleteError, setDeleteError] = useState<string | null>(null);

    const abortRef = useRef<AbortController | null>(null);

    const load = useCallback(async () => {
        abortRef.current?.abort();
        const controller = new AbortController();
        abortRef.current = controller;
        setStatus({ state: "loading" });
        try {
            const result = await listDocuments(
                {
                    page,
                    pageSize: PAGE_SIZE,
                    ocrStatus: ocrStatus === "all" ? undefined : (ocrStatus as OcrStatus),
                    moduleRef: moduleRef === "all" ? undefined : moduleRef,
                },
                { signal: controller.signal },
            );
            if (controller.signal.aborted) return;
            setStatus({
                state: "ready",
                documents: result.data,
                meta: result.meta,
            });
        } catch (error) {
            if (controller.signal.aborted) return;
            const message =
                error instanceof ApiError
                    ? error.message
                    : "Could not load documents.";
            setStatus({ state: "error", message });
        }
    }, [page, ocrStatus, moduleRef]);

    useEffect(() => {
        void load();
        return () => abortRef.current?.abort();
    }, [load]);

    useEffect(() => {
        if (!notice) return;
        const timer = setTimeout(() => setNotice(null), 4000);
        return () => clearTimeout(timer);
    }, [notice]);

    function refresh() {
        if (page !== 1) setPage(1);
        else void load();
    }

    async function handleDownload(document: ErpDocument) {
        try {
            const result = await downloadDocument(document.id);
            if (!result) {
                setNotice("Could not download the document.");
                return;
            }
            const url = URL.createObjectURL(result.blob);
            const anchor = window.document.createElement("a");
            anchor.href = url;
            anchor.download = result.filename;
            anchor.click();
            URL.revokeObjectURL(url);
        } catch {
            setNotice("Could not download the document.");
        }
    }

    async function handleConfirmTags() {
        if (!confirming) return;
        setConfirmingBusy(true);
        setConfirmError(null);
        try {
            await confirmDocumentTags(
                confirming.document.id,
                confirming.aiTags,
            );
            setNotice("Tags confirmed for the document.");
            setConfirming(null);
            void load();
        } catch (error) {
            const message =
                error instanceof ApiError
                    ? error.message
                    : "Could not confirm tags.";
            setConfirmError(message);
        } finally {
            setConfirmingBusy(false);
        }
    }

    async function handleDelete() {
        if (!deleting) return;
        setDeletingBusy(true);
        setDeleteError(null);
        try {
            await deleteDocument(deleting.id);
            setNotice(`Deleted ${deleting.filename}.`);
            setDeleting(null);
            refresh();
        } catch (error) {
            const message =
                error instanceof ApiError
                    ? error.message
                    : "Could not delete the document.";
            setDeleteError(message);
        } finally {
            setDeletingBusy(false);
        }
    }

    if (status.state === "loading") return <DataTableSkeleton rows={6} />;

    if (status.state === "error") {
        return <DocumentsError message={status.message} />;
    }

    const documents = status.documents;

    return (
        <div className="space-y-4">
            {notice ? <DocumentsSuccess message={notice} /> : null}

            <div className="flex items-center justify-between gap-3 flex-wrap">
                <div className="flex items-center gap-4 flex-wrap">
                    <p className="text-sm text-muted-foreground">
                        {status.meta.total} document
                        {status.meta.total === 1 ? "" : "s"}
                    </p>
                    <Select value={ocrStatus} onValueChange={(value) => {
                        if (page !== 1) setPage(1);
                        setOcrStatus(value);
                    }}>
                        <SelectTrigger aria-label="Filter by OCR status" size="sm">
                            <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                            <SelectItem value="all">All statuses</SelectItem>
                            {(Object.keys(OCR_STATUS_LABELS) as OcrStatus[]).map(
                                (value) => (
                                    <SelectItem key={value} value={value}>
                                        {OCR_STATUS_LABELS[value]}
                                    </SelectItem>
                                ),
                            )}
                        </SelectContent>
                    </Select>
                    <Select value={moduleRef} onValueChange={(value) => {
                        if (page !== 1) setPage(1);
                        setModuleRef(value);
                    }}>
                        <SelectTrigger aria-label="Filter by module" size="sm">
                            <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                            <SelectItem value="all">All modules</SelectItem>
                            <SelectItem value="">General</SelectItem>
                            {["inventory", "sales", "crm", "finance", "hr", "payroll"].map(
                                (value) => (
                                    <SelectItem key={value} value={value}>
                                        {moduleRefLabel(value)}
                                    </SelectItem>
                                ),
                            )}
                        </SelectContent>
                    </Select>
                </div>
                {canWrite ? <DocumentsUploadDialog onUploaded={refresh} /> : null}
            </div>

            {documents.length === 0 ? (
                <DocumentsEmpty
                    title="No documents yet"
                    description="Upload files to start building the document library. AI extraction will scan them for text and suggest tags."
                    icon={FileText}
                    action={
                        canWrite ? (
                            <DocumentsUploadDialog onUploaded={refresh} />
                        ) : undefined
                    }
                />
            ) : (
                <div className="overflow-hidden rounded-xl border border-border bg-card">
                    <div className="overflow-x-auto">
                        <table className="w-full text-left text-sm">
                            <thead>
                                <tr className="border-b border-border bg-muted/40">
                                    <th scope="col" className="px-4 py-3 text-xs font-semibold tracking-wider text-muted-foreground uppercase">
                                        Name
                                    </th>
                                    <th scope="col" className="px-4 py-3 text-xs font-semibold tracking-wider text-muted-foreground uppercase">
                                        Module
                                    </th>
                                    <th scope="col" className="px-4 py-3 text-xs font-semibold tracking-wider text-muted-foreground uppercase">
                                        Tags
                                    </th>
                                    <th scope="col" className="px-4 py-3 text-xs font-semibold tracking-wider text-muted-foreground uppercase">
                                        Status
                                    </th>
                                    <th scope="col" className="px-4 py-3 text-right text-xs font-semibold tracking-wider text-muted-foreground uppercase">
                                        Size
                                    </th>
                                    <th scope="col" className="px-4 py-3 text-xs font-semibold tracking-wider text-muted-foreground uppercase">
                                        Uploaded
                                    </th>
                                    <th scope="col" className="px-4 py-3">
                                        <span className="sr-only">Actions</span>
                                    </th>
                                </tr>
                            </thead>
                            <tbody>
                                {documents.map((document) => {
                                    const showConfirm =
                                        canWrite &&
                                        !document.tagsConfirmed &&
                                        document.aiTags.length > 0;
                                    return (
                                        <tr
                                            key={document.id}
                                            className="border-b border-border/60 transition-colors last:border-0 hover:bg-muted/30"
                                        >
                                            <td className="px-4 py-3">
                                                <Link
                                                    href={`/dashboard/erp/documents/${document.id}`}
                                                    className="font-medium text-foreground hover:text-primary"
                                                >
                                                    {document.filename}
                                                </Link>
                                            </td>
                                            <td className="px-4 py-3 text-muted-foreground">
                                                {moduleRefLabel(document.moduleRef)}
                                            </td>
                                            <td className="px-4 py-3">
                                                <div className="flex flex-wrap items-center gap-1">
                                                    {document.tags.slice(0, 3).map(
                                                        (tag) => (
                                                            <Badge
                                                                key={tag}
                                                                variant="outline"
                                                                className="text-xs"
                                                            >
                                                                {tag}
                                                            </Badge>
                                                        ),
                                                    )}
                                                    {document.tags.length > 3 ? (
                                                        <span className="text-xs text-muted-foreground">
                                                            +{document.tags.length - 3}
                                                        </span>
                                                    ) : null}
                                                    {document.tags.length === 0 ? (
                                                        <span className="text-xs text-muted-foreground">
                                                            -
                                                        </span>
                                                    ) : null}
                                                </div>
                                            </td>
                                            <td className="px-4 py-3">
                                                <Badge
                                                    variant="secondary"
                                                    className={`text-xs ${ocrBadgeClass(document.ocrStatus)}`}
                                                >
                                                    {OCR_STATUS_LABELS[
                                                        document.ocrStatus
                                                    ]}
                                                </Badge>
                                            </td>
                                            <td className="px-4 py-3 text-right text-muted-foreground tabular-nums">
                                                {formatBytes(document.sizeBytes)}
                                            </td>
                                            <td className="px-4 py-3 text-muted-foreground">
                                                {formatDate(document.createdAt)}
                                            </td>
                                            <td className="px-4 py-3">
                                                <div className="flex items-center justify-end gap-1">
                                                    {showConfirm ? (
                                                        <Button
                                                            variant="ghost"
                                                            size="icon-sm"
                                                            onClick={() =>
                                                                setConfirming({
                                                                    document,
                                                                    aiTags: document.aiTags,
                                                                })
                                                            }
                                                            aria-label={`Confirm AI tags for ${document.filename}`}
                                                        >
                                                            <Sparkles aria-hidden="true" />
                                                        </Button>
                                                    ) : null}
                                                    <Button
                                                        variant="ghost"
                                                        size="icon-sm"
                                                        onClick={() =>
                                                            void handleDownload(
                                                                document,
                                                            )
                                                        }
                                                        aria-label={`Download ${document.filename}`}
                                                    >
                                                        <Download aria-hidden="true" />
                                                    </Button>
                                                    {canDelete ? (
                                                        <Button
                                                            variant="ghost"
                                                            size="icon-sm"
                                                            className="text-destructive hover:bg-destructive/10 hover:text-destructive"
                                                            onClick={() => {
                                                                setDeleteError(
                                                                    null,
                                                                );
                                                                setDeleting(
                                                                    document,
                                                                );
                                                            }}
                                                            aria-label={`Delete ${document.filename}`}
                                                        >
                                                            <Trash2 aria-hidden="true" />
                                                        </Button>
                                                    ) : null}
                                                </div>
                                            </td>
                                        </tr>
                                    );
                                })}
                            </tbody>
                        </table>
                    </div>
                    <Pagination meta={status.meta} onPageChange={setPage} />
                </div>
            )}

            <Dialog
                open={confirming !== null}
                onOpenChange={(open) => {
                    if (!open && !confirmingBusy) setConfirming(null);
                }}
            >
                <DialogContent>
                    <DialogHeader>
                        <DialogTitle>Confirm AI tags</DialogTitle>
                        <DialogDescription>
                            {confirming
                                ? `The AI agent suggested these tags for "${confirming.document.filename}". Confirming makes them authoritative.`
                                : ""}
                        </DialogDescription>
                    </DialogHeader>

                    {confirming ? (
                        <div className="flex flex-wrap items-center gap-1.5">
                            {confirming.aiTags.map((tag) => (
                                <Badge
                                    key={tag}
                                    variant="outline"
                                    className="text-xs"
                                >
                                    {tag}
                                </Badge>
                            ))}
                        </div>
                    ) : null}

                    {confirmError ? (
                        <DocumentsError message={confirmError} />
                    ) : null}

                    <DialogFooter showCloseButton={false}>
                        <Button
                            variant="outline"
                            onClick={() => setConfirming(null)}
                            disabled={confirmingBusy}
                        >
                            Cancel
                        </Button>
                        <Button
                            onClick={() => void handleConfirmTags()}
                            disabled={confirmingBusy}
                        >
                            {confirmingBusy ? "Confirming…" : "Confirm tags"}
                        </Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>

            <Dialog
                open={deleting !== null}
                onOpenChange={(open) => {
                    if (!open && !deletingBusy) setDeleting(null);
                }}
            >
                <DialogContent>
                    <DialogHeader>
                        <DialogTitle>Delete document?</DialogTitle>
                        <DialogDescription>
                            {deleting
                                ? `"${deleting.filename}" and its version history will be permanently removed.`
                                : ""}
                        </DialogDescription>
                    </DialogHeader>

                    {deleteError ? (
                        <DocumentsError message={deleteError} />
                    ) : null}

                    <DialogFooter showCloseButton={false}>
                        <Button
                            variant="outline"
                            onClick={() => setDeleting(null)}
                            disabled={deletingBusy}
                        >
                            Cancel
                        </Button>
                        <Button
                            variant="destructive"
                            onClick={() => void handleDelete()}
                            disabled={deletingBusy}
                        >
                            {deletingBusy ? "Deleting…" : "Delete"}
                        </Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>
        </div>
    );
}