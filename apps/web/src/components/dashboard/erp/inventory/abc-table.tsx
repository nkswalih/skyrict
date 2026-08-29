"use client";

import { useCallback, useEffect, useState } from "react";
import { Loader2 } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { InventoryEmpty } from "@/components/dashboard/erp/inventory/inventory-empty";
import { ApiError } from "@/lib/api/http";
import { listAbcClassifications, getAbcSummary, type AbcItem } from "@/lib/api/ai-api";
import { BarChart3 } from "lucide-react";

type Status =
  | { state: "loading" }
  | { state: "error"; message: string }
  | { state: "ready"; items: AbcItem[]; summary: Record<string, number> };

const BAND_STYLES: Record<string, string> = {
  A: "bg-red-500/10 text-red-700 ring-red-500/30",
  B: "bg-amber-500/10 text-amber-700 ring-amber-500/30",
  C: "bg-blue-500/10 text-blue-700 ring-blue-500/30",
};

export function AbcTable() {
  const [status, setStatus] = useState<Status>({ state: "loading" });
  const [filter, setFilter] = useState<"all" | "A" | "B" | "C">("all");

  const load = useCallback(async () => {
    setStatus({ state: "loading" });
    try {
      const [itemsRes, summaryRes] = await Promise.all([
        listAbcClassifications(),
        getAbcSummary(),
      ]);
      setStatus({
        state: "ready",
        items: itemsRes.data,
        summary: summaryRes.data,
      });
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : "Could not load ABC data.";
      setStatus({ state: "error", message: msg });
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  if (status.state === "loading") {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 className="size-6 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (status.state === "error") {
    return <p className="text-sm text-destructive py-8 text-center">{status.message}</p>;
  }

  const { items, summary } = status;
  const filtered = filter === "all" ? items : items.filter((i) => i.band === filter);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <h2 className="font-display text-lg font-semibold tracking-tight text-foreground">
          ABC Classification
        </h2>
        <div className="flex gap-1.5">
          {(["all", "A", "B", "C"] as const).map((b) => (
            <button
              key={b}
              onClick={() => setFilter(b)}
              className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 text-xs font-medium transition-colors ${
                filter === b
                  ? "bg-primary text-primary-foreground"
                  : "text-muted-foreground hover:bg-muted hover:text-foreground"
              }`}
            >
              {b === "all" ? "All" : `Band ${b}`}
              {b !== "all" && summary[b] != null && (
                <span className="opacity-70">{summary[b]}</span>
              )}
            </button>
          ))}
        </div>
      </div>

      {filtered.length === 0 ? (
        <InventoryEmpty
          title="No ABC classifications"
          description="No ABC classifications found. Run the ABC scan from the backend to populate this data."
          icon={BarChart3}
        />
      ) : (
        <div className="overflow-hidden rounded-xl border border-border bg-card">
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead>
                <tr className="border-b border-border bg-muted/40">
                  <th scope="col" className="px-4 py-3 text-xs font-semibold tracking-wider text-muted-foreground uppercase">
                    Product
                  </th>
                  <th scope="col" className="px-4 py-3 text-xs font-semibold tracking-wider text-muted-foreground uppercase">
                    SKU
                  </th>
                  <th scope="col" className="px-4 py-3 text-right text-xs font-semibold tracking-wider text-muted-foreground uppercase">
                    Revenue
                  </th>
                  <th scope="col" className="px-4 py-3 text-right text-xs font-semibold tracking-wider text-muted-foreground uppercase">
                    Share
                  </th>
                  <th scope="col" className="px-4 py-3 text-xs font-semibold tracking-wider text-muted-foreground uppercase">
                    Band
                  </th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((item) => (
                  <tr
                    key={item.product_id}
                    className="border-b border-border/60 transition-colors last:border-0 hover:bg-muted/30"
                  >
                    <td className="px-4 py-3 font-medium text-foreground">
                      {item.product_name}
                    </td>
                    <td className="px-4 py-3 text-muted-foreground">
                      {item.sku}
                    </td>
                    <td className="px-4 py-3 text-right tabular-nums text-foreground">
                      {Number(item.revenue).toLocaleString(undefined, {
                        minimumFractionDigits: 2,
                        maximumFractionDigits: 2,
                      })}
                    </td>
                    <td className="px-4 py-3 text-right tabular-nums text-muted-foreground">
                      {(parseFloat(item.revenue_share) * 100).toFixed(1)}%
                    </td>
                    <td className="px-4 py-3">
                      <Badge
                        variant="outline"
                        className={`text-xs ring-1 ${BAND_STYLES[item.band] ?? ""}`}
                      >
                        {item.band}
                      </Badge>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
