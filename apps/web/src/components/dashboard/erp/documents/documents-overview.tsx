"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
    AlertTriangle,
    CheckCircle2,
    Clock,
    FileText,
    LoaderCircle,
    RefreshCw,
    Sparkles,
} from "lucide-react";
import Link from "next/link";

import { DocumentsUploadDialog } from "@/components/dashboard/erp/documents/upload-dialog";
import {
    DocumentsError,
    DocumentsSuccess,
} from "@/components/dashboard/erp/documents/documents-banners";
import { StatCard } from "@/components/dashboard/shared/stat-card";
import { Button } from "@/components/ui/button";
import { useModuleAccess } from "@/lib/access/modules";
import {
    ApiError,
} from "@/lib/api/http";
import {
    listDocuments,
    moduleRefLabel,
    OCR_STATUS_LABELS,
    reindexDocuments,
    type Document,
} from "@/lib/api/documents-api";
import { formatBytes, formatDate } from "@/lib/api/documents-api";

type OverviewStatus =
    | { state: "loading" }
    | { state: "error"; message: string }
    | { state: "ready"; documents: Document[] };

export function DocumentsOverview() {
    const { status: accessStatus, permissions } = useModuleAccess();
    const canWrite =
        accessStatus === "ready" &&
        (permissions.includes("*") ||
            permissions.includes("erp.documents.write"));

    const [status, setStatus] = useState<OverviewStatus>({ state: "loading" });
    const [notice, setNotice] = useState<string | null>(null);
    const [reindexing, setReindexing] = useState(false);
    const [reindexed, setReindexed] = useState<number | null>(null);

    const abortRef = useRef<AbortController | null>(null);

    const load = useCallback(async () => {
        abortRef.current?.abort();
        const controller = new AbortController();
        abortRef.current = controller;
        setStatus({ state: "loading" });
        try {
            const result = await listDocuments(
                { page: 1, pageSize: 100 },
                { signal: controller.signal },
            );
            if (controller.signal.aborted) return;
            setStatus({ state: "ready", documents: result.data });
        } catch (error) {
            if (controller.signal.aborted) return;
            const message =
                error instanceof ApiError
                    ? error.message
                    : "Could not load documents.";
            setStatus({ state: "error", message });
        }
    }, []);

    useEffect(() => {
        void load();
        return () => abortRef.current?.abort();
    }, [load]);

    useEffect(() => {
        if (!notice) return;
        const timer = setTimeout(() => setNotice(null), 4000);
        return () => clearTimeout(timer);
    }, [notice]);

    async function handleReindex() {
        setReindexing(true);
        setNotice(null);
        setReindexed(null);
        try {
            const result = await reindexDocuments("failed");
            setReindexed(result?.enqueued ?? 0);
        } catch {
            setNotice("Reindex failed. Try again.");
        } finally {
            setReindexing(false);
        }
    }

    if (status.state === "loading") {
        return (
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
                <LoaderCircle className="size-4 animate-spin" />
                Loading documents…
            </div>
        );
    }

    if (status.state === "error") {
        return <DocumentsError message={status.message} />;
    }

    const documents = status.documents;
    const counts: Record<string, number> = { pending: 0, processing: 0, ready: 0, failed: 0 };
    for (const doc of documents) {
        if (doc.ocrStatus in counts) counts[doc.ocrStatus] += 1;
    }
    const ready = documents.filter((doc) => doc.ocrStatus === "ready");
    const failed = counts.failed;

    return (
        <div className="space-y-6">
            {notice ? <DocumentsSuccess message={notice} /> : null}

            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
                <StatCard
                    icon={FileText}
                    label="Total documents"
                    value={String(documents.length)}
                    hint="Across all modules"
                />
                <StatCard
                    icon={CheckCircle2}
                    label="Ready"
                    value={String(counts.ready)}
                    href="/dashboard/erp/documents/list?status=ready"
                />
                <StatCard
                    icon={Clock}
                    label="Pending / processing"
                    value={String(counts.pending + counts.processing)}
                    href="/dashboard/erp/documents/list"
                />
                <StatCard
                    icon={AlertTriangle}
                    label="Failed"
                    value={String(failed)}
                    href="/dashboard/erp/documents/list?status=failed"
                />
            </div>

            <div className="flex flex-wrap items-center justify-between gap-3">
                <h2 className="font-display text-lg font-semibold tracking-tight text-foreground">
                    Extracted documents
                </h2>
                <div className="flex items-center gap-2">
                    {canWrite ? (
                        <>
                            <Button
                                variant="outline"
                                size="sm"
                                onClick={() => void handleReindex()}
                                disabled={reindexing || failed === 0}
                            >
                                {reindexing ? (
                                    <RefreshCw className="size-3.5 animate-spin" />
                                ) : (
                                    <RefreshCw aria-hidden="true" className="size-3.5" />
                                )}
                                Reindex failed
                            </Button>
                            {reindexed !== null ? (
                                <span className="text-xs text-muted-foreground">
                                    {reindexed} re-queued
                                </span>
                            ) : null}
                            <DocumentsUploadDialog onUploaded={() => void load()} />
                        </>
                    ) : null}
                </div>
            </div>

            {ready.length === 0 ? (
                <p className="text-sm text-muted-foreground">
                    No documents have been extracted yet. Upload one to get
                    started.
                </p>
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
                                        AI tags
                                    </th>
                                    <th scope="col" className="px-4 py-3 text-right text-xs font-semibold tracking-wider text-muted-foreground uppercase">
                                        Size
                                    </th>
                                    <th scope="col" className="px-4 py-3 text-xs font-semibold tracking-wider text-muted-foreground uppercase">
                                        Uploaded
                                    </th>
                                </tr>
                            </thead>
                            <tbody>
                                {ready.slice(0, 5).map((doc) => (
                                    <tr
                                        key={doc.id}
                                        className="border-b border-border/60 transition-colors last:border-0 hover:bg-muted/30"
                                    >
                                        <td className="px-4 py-3">
                                            <Link
                                                href={`/dashboard/erp/documents/${doc.id}`}
                                                className="font-medium text-foreground hover:text-primary"
                                            >
                                                {doc.filename}
                                            </Link>
                                        </td>
                                        <td className="px-4 py-3 text-muted-foreground">
                                            {moduleRefLabel(doc.moduleRef)}
                                        </td>
                                        <td className="px-4 py-3">
                                            <div className="flex flex-wrap items-center gap-1">
                                                {doc.aiTags.length > 0 ? (
                                                    <>
                                                        <Sparkles aria-hidden="true" className="size-3.5 text-primary" />
                                                        {doc.aiTags.slice(0, 3).map((tag) => (
                                                            <span
                                                                key={tag}
                                                                className="inline-flex items-center rounded-full bg-primary/10 px-2 py-0.5 text-xs text-primary"
                                                            >
                                                                {tag}
                                                            </span>
                                                        ))}
                                                        {!doc.tagsConfirmed ? (
                                                            <span className="text-xs text-muted-foreground">
                                                                suggested
                                                            </span>
                                                        ) : null}
                                                    </>
                                                ) : (
                                                    <span className="text-xs text-muted-foreground">
                                                        -
                                                    </span>
                                                )}
                                            </div>
                                        </td>
                                        <td className="px-4 py-3 text-right text-muted-foreground tabular-nums">
                                            {formatBytes(doc.sizeBytes)}
                                        </td>
                                        <td className="px-4 py-3 text-muted-foreground">
                                            {formatDate(doc.createdAt)}
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                </div>
            )}

            <p className="text-xs text-muted-foreground">
                Status labels reference core:{" "}
                {Object.entries(OCR_STATUS_LABELS).map(([key, label]) => `${label} (${key})`).join(", ")}.
            </p>
        </div>
    );
}