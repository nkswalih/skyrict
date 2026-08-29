"use client";

import { useCallback, useEffect, useState } from "react";
import { Check, Loader2, RefreshCw, X } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { InventoryEmpty } from "@/components/dashboard/erp/inventory/inventory-empty";
import { ApiError } from "@/lib/api/http";
import {
  listSuggestions,
  triggerScan,
  approveSuggestion,
  rejectSuggestion,
  type SuggestionItem,
} from "@/lib/api/ai-api";
import { ShoppingCart } from "lucide-react";

type Status =
  | { state: "loading" }
  | { state: "error"; message: string }
  | { state: "ready"; items: SuggestionItem[]; total: number };

function confidenceColor(c: string): string {
  const n = parseFloat(c);
  if (n >= 0.8) return "bg-emerald-500/10 text-emerald-700 ring-emerald-500/30";
  if (n >= 0.6) return "bg-amber-500/10 text-amber-700 ring-amber-500/30";
  return "bg-red-500/10 text-red-700 ring-red-500/30";
}

export function RestockSuggestions() {
  const [status, setStatus] = useState<Status>({ state: "loading" });
  const [scanning, setScanning] = useState(false);

  const load = useCallback(async () => {
    setStatus({ state: "loading" });
    try {
      const res = await listSuggestions();
      setStatus({ state: "ready", items: res.data, total: res.meta.total });
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : "Could not load suggestions.";
      setStatus({ state: "error", message: msg });
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const handleScan = async () => {
    setScanning(true);
    try {
      await triggerScan();
      await load();
    } catch {
      // scan errors are non-fatal
    } finally {
      setScanning(false);
    }
  };

  const handleApprove = async (id: string) => {
    try {
      await approveSuggestion(id);
      await load();
    } catch {
      // handled by UI
    }
  };

  const handleReject = async (id: string) => {
    try {
      await rejectSuggestion(id, "Rejected by manager");
      await load();
    } catch {
      // handled by UI
    }
  };

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

  const { items } = status;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="font-display text-lg font-semibold tracking-tight text-foreground">
          Restock Suggestions
        </h2>
        <Button
          variant="outline"
          size="sm"
          onClick={handleScan}
          disabled={scanning}
        >
          {scanning ? (
            <Loader2 aria-hidden="true" className="mr-1.5 size-4 animate-spin" />
          ) : (
            <RefreshCw aria-hidden="true" className="mr-1.5 size-4" />
          )}
          Scan now
        </Button>
      </div>
      {items.length === 0 ? (
        <InventoryEmpty
          title="No pending suggestions"
          description="No pending restock suggestions. Run a scan to check for items below reorder point."
          icon={ShoppingCart}
        />
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {items.map((item) => (
            <div
              key={item.id}
              className="rounded-xl border border-border bg-card p-5 space-y-3"
            >
              <div className="flex items-start justify-between">
                <p className="text-sm font-medium text-foreground">
                  {item.product_id.slice(0, 8)}...
                </p>
                <Badge
                  variant="outline"
                  className={`text-xs ring-1 ${confidenceColor(item.confidence)}`}
                >
                  {Math.round(parseFloat(item.confidence) * 100)}% confidence
                </Badge>
              </div>
              <div className="space-y-1 text-xs text-muted-foreground">
                <p>Current stock: {item.current_stock}</p>
                <p>Reorder point: {item.reorder_point}</p>
                <p className="font-medium text-foreground">
                  Suggest ordering: {item.suggested_qty}
                </p>
                {item.estimated_cost && (
                  <p>Estimated cost: {parseFloat(item.estimated_cost).toFixed(2)}</p>
                )}
              </div>
              <p className="text-xs text-muted-foreground italic">{item.reason}</p>
              <div className="flex gap-2 pt-1">
                <Button
                  size="sm"
                  variant="outline"
                  className="flex-1"
                  onClick={() => handleApprove(item.id)}
                >
                  <Check aria-hidden="true" className="mr-1 size-3" />
                  Approve
                </Button>
                <Button
                  size="sm"
                  variant="ghost"
                  className="flex-1 text-muted-foreground"
                  onClick={() => handleReject(item.id)}
                >
                  <X aria-hidden="true" className="mr-1 size-3" />
                  Reject
                </Button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
