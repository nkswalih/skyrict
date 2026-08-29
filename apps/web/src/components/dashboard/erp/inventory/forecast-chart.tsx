"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { Loader2 } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { ApiError } from "@/lib/api/http";
import { getForecast, type ForecastItem } from "@/lib/api/ai-api";
import { getCatalogProducts, type Product } from "@/lib/api/inventory-api";

type Status =
  | { state: "idle" }
  | { state: "loading" }
  | { state: "error"; message: string }
  | { state: "ready"; data: ForecastItem[]; productId: string };

function stockoutDateLabel(date: string | null): { text: string; color: string } {
  if (!date) return { text: "No risk", color: "bg-emerald-500/10 text-emerald-700 ring-emerald-500/30" };
  const days = Math.ceil(
    (new Date(date).getTime() - Date.now()) / (1000 * 60 * 60 * 24),
  );
  if (days <= 0) return { text: "Imminent", color: "bg-red-600/10 text-red-800 ring-red-600/30" };
  if (days <= 14) return { text: `${days}d`, color: "bg-red-500/10 text-red-700 ring-red-500/30" };
  if (days <= 30) return { text: `${days}d`, color: "bg-amber-500/10 text-amber-700 ring-amber-500/30" };
  return { text: `${days}d`, color: "bg-emerald-500/10 text-emerald-700 ring-emerald-500/30" };
}

export function ForecastChart() {
  const [products, setProducts] = useState<Product[] | null>(null);
  const [productsError, setProductsError] = useState<string | null>(null);
  const [productId, setProductId] = useState("");
  const [status, setStatus] = useState<Status>({ state: "idle" });

  useEffect(() => {
    let cancelled = false;
    getCatalogProducts()
      .then((items) => {
        if (!cancelled) setProducts(items);
      })
      .catch(() => {
        if (!cancelled) setProductsError("Could not load the product catalog.");
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const activeProducts = useMemo(
    () => (products ?? []).filter((product) => product.isActive),
    [products],
  );

  const load = useCallback(async (pid: string) => {
    setStatus({ state: "loading" });
    try {
      const res = await getForecast(pid);
      setStatus({ state: "ready", data: res.data, productId: pid });
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : "Could not load forecast.";
      setStatus({ state: "error", message: msg });
    }
  }, []);

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (productId) void load(productId);
  }

  return (
    <div className="space-y-6">
      <h2 className="font-display text-lg font-semibold tracking-tight text-foreground">
        Demand Forecast
      </h2>
      <form onSubmit={handleSubmit} className="flex items-end gap-3 max-w-md">
        <div className="grid gap-1.5 flex-1">
          <Label htmlFor="forecast-product">Product</Label>
          {productsError ? (
            <p className="text-sm text-destructive">{productsError}</p>
          ) : (
            <Select
              value={productId}
              onValueChange={(value) => {
                setProductId(value);
                setStatus({ state: "idle" });
              }}
            >
              <SelectTrigger
                id="forecast-product"
                size="default"
                className="w-full justify-between"
              >
                <SelectValue placeholder="Select a product" />
              </SelectTrigger>
              <SelectContent>
                {activeProducts.length === 0 && (
                  <SelectItem value="__none__" disabled>
                    No products available
                  </SelectItem>
                )}
                {activeProducts.map((product) => (
                  <SelectItem key={product.id} value={product.id}>
                    {product.sku} — {product.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          )}
        </div>
        <Button
          type="submit"
          disabled={!productId || status.state === "loading"}
        >
          {status.state === "loading" ? (
            <Loader2 aria-hidden="true" className="mr-1.5 size-4 animate-spin" />
          ) : null}
          Forecast
        </Button>
      </form>

      {status.state === "error" && (
        <p className="text-sm text-destructive">{status.message}</p>
      )}

      {status.state === "ready" && status.data.length === 0 && (
        <p className="text-sm text-muted-foreground">
          No forecast data available for this product yet.
        </p>
      )}

      {status.state === "ready" && status.data.length > 0 && (
        <div className="space-y-4">
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {status.data.map((item, i) => {
              const so = stockoutDateLabel(item.stockout_date);
              return (
                <div
                  key={`${item.product_id}-${i}`}
                  className="rounded-xl border border-border bg-card p-5 space-y-3"
                >
                  <div className="flex items-center justify-between">
                    <p className="text-sm font-medium text-foreground">
                      {item.horizon_weeks}-week forecast
                    </p>
                    <Badge variant="outline" className="text-xs">
                      {item.horizon_weeks}wk
                    </Badge>
                  </div>
                  <div className="space-y-1 text-xs text-muted-foreground">
                    <p>
                      Avg daily demand:{" "}
                      <span className="font-medium text-foreground">
                        {parseFloat(item.avg_daily_demand).toFixed(1)}
                      </span>
                    </p>
                    {item.weeks_of_supply && (
                      <p>
                        Weeks of supply:{" "}
                        <span className="font-medium text-foreground">
                          {parseFloat(item.weeks_of_supply).toFixed(1)}w
                        </span>
                      </p>
                    )}
                  </div>
                  <div className="pt-1">
                    <Badge variant="outline" className={`text-xs ring-1 ${so.color}`}>
                      Stockout: {so.text}
                    </Badge>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {status.state === "idle" && !productsError && (
        <p className="text-sm text-muted-foreground">
          Select a product above to view its demand forecast and stockout risk.
        </p>
      )}
    </div>
  );
}