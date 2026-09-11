"use client";

import { useRef, useState } from "react";
import { FileUp, Plus } from "lucide-react";

import { DocumentsError } from "@/components/dashboard/erp/documents/documents-banners";
import { Button } from "@/components/ui/button";
import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogFooter,
    DialogHeader,
    DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from "@/components/ui/select";
import { ApiError } from "@/lib/api/http";
import { uploadDocument } from "@/lib/api/documents-api";

const MODULE_OPTIONS = [
    { value: "", label: "General (no link)" },
    { value: "inventory", label: "Inventory" },
    { value: "sales", label: "Sales" },
    { value: "crm", label: "CRM" },
    { value: "finance", label: "Finance" },
    { value: "hr", label: "HR" },
    { value: "payroll", label: "Payroll" },
];

export function DocumentsUploadDialog({
    onUploaded,
}: {
    onUploaded: () => void;
}) {
    const [open, setOpen] = useState(false);
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [file, setFile] = useState<File | null>(null);
    const [moduleRef, setModuleRef] = useState("");
    const [tags, setTags] = useState("");
    const inputRef = useRef<HTMLInputElement | null>(null);

    function reset() {
        setFile(null);
        setModuleRef("");
        setTags("");
        setError(null);
        if (inputRef.current) inputRef.current.value = "";
    }

    async function handleSubmit() {
        if (!file) {
            setError("Choose a file to upload.");
            return;
        }
        setBusy(true);
        setError(null);
        try {
            await uploadDocument({
                file,
                moduleRef: moduleRef || undefined,
                tags: tags
                    ? tags
                          .split(",")
                          .map((tag) => tag.trim())
                          .filter(Boolean)
                    : undefined,
            });
            reset();
            setOpen(false);
            onUploaded();
        } catch (err) {
            const message =
                err instanceof ApiError
                    ? err.message
                    : "Could not upload the document.";
            setError(message);
        } finally {
            setBusy(false);
        }
    }

    return (
        <>
            <Button
                onClick={() => {
                    reset();
                    setOpen(true);
                }}
            >
                <Plus aria-hidden="true" />
                Upload document
            </Button>
            <Dialog open={open} onOpenChange={setOpen}>
                <DialogContent>
                    <DialogHeader>
                        <DialogTitle>Upload document</DialogTitle>
                        <DialogDescription>
                            The file is stored immutably and queued for AI
                            extraction (OCR + tag suggestions).
                        </DialogDescription>
                    </DialogHeader>

                    <div className="grid gap-3">
                        {error ? <DocumentsError message={error} /> : null}

                        <button
                            type="button"
                            onClick={() => inputRef.current?.click()}
                            className="flex flex-col items-center justify-center gap-2 rounded-xl border border-dashed border-border bg-muted/30 px-4 py-8 text-center transition-colors hover:border-primary/50 hover:bg-muted/40"
                        >
                            <FileUp
                                aria-hidden="true"
                                className="size-6 text-muted-foreground"
                            />
                            {file ? (
                                <span className="text-sm font-medium text-foreground">
                                    {file.name}
                                </span>
                            ) : (
                                <span className="text-sm text-muted-foreground">
                                    Choose a file to upload
                                </span>
                            )}
                            <span className="text-xs text-muted-foreground">
                                Files are stored immutably with checksum
                                tracking.
                            </span>
                        </button>
                        <input
                            ref={inputRef}
                            id="documents-upload-file"
                            type="file"
                            className="sr-only"
                            onChange={(event) => {
                                const next = event.target.files?.[0] ?? null;
                                if (next) {
                                    setFile(next);
                                    setError(null);
                                }
                            }}
                        />

                        <div className="grid gap-1.5">
                            <Label htmlFor="documents-upload-module">
                                Link to module
                            </Label>
                            <Select
                                value={moduleRef}
                                onValueChange={setModuleRef}
                            >
                                <SelectTrigger
                                    id="documents-upload-module"
                                    className="w-full"
                                >
                                    <SelectValue />
                                </SelectTrigger>
                                <SelectContent>
                                    {MODULE_OPTIONS.map((option) => (
                                        <SelectItem
                                            key={option.value}
                                            value={option.value}
                                        >
                                            {option.label}
                                        </SelectItem>
                                    ))}
                                </SelectContent>
                            </Select>
                        </div>

                        <div className="grid gap-1.5">
                            <Label htmlFor="documents-upload-tags">
                                Tags
                            </Label>
                            <Input
                                id="documents-upload-tags"
                                value={tags}
                                onChange={(event) =>
                                    setTags(event.target.value)
                                }
                                placeholder="invoice, quotations, 2024"
                            />
                            <p className="text-xs text-muted-foreground">
                                Comma-separated. AI tag suggestions arrive after
                                extraction.
                            </p>
                        </div>
                    </div>

                    <DialogFooter showCloseButton={false}>
                        <Button
                            variant="outline"
                            onClick={() => setOpen(false)}
                            disabled={busy}
                        >
                            Cancel
                        </Button>
                        <Button
                            type="button"
                            onClick={() => void handleSubmit()}
                            disabled={busy}
                        >
                            {busy ? "Uploading…" : "Upload"}
                        </Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>
        </>
    );
}