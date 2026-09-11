"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
    Download,
    FilePlus2,
    FileText,
    RefreshCw,
    Sparkles,
    Trash2,
} from "lucide-react";

import {
    DocumentsError,
    DocumentsSuccess,
} from "@/components/dashboard/erp/documents/documents-banners";
import {
    OCR_STATUS_LABELS,
    addDocumentVersion,
    confirmDocumentTags,
    deleteDocument,
    downloadDocument,
    formatBytes,
    formatDate,
    getDocument,
    listDocumentVersions,
    moduleRefLabel,
    type Document as ErpDocument,
    type DocumentVersion,
} from "@/lib/api/documents-api";
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
import { useModuleAccess } from "@/lib/access/modules";
import { ApiError } from "@/lib/api/http";

function ocrBadgeClass(status: string): string {
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

type DetailStatus =
    | { state: "loading" }
    | { state: "error"; message: string }
    | { state: "ready"; document: ErpDocument; versions: DocumentVersion[] };

export function DocumentDetail({ id }: { id: string }) {
    const { status: accessStatus, permissions } = useModuleAccess();
    const canWrite =
        accessStatus === "ready" &&
        (permissions.includes("*") ||
            permissions.includes("erp.documents.write"));
    const canDelete =
        accessStatus === "ready" &&
        (permissions.includes("*") ||
            permissions.includes("erp.documents.delete"));

    const [status, setStatus] = useState<DetailStatus>({ state: "loading" });
    const [notice, setNotice] = useState<string | null>(null);
    const [downloading, setDownloading] = useState(false);

    const [confirmingBusy, setConfirmingBusy] = useState(false);
    const [confirmError, setConfirmError] = useState<string | null>(null);

    const [versionBusy, setVersionBusy] = useState(false);
    const [versionError, setVersionError] = useState<string | null>(null);

    const [deletingOpen, setDeletingOpen] = useState(false);
    const [deletingBusy, setDeletingBusy] = useState(false);
    const [deleteError, setDeleteError] = useState<string | null>(null);

    const versionInputRef = useRef<HTMLInputElement | null>(null);

    const load = useCallback(async () => {
        try {
            const [document, versions] = await Promise.all([
                getDocument(id),
                listDocumentVersions(id),
            ]);
            if (!document) {
                setStatus({
                    state: "error",
                    message: "Document not found.",
                });
                return;
            }
            setStatus({
                state: "ready",
                document,
                versions,
            });
        } catch (error) {
            const message =
                error instanceof ApiError
                    ? error.message
                    : "Could not load the document.";
            setStatus({ state: "error", message });
        }
    }, [id]);

    useEffect(() => {
        setStatus({ state: "loading" });
        void load();
    }, [load]);

    useEffect(() => {
        if (!notice) return;
        const timer = setTimeout(() => setNotice(null), 4000);
        return () => clearTimeout(timer);
    }, [notice]);

    async function handleDownload() {
        if (status.state !== "ready") return;
        setDownloading(true);
        try {
            const result = await downloadDocument(status.document.id);
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
        } finally {
            setDownloading(false);
        }
    }

    async function handleConfirmTags() {
        if (status.state !== "ready") return;
        setConfirmingBusy(true);
        setConfirmError(null);
        try {
            await confirmDocumentTags(status.document.id, status.document.aiTags);
            setNotice("Tags confirmed.");
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

    async function handleAddVersion(file: File | null) {
        if (status.state !== "ready" || !file) return;
        setVersionBusy(true);
        setVersionError(null);
        try {
            await addDocumentVersion(status.document.id, file);
            setNotice("New version uploaded.");
            if (versionInputRef.current) versionInputRef.current.value = "";
            void load();
        } catch (error) {
            const message =
                error instanceof ApiError
                    ? error.message
                    : "Could not upload a new version.";
            setVersionError(message);
        } finally {
            setVersionBusy(false);
        }
    }

    async function handleDelete() {
        if (status.state !== "ready") return;
        setDeletingBusy(true);
        setDeleteError(null);
        try {
            await deleteDocument(status.document.id);
            window.location.assign("/dashboard/erp/documents/list");
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

    if (status.state === "loading") return <DataTableSkeleton rows={5} />;

    if (status.state === "error") {
        return <DocumentsError message={status.message} />;
    }

    const { document, versions } = status;

    return (
        <div className="space-y-6">
            {notice ? <DocumentsSuccess message={notice} /> : null}

            <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="flex items-start gap-3">
                    <div className="mt-0.5 flex size-10 shrink-0 items-center justify-center rounded-xl border border-border bg-card text-primary">
                        <FileText aria-hidden="true" className="size-5" />
                    </div>
                    <div className="space-y-1">
                        <h1 className="font-display text-2xl font-semibold tracking-tight text-foreground">
                            {document.filename}
                        </h1>
                        <div className="flex flex-wrap items-center gap-2">
                            <Badge
                                variant="secondary"
                                className={`text-xs ${ocrBadgeClass(document.ocrStatus)}`}
                            >
                                {OCR_STATUS_LABELS[document.ocrStatus]}
                            </Badge>
                            <span className="text-sm text-muted-foreground">
                                {moduleRefLabel(document.moduleRef)}
                            </span>
                            <span className="text-sm text-muted-foreground">
                                {formatBytes(document.sizeBytes)}
                            </span>
                        </div>
                    </div>
                </div>
                <div className="flex items-center gap-2">
                    <Button
                        variant="outline"
                        size="sm"
                        onClick={() => void handleDownload()}
                        disabled={downloading}
                    >
                        {downloading ? (
                            <RefreshCw className="size-3.5 animate-spin" />
                        ) : (
                            <Download aria-hidden="true" className="size-3.5" />
                        )}
                        Download
                    </Button>
                    {canDelete ? (
                        <Button
                            variant="destructive"
                            size="sm"
                            onClick={() => {
                                setDeleteError(null);
                                setDeletingOpen(true);
                            }}
                        >
                            <Trash2 aria-hidden="true" className="size-3.5" />
                            Delete
                        </Button>
                    ) : null}
                </div>
            </div>

            <div className="grid gap-6 lg:grid-cols-3">
                <div className="space-y-6 lg:col-span-2">
                    <section className="rounded-xl border border-border bg-card">
                        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border/60 px-5 py-4">
                            <h2 className="font-display text-base font-semibold text-foreground">
                                Tags
                            </h2>
                            {canWrite ? (
                                <Button
                                    variant="outline"
                                    size="sm"
                                    onClick={() => void handleConfirmTags()}
                                    disabled={
                                        confirmingBusy ||
                                        document.tagsConfirmed ||
                                        document.aiTags.length === 0
                                    }
                                >
                                    <Sparkles aria-hidden="true" className="mr-1.5 size-3.5" />
                                    Confirm AI tags
                                </Button>
                            ) : null}
                        </div>
                        <div className="px-5 py-4">
                            {confirmError ? (
                                <DocumentsError message={confirmError} className="mb-3" />
                            ) : null}

                            {document.tags.length === 0 ? (
                                <p className="text-sm text-muted-foreground">
                                    No tags yet.
                                    {document.aiTags.length > 0
                                        ? " The AI agent suggested tags below."
                                        : ""}
                                </p>
                            ) : (
                                <div className="flex flex-wrap items-center gap-1.5">
                                    {document.tags.map((tag) => (
                                        <Badge key={tag} variant="outline" className="text-xs">
                                            {tag}
                                        </Badge>
                                    ))}
                                </div>
                            )}

                            {document.aiTags.length > 0 && !document.tagsConfirmed ? (
                                <div className="mt-4">
                                    <p className="mb-1.5 text-xs font-medium tracking-wider text-muted-foreground uppercase">
                                        AI suggestions
                                    </p>
                                    <div className="flex flex-wrap items-center gap-1.5">
                                        {document.aiTags.map((tag) => (
                                            <span
                                                key={tag}
                                                className="inline-flex items-center gap-1 rounded-full bg-primary/10 px-2 py-1 text-xs text-primary"
                                            >
                                                <Sparkles aria-hidden="true" className="size-3" />
                                                {tag}
                                            </span>
                                        ))}
                                    </div>
                                </div>
                            ) : null}
                        </div>
                    </section>

                    <section className="rounded-xl border border-border bg-card">
                        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border/60 px-5 py-4">
                            <h2 className="font-display text-base font-semibold text-foreground">
                                Version history
                            </h2>
                            {canWrite ? (
                                <>
                                    <Button
                                        variant="outline"
                                        size="sm"
                                        onClick={() =>
                                            versionInputRef.current?.click()
                                        }
                                        disabled={versionBusy}
                                    >
                                        <FilePlus2 aria-hidden="true" className="mr-1.5 size-3.5" />
                                        Add version
                                    </Button>
                                    <input
                                        ref={versionInputRef}
                                        type="file"
                                        className="sr-only"
                                        onChange={(event) => {
                                            void handleAddVersion(
                                                event.target.files?.[0] ?? null,
                                            );
                                        }}
                                    />
                                </>
                            ) : null}
                        </div>
                        <div className="px-5 py-4">
                            {versionError ? (
                                <DocumentsError message={versionError} className="mb-3" />
                            ) : null}
                            {versions.length === 0 ? (
                                <p className="text-sm text-muted-foreground">
                                    No versions recorded.
                                </p>
                            ) : (
                                <div className="overflow-hidden rounded-lg border border-border">
                                    <table className="w-full text-left text-sm">
                                        <thead>
                                            <tr className="border-b border-border bg-muted/40">
                                                <th scope="col" className="px-4 py-2.5 text-xs font-semibold tracking-wider text-muted-foreground uppercase">
                                                    Version
                                                </th>
                                                <th scope="col" className="px-4 py-2.5 text-xs font-semibold tracking-wider text-muted-foreground uppercase">
                                                    Filename
                                                </th>
                                                <th scope="col" className="px-4 py-2.5 text-right text-xs font-semibold tracking-wider text-muted-foreground uppercase">
                                                    Size
                                                </th>
                                                <th scope="col" className="px-4 py-2.5 text-xs font-semibold tracking-wider text-muted-foreground uppercase">
                                                    Added
                                                </th>
                                            </tr>
                                        </thead>
                                        <tbody>
                                            {versions.map((version) => (
                                                <tr
                                                    key={version.id}
                                                    className="border-b border-border/60 last:border-0"
                                                >
                                                    <td className="px-4 py-2.5 text-muted-foreground">
                                                        v{version.versionNumber}
                                                    </td>
                                                    <td className="px-4 py-2.5 text-foreground">
                                                        {version.filename}
                                                    </td>
                                                    <td className="px-4 py-2.5 text-right text-muted-foreground tabular-nums">
                                                        {formatBytes(version.sizeBytes)}
                                                    </td>
                                                    <td className="px-4 py-2.5 text-muted-foreground">
                                                        {formatDate(version.createdAt)}
                                                    </td>
                                                </tr>
                                            ))}
                                        </tbody>
                                    </table>
                                </div>
                            )}
                        </div>
                    </section>

                    <section className="rounded-xl border border-border bg-card">
                        <div className="border-b border-border/60 px-5 py-4">
                            <h2 className="font-display text-base font-semibold text-foreground">
                                Metadata
                            </h2>
                        </div>
                        <dl className="divide-y divide-border/60 text-sm">
                            {[
                                ["Checksum (SHA-256)", document.checksumSha256, true],
                                ["Storage backend", document.storageBackend, false],
                                ["Uploaded", formatDate(document.createdAt), false],
                                ["Updated", formatDate(document.updatedAt), false],
                                ["Version count", String(document.versionCount), false],
                                ["Created by", document.createdBy ?? "-", false],
                            ].map(([label, value, mono]) => (
                                <div
                                    key={String(label)}
                                    className="grid grid-cols-3 gap-3 px-5 py-3"
                                >
                                    <dt className="text-muted-foreground">
                                        {String(label)}
                                    </dt>
                                    <dd
                                        className={`col-span-2 break-words text-foreground ${
                                            mono ? "font-mono text-xs" : ""
                                        }`}
                                    >
                                        {String(value)}
                                    </dd>
                                </div>
                            ))}
                        </dl>
                    </section>
                </div>

                {document.extractedText ? (
                    <section className="rounded-xl border border-border bg-card">
                        <div className="border-b border-border/60 px-5 py-4">
                            <h2 className="font-display text-base font-semibold text-foreground">
                                Extracted text
                            </h2>
                        </div>
                        <p className="max-h-96 overflow-y-auto whitespace-pre-line px-5 py-4 text-sm leading-relaxed text-muted-foreground">
                            {document.extractedText}
                        </p>
                    </section>
                ) : null}
            </div>

            <Dialog open={deletingOpen} onOpenChange={setDeletingOpen}>
                <DialogContent>
                    <DialogHeader>
                        <DialogTitle>Delete document?</DialogTitle>
                        <DialogDescription>
                            {document.filename} and its version history will be
                            permanently removed.
                        </DialogDescription>
                    </DialogHeader>

                    {deleteError ? (
                        <DocumentsError message={deleteError} />
                    ) : null}

                    <DialogFooter showCloseButton={false}>
                        <Button
                            variant="outline"
                            onClick={() => setDeletingOpen(false)}
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