"use client";

import { useCallback, useEffect, useState } from "react";
import { AlertTriangle, ArrowUpRight, Check, Loader2, RefreshCw, X } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { InventoryEmpty } from "@/components/dashboard/erp/inventory/inventory-empty";
import { ApiError } from "@/lib/api/http";
import {
  listAnomalies,
  triggerAnomalyScan,
  resolveAnomaly,
  dismissAnomaly,
  escalateAnomaly,
  type AnomalyItem,
} from "@/lib/api/ai-api";

type Status =
  | { state: "loading" }
  | { state: "error"; message: string }
  | { state: "ready"; items: AnomalyItem[]; meta: { total: number; open: number; high_severity: number } };

const SEVERITY_STYLES: Record<string, string> = {
  low: "bg-blue-500/10 text-blue-700 ring-blue-500/30",
  medium: "bg-amber-500/10 text-amber-700 ring-amber-500/30",
  high: "bg-red-500/10 text-red-700 ring-red-500/30",
  critical: "bg-red-600/10 text-red-800 ring-red-600/30",
};

export function AnomalyFeed() {
  const [status, setStatus] = useState<Status>({ state: "loading" });
  const [scanning, setScanning] = useState(false);

  const load = useCallback(async () => {
    setStatus({ state: "loading" });
    try {
      const res = await listAnomalies();
      setStatus({ state: "ready", items: res.data, meta: res.meta });
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : "Could not load anomalies.";
      setStatus({ state: "error", message: msg });
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const handleScan = async () => {
    setScanning(true);
    try {
      await triggerAnomalyScan();
      await load();
    } catch {
      // non-fatal
    } finally {
      setScanning(false);
    }
  };

  const handleAction = async (id: string, action: "resolve" | "dismiss" | "escalate") => {
    try {
      if (action === "resolve") await resolveAnomaly(id);
      else if (action === "dismiss") await dismissAnomaly(id, "False positive");
      else await escalateAnomaly(id);
      await load();
    } catch {
      // handled
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

  const { items, meta } = status;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <h2 className="font-display text-lg font-semibold tracking-tight text-foreground">
            Anomaly Feed
          </h2>
          {meta.open > 0 && (
            <Badge variant="outline" className="text-xs bg-red-500/10 text-red-700 ring-1 ring-red-500/30">
              {meta.open} open
            </Badge>
          )}
        </div>
        <Button variant="outline" size="sm" onClick={handleScan} disabled={scanning}>
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
          title="No anomalies detected"
          description="No anomalies detected. Run a scan to check for unusual patterns."
          icon={AlertTriangle}
        />
      ) : (
        <div className="space-y-3">
          {items.map((item) => (
            <div
              key={item.id}
              className="rounded-xl border border-border bg-card p-4 flex items-start gap-3"
            >
              <AlertTriangle
                aria-hidden="true"
                className={`mt-0.5 size-4 shrink-0 ${
                  item.severity === "critical"
                    ? "text-red-600"
                    : item.severity === "high"
                      ? "text-red-500"
                      : item.severity === "medium"
                        ? "text-amber-500"
                        : "text-blue-500"
                }`}
              />
              <div className="flex-1 min-w-0 space-y-1">
                <div className="flex items-center gap-2 flex-wrap">
                  <p className="text-sm font-medium text-foreground">{item.title}</p>
                  <Badge
                    variant="outline"
                    className={`text-xs ring-1 ${SEVERITY_STYLES[item.severity] ?? ""}`}
                  >
                    {item.severity}
                  </Badge>
                  <Badge variant="outline" className="text-xs">
                    {item.status}
                  </Badge>
                </div>
                <p className="text-xs text-muted-foreground line-clamp-2">
                  {item.description}
                </p>
                {item.status === "open" && (
                  <div className="flex gap-2 pt-1">
                    <Button size="sm" variant="outline" onClick={() => handleAction(item.id, "resolve")}>
                      <Check aria-hidden="true" className="mr-1 size-3" /> Resolve
                    </Button>
                    <Button size="sm" variant="ghost" onClick={() => handleAction(item.id, "dismiss")}>
                      <X aria-hidden="true" className="mr-1 size-3" /> Dismiss
                    </Button>
                    <Button size="sm" variant="ghost" onClick={() => handleAction(item.id, "escalate")}>
                      <ArrowUpRight aria-hidden="true" className="mr-1 size-3" /> Escalate
                    </Button>
                  </div>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
