/**
 * AI features API client (SKY-68).
 *
 * NL queries, restock suggestions, anomaly feed, forecasts, ABC classification.
 * All calls go through /api/v1/ai/* which the BFF proxies to core's AI router,
 * which then forwards to the ai-agent microservice.
 */

import { apiFetchBody, apiPostBody } from "@/lib/api/http";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface NlQueryResponse {
  answer: string;
  data: Record<string, unknown> | null;
  model_used: string | null;
  latency_ms: number;
}

export interface SuggestionItem {
  id: string;
  product_id: string;
  warehouse_id: string;
  current_stock: string;
  reorder_point: string;
  suggested_qty: string;
  estimated_cost: string | null;
  reason: string;
  confidence: string;
  status: "pending" | "approved" | "rejected" | "expired";
  review_note: string | null;
  created_at: string;
}

export interface SuggestionListResponse {
  data: SuggestionItem[];
  meta: { total: number; pending: number };
}

export interface ScanResponse {
  created: number;
  skipped_pending: number;
  considered: number;
}

export interface AnomalyItem {
  id: string;
  anomaly_type: string;
  severity: "low" | "medium" | "high" | "critical";
  title: string;
  description: string;
  affected_product_id: string | null;
  affected_warehouse_id: string | null;
  related_movement_ids: string[];
  status: "open" | "resolved" | "dismissed" | "escalated";
  resolution_note: string | null;
  created_at: string;
}

export interface AnomalyListResponse {
  data: AnomalyItem[];
  meta: { total: number; open: number; high_severity: number };
}

export interface ForecastItem {
  product_id: string;
  horizon_weeks: number;
  avg_daily_demand: string;
  weeks_of_supply: string | null;
  stockout_date: string | null;
}

export interface AbcItem {
  product_id: string;
  product_name: string;
  sku: string;
  revenue: string;
  revenue_share: string;
  band: "A" | "B" | "C";
}

// ---------------------------------------------------------------------------
// NL Query
// ---------------------------------------------------------------------------

export async function queryInventory(question: string): Promise<NlQueryResponse> {
  return apiPostBody<NlQueryResponse>("/api/v1/ai/inventory/query", { query: question });
}

// ---------------------------------------------------------------------------
// Restock Suggestions
// ---------------------------------------------------------------------------

export async function listSuggestions(): Promise<SuggestionListResponse> {
  return apiFetchBody<SuggestionListResponse>("/api/v1/ai/suggestions");
}

export async function triggerScan(): Promise<ScanResponse> {
  return apiPostBody<ScanResponse>("/api/v1/ai/suggestions/scan", {});
}

export async function approveSuggestion(
  id: string,
  note?: string,
): Promise<SuggestionItem> {
  return apiPostBody<SuggestionItem>(`/api/v1/ai/suggestions/${id}/approve`, { note });
}

export async function rejectSuggestion(
  id: string,
  note?: string,
): Promise<SuggestionItem> {
  return apiPostBody<SuggestionItem>(`/api/v1/ai/suggestions/${id}/reject`, { note });
}

// ---------------------------------------------------------------------------
// Anomalies
// ---------------------------------------------------------------------------

export async function listAnomalies(): Promise<AnomalyListResponse> {
  return apiFetchBody<AnomalyListResponse>("/api/v1/ai/anomalies");
}

export async function triggerAnomalyScan(): Promise<{ detected: number; duplicates_skipped: number }> {
  return apiPostBody("/api/v1/ai/anomalies/scan", {});
}

export async function resolveAnomaly(id: string, note?: string): Promise<void> {
  await apiPostBody(`/api/v1/ai/anomalies/${id}/resolve`, { note });
}

export async function dismissAnomaly(id: string, note?: string): Promise<void> {
  await apiPostBody(`/api/v1/ai/anomalies/${id}/dismiss`, { note });
}

export async function escalateAnomaly(id: string, note?: string): Promise<void> {
  await apiPostBody(`/api/v1/ai/anomalies/${id}/escalate`, { note });
}

// ---------------------------------------------------------------------------
// Forecast
// ---------------------------------------------------------------------------

export async function getForecast(productId: string): Promise<{ data: ForecastItem[] }> {
  return apiFetchBody(`/api/v1/ai/forecast/${productId}`);
}

// ---------------------------------------------------------------------------
// ABC Classification
// ---------------------------------------------------------------------------

export async function listAbcClassifications(): Promise<{ data: AbcItem[] }> {
  return apiFetchBody("/api/v1/ai/abc");
}

export async function getAbcSummary(): Promise<{ data: Record<string, number> }> {
  return apiFetchBody("/api/v1/ai/abc/summary");
}
