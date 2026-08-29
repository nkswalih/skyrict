"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";
import { Package, Pencil, Plus, RotateCcw, Trash2 } from "lucide-react";

import { InventoryEmpty } from "@/components/dashboard/erp/inventory/inventory-empty";
import {
    InventoryError,
    InventorySuccess,
} from "@/components/dashboard/erp/inventory/inventory-banners";
import { Pagination } from "@/components/dashboard/erp/pagination";
import { DataTableSkeleton } from "@/components/dashboard/shared/data-table";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
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
import { useModuleAccess } from "@/lib/access/modules";
import { ApiError } from "@/lib/api/http";
import { listAbcClassifications } from "@/lib/api/ai-api";
import {
    createProduct,
    deleteProduct,
    formatMoney,
    invalidateCatalog,
    listProducts,
    reactivateProduct,
    updateProduct,
    type PaginationMeta,
    type Product,
} from "@/lib/api/inventory-api";

const PAGE_SIZE = 20;

type Status =
    | { state: "loading" }
    | { state: "error"; message: string }
    | { state: "ready"; products: Product[]; meta: PaginationMeta };

const EMPTY_FORM = {
    sku: "",
    name: "",
    category: "",
    unit: "",
    costPrice: "",
    sellPrice: "",
    reorderPoint: "",
};

function formFromProduct(product: Product) {
    return {
        sku: product.sku,
        name: product.name,
        category: product.category ?? "",
        unit: product.unit ?? "",
        costPrice: product.costPrice[0],
        sellPrice: product.sellPrice[0],
        reorderPoint: product.reorderPoint,
    };
}

export function ProductsClient() {
    const { status: accessStatus, permissions } = useModuleAccess();
    const canWrite =
        accessStatus === "ready" &&
        (permissions.includes("*") ||
            permissions.includes("erp.inventory.write"));

    const [status, setStatus] = useState<Status>({ state: "loading" });
    const [page, setPage] = useState(1);
    const [includeInactive, setIncludeInactive] = useState(false);
    const [notice, setNotice] = useState<string | null>(null);

    const [dialogOpen, setDialogOpen] = useState(false);
    const [editing, setEditing] = useState<Product | null>(null);
    const [form, setForm] = useState(EMPTY_FORM);
    const [submitting, setSubmitting] = useState(false);
    const [formError, setFormError] = useState<string | null>(null);

    const [abcFilter, setAbcFilter] = useState<"all" | "A" | "B" | "C">("all");
    const [abcMap, setAbcMap] = useState<Map<string, string>>(new Map());

    const [deleting, setDeleting] = useState<Product | null>(null);
    const [deletingBusy, setDeletingBusy] = useState(false);
    const [deleteError, setDeleteError] = useState<string | null>(null);

    const abortRef = useRef<AbortController | null>(null);

    const load = useCallback(async () => {
        abortRef.current?.abort();
        const controller = new AbortController();
        abortRef.current = controller;
        setStatus({ state: "loading" });
        try {
            const result = await listProducts(
                {
                    page,
                    pageSize: PAGE_SIZE,
                    includeInactive,
                },
                { signal: controller.signal },
            );
            if (controller.signal.aborted) return;
            setStatus({
                state: "ready",
                products: result.data,
                meta: result.meta,
            });
        } catch (error) {
            if (controller.signal.aborted) return;
            const message =
                error instanceof ApiError
                    ? error.message
                    : "Could not load products.";
            setStatus({ state: "error", message });
        }
    }, [page, includeInactive]);

    useEffect(() => {
        void load();
        return () => abortRef.current?.abort();
    }, [load]);

    useEffect(() => {
        if (!notice) return;
        const timer = setTimeout(() => setNotice(null), 4000);
        return () => clearTimeout(timer);
    }, [notice]);

    useEffect(() => {
        listAbcClassifications()
            .then((res) => {
                const map = new Map<string, string>();
                for (const item of res.data) {
                    map.set(item.product_id, item.band);
                }
                setAbcMap(map);
            })
            .catch(() => {
                // ABC data unavailable — filter silently hidden
            });
    }, []);

    function openCreate() {
        setEditing(null);
        setForm(EMPTY_FORM);
        setFormError(null);
        setDialogOpen(true);
    }

    function openEdit(product: Product) {
        setEditing(product);
        setForm(formFromProduct(product));
        setFormError(null);
        setDialogOpen(true);
    }

    async function handleSubmit(event: FormEvent) {
        event.preventDefault();
        const sku = form.sku.trim();
        const name = form.name.trim();
        if (!sku || !name) {
            setFormError("SKU and name are required.");
            return;
        }
        setSubmitting(true);
        setFormError(null);
        try {
            const input = {
                sku,
                name,
                category: form.category.trim() || null,
                unit: form.unit.trim() || null,
                costPrice: form.costPrice ? Number(form.costPrice) : 0,
                sellPrice: form.sellPrice ? Number(form.sellPrice) : 0,
                reorderPoint: form.reorderPoint ? Number(form.reorderPoint) : 0,
            };
            if (editing) {
                await updateProduct(editing.id, input);
                setNotice(`Updated product ${sku}.`);
            } else {
                await createProduct(input);
                setNotice(`Created product ${sku}.`);
            }
            invalidateCatalog();
            setDialogOpen(false);
            if (page !== 1) setPage(1);
            else void load();
        } catch (error) {
            const message =
                error instanceof ApiError
                    ? error.message
                    : editing
                      ? "Could not update the product."
                      : "Could not create the product.";
            setFormError(message);
        } finally {
            setSubmitting(false);
        }
    }

    async function handleDelete() {
        if (!deleting) return;
        setDeletingBusy(true);
        setDeleteError(null);
        try {
            await deleteProduct(deleting.id);
            invalidateCatalog();
            setNotice(`Archived product ${deleting.sku}.`);
            setDeleting(null);
            if (page !== 1) setPage(1);
            else void load();
        } catch (error) {
            const message =
                error instanceof ApiError
                    ? error.message
                    : "Could not delete the product.";
            setDeleteError(message);
        } finally {
            setDeletingBusy(false);
        }
    }

    async function handleReactivate(product: Product) {
        try {
            await reactivateProduct(product.id);
            invalidateCatalog();
            setNotice(`Reactivated product ${product.sku}.`);
            if (page !== 1) setPage(1);
            else void load();
        } catch (error) {
            const message =
                error instanceof ApiError
                    ? error.message
                    : "Could not reactivate the product.";
            setNotice(message);
        }
    }

    if (status.state === "loading") return <DataTableSkeleton rows={6} />;

    if (status.state === "error") {
        return <InventoryError message={status.message} />;
    }

    const visibleProducts =
        abcFilter === "all"
            ? status.products
            : status.products.filter((p) => abcMap.get(p.id) === abcFilter);

    return (
        <div className="space-y-4">
            {notice ? <InventorySuccess message={notice} /> : null}

            <div className="flex items-center justify-between gap-3 flex-wrap">
                <div className="flex items-center gap-4 flex-wrap">
                    <p className="text-sm text-muted-foreground">
                        {status.meta.total} product
                        {status.meta.total === 1 ? "" : "s"}
                    </p>
                    <div className="flex items-center gap-2">
                        <Checkbox
                            id="products-include-archived"
                            checked={includeInactive}
                            onCheckedChange={(checked) => {
                                if (page !== 1) setPage(1);
                                setIncludeInactive(checked === true);
                            }}
                            aria-label="Include archived products"
                        />
                        <label
                            htmlFor="products-include-archived"
                            className="cursor-pointer text-sm text-muted-foreground"
                        >
                            Include archived
                        </label>
                    </div>
                    {abcMap.size > 0 && (
                        <div className="flex items-center gap-1.5">
                            <span className="text-xs text-muted-foreground">ABC:</span>
                            {(["all", "A", "B", "C"] as const).map((b) => (
                                <button
                                    key={b}
                                    onClick={() => setAbcFilter(b)}
                                    className={`inline-flex items-center rounded-full px-2.5 py-1 text-xs font-medium transition-colors ${
                                        abcFilter === b
                                            ? "bg-primary text-primary-foreground"
                                            : "text-muted-foreground hover:bg-muted hover:text-foreground"
                                    }`}
                                >
                                    {b === "all" ? "All" : `Band ${b}`}
                                </button>
                            ))}
                        </div>
                    )}
                </div>
                {canWrite ? (
                    <Button onClick={openCreate}>
                        <Plus aria-hidden="true" />
                        New product
                    </Button>
                ) : null}
            </div>

            {visibleProducts.length === 0 ? (
                <InventoryEmpty
                    title={abcFilter !== "all" ? `No Band ${abcFilter} products` : "No products yet"}
                    description={abcFilter !== "all" ? "No products match the selected ABC filter." : "Products are what you track stock for. Create one to start building your catalog."}
                    icon={Package}
                    action={
                        canWrite && abcFilter === "all" ? (
                            <Button onClick={openCreate}>
                                <Plus aria-hidden="true" />
                                Create a product
                            </Button>
                        ) : undefined
                    }
                />
            ) : (
                <div className="overflow-hidden rounded-xl border border-border bg-card">
                    <div className="overflow-x-auto">
                        <table className="w-full text-left text-sm">
                            <thead>
                                <tr className="border-b border-border bg-muted/40">
                                    <th
                                        scope="col"
                                        className="px-4 py-3 text-xs font-semibold tracking-wider text-muted-foreground uppercase"
                                    >
                                        SKU
                                    </th>
                                    <th
                                        scope="col"
                                        className="px-4 py-3 text-xs font-semibold tracking-wider text-muted-foreground uppercase"
                                    >
                                        Name
                                    </th>
                                    <th
                                        scope="col"
                                        className="px-4 py-3 text-xs font-semibold tracking-wider text-muted-foreground uppercase"
                                    >
                                        Category
                                    </th>
                                    <th
                                        scope="col"
                                        className="px-4 py-3 text-right text-xs font-semibold tracking-wider text-muted-foreground uppercase"
                                    >
                                        Sell
                                    </th>
                                    <th
                                        scope="col"
                                        className="px-4 py-3 text-right text-xs font-semibold tracking-wider text-muted-foreground uppercase"
                                    >
                                        Reorder at
                                    </th>
                                    {abcMap.size > 0 && (
                                        <th
                                            scope="col"
                                            className="px-4 py-3 text-xs font-semibold tracking-wider text-muted-foreground uppercase"
                                        >
                                            ABC
                                        </th>
                                    )}
                                    <th
                                        scope="col"
                                        className="px-4 py-3 text-xs font-semibold tracking-wider text-muted-foreground uppercase"
                                    >
                                        Status
                                    </th>
                                    {canWrite ? (
                                        <th scope="col" className="px-4 py-3">
                                            <span className="sr-only">
                                                Actions
                                            </span>
                                        </th>
                                    ) : null}
                                </tr>
                            </thead>
                            <tbody>
                                {visibleProducts.map((product) => {
                                    const band = abcMap.get(product.id);
                                    return (
                                    <tr
                                        key={product.id}
                                        className="border-b border-border/60 transition-colors last:border-0 hover:bg-muted/30"
                                    >
                                        <td className="px-4 py-3 font-medium text-foreground">
                                            {product.sku}
                                        </td>
                                        <td className="px-4 py-3 text-foreground">
                                            {product.name}
                                        </td>
                                        <td className="px-4 py-3 text-muted-foreground">
                                            {product.category ?? "—"}
                                        </td>
                                        <td className="px-4 py-3 text-right tabular-nums text-foreground">
                                            {formatMoney(product.sellPrice)}
                                        </td>
                                        <td className="px-4 py-3 text-right tabular-nums text-muted-foreground">
                                            {product.reorderPoint}
                                        </td>
                                        {abcMap.size > 0 && (
                                            <td className="px-4 py-3">
                                                {band ? (
                                                    <Badge
                                                        variant="outline"
                                                        className={`text-xs ring-1 ${
                                                            band === "A"
                                                                ? "bg-red-500/10 text-red-700 ring-red-500/30"
                                                                : band === "B"
                                                                  ? "bg-amber-500/10 text-amber-700 ring-amber-500/30"
                                                                  : "bg-blue-500/10 text-blue-700 ring-blue-500/30"
                                                        }`}
                                                    >
                                                        {band}
                                                    </Badge>
                                                ) : (
                                                    <span className="text-xs text-muted-foreground">—</span>
                                                )}
                                            </td>
                                        )}
                                        <td className="px-4 py-3">
                                            {product.isActive ? (
                                                <Badge
                                                    variant="outline"
                                                    className="bg-emerald-500/15 text-emerald-700 ring-1 ring-emerald-500/30 dark:text-emerald-400"
                                                >
                                                    Active
                                                </Badge>
                                            ) : (
                                                <Badge
                                                    variant="outline"
                                                    className="text-muted-foreground"
                                                >
                                                    Archived
                                                </Badge>
                                            )}
                                        </td>
                                        {canWrite ? (
                                            <td className="px-4 py-3">
                                                <div className="flex items-center justify-end gap-1">
                                                    {product.isActive ? (
                                                        <>
                                                            <Button
                                                                variant="ghost"
                                                                size="icon-sm"
                                                                onClick={() =>
                                                                    openEdit(
                                                                        product,
                                                                    )
                                                                }
                                                                aria-label={`Edit ${product.name}`}
                                                            >
                                                                <Pencil aria-hidden="true" />
                                                            </Button>
                                                            <Button
                                                                variant="ghost"
                                                                size="icon-sm"
                                                                className="text-destructive hover:bg-destructive/10 hover:text-destructive"
                                                                onClick={() => {
                                                                    setDeleteError(
                                                                        null,
                                                                    );
                                                                    setDeleting(
                                                                        product,
                                                                    );
                                                                }}
                                                                aria-label={`Delete ${product.name}`}
                                                            >
                                                                <Trash2 aria-hidden="true" />
                                                            </Button>
                                                        </>
                                                    ) : (
                                                        <Button
                                                            variant="ghost"
                                                            size="icon-sm"
                                                            onClick={() =>
                                                                void handleReactivate(
                                                                    product,
                                                                )
                                                            }
                                                            aria-label={`Reactivate ${product.name}`}
                                                        >
                                                            <RotateCcw aria-hidden="true" />
                                                        </Button>
                                                    )}
                                                </div>
                                            </td>
                                        ) : null}
                                    </tr>
                                )})}
                            </tbody>
                        </table>
                    </div>
                    <Pagination meta={status.meta} onPageChange={setPage} />
                </div>
            )}

            <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
                <DialogContent>
                    <DialogHeader>
                        <DialogTitle>
                            {editing ? "Edit product" : "New product"}
                        </DialogTitle>
                        <DialogDescription>
                            The SKU must be unique in this workspace.
                        </DialogDescription>
                    </DialogHeader>

                    <form
                        id="inventory-product-form"
                        onSubmit={handleSubmit}
                        className="grid gap-3"
                    >
                        {formError ? (
                            <InventoryError message={formError} />
                        ) : null}
                        <div className="grid gap-1.5">
                            <Label htmlFor="product-sku">SKU</Label>
                            <Input
                                id="product-sku"
                                value={form.sku}
                                onChange={(event) =>
                                    setForm({
                                        ...form,
                                        sku: event.target.value,
                                    })
                                }
                                placeholder="e.g. SKU-1001"
                                required
                                maxLength={64}
                            />
                        </div>
                        <div className="grid gap-1.5">
                            <Label htmlFor="product-name">Name</Label>
                            <Input
                                id="product-name"
                                value={form.name}
                                onChange={(event) =>
                                    setForm({
                                        ...form,
                                        name: event.target.value,
                                    })
                                }
                                placeholder="e.g. Steel bracket 4×4"
                                required
                                maxLength={255}
                            />
                        </div>
                        <div className="grid grid-cols-2 gap-3">
                            <div className="grid gap-1.5">
                                <Label htmlFor="product-category">
                                    Category
                                </Label>
                                <Input
                                    id="product-category"
                                    value={form.category}
                                    onChange={(event) =>
                                        setForm({
                                            ...form,
                                            category: event.target.value,
                                        })
                                    }
                                    placeholder="Hardware"
                                    maxLength={100}
                                />
                            </div>
                            <div className="grid gap-1.5">
                                <Label htmlFor="product-unit">Unit</Label>
                                <Input
                                    id="product-unit"
                                    value={form.unit}
                                    onChange={(event) =>
                                        setForm({
                                            ...form,
                                            unit: event.target.value,
                                        })
                                    }
                                    placeholder="pcs"
                                    maxLength={32}
                                />
                            </div>
                        </div>
                        <div className="grid grid-cols-3 gap-3">
                            <div className="grid gap-1.5">
                                <Label htmlFor="product-cost">Cost</Label>
                                <Input
                                    id="product-cost"
                                    type="number"
                                    min="0"
                                    step="0.01"
                                    value={form.costPrice}
                                    onChange={(event) =>
                                        setForm({
                                            ...form,
                                            costPrice: event.target.value,
                                        })
                                    }
                                    placeholder="0.00"
                                />
                            </div>
                            <div className="grid gap-1.5">
                                <Label htmlFor="product-sell">Sell price</Label>
                                <Input
                                    id="product-sell"
                                    type="number"
                                    min="0"
                                    step="0.01"
                                    value={form.sellPrice}
                                    onChange={(event) =>
                                        setForm({
                                            ...form,
                                            sellPrice: event.target.value,
                                        })
                                    }
                                    placeholder="0.00"
                                />
                            </div>
                            <div className="grid gap-1.5">
                                <Label htmlFor="product-reorder">
                                    Reorder at
                                </Label>
                                <Input
                                    id="product-reorder"
                                    type="number"
                                    min="0"
                                    step="1"
                                    value={form.reorderPoint}
                                    onChange={(event) =>
                                        setForm({
                                            ...form,
                                            reorderPoint: event.target.value,
                                        })
                                    }
                                    placeholder="0"
                                />
                            </div>
                        </div>
                    </form>

                    <DialogFooter showCloseButton={false}>
                        <Button
                            variant="outline"
                            onClick={() => setDialogOpen(false)}
                            disabled={submitting}
                        >
                            Cancel
                        </Button>
                        <Button
                            type="submit"
                            form="inventory-product-form"
                            disabled={submitting}
                        >
                            {submitting
                                ? editing
                                    ? "Saving…"
                                    : "Creating…"
                                : editing
                                  ? "Save changes"
                                  : "Create product"}
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
                        <DialogTitle>Archive product?</DialogTitle>
                        <DialogDescription>
                            {deleting
                                ? `${deleting.name} (${deleting.sku}) will be archived and hidden from the catalog. Remaining stock can be written off via Adjust stock, but it cannot be archived while reservations are open — and it stops receiving new stock movements until reactivated.`
                                : ""}
                        </DialogDescription>
                    </DialogHeader>

                    {deleteError ? (
                        <InventoryError message={deleteError} />
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
                            {deletingBusy ? "Archiving…" : "Archive"}
                        </Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>
        </div>
    );
}
