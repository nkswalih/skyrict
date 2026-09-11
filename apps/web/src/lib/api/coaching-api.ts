/**
 * Sales Coach AI API client (SKY-90 wave 2).
 *
 * Drives the coaching suggestion queue behind /api/v1/ai/coaching/* - the BFF
 * proxies those paths to core's AI router, which forwards to the ai-agent
 * microservice after enforcing the erp.ai.coaching.read / review permissions.
 * Coaching responses deliberately carry no CRM-record evidence: the suggestion
 * body is enough for a manager to accept or dismiss, and record-level evidence
 * stays inside the service.
 */

import { apiFetchBody, apiPostBody, buildQueryString } from "@/lib/api/http";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type CoachingSuggestionStatus =
    | "pending"
    | "viewed"
    | "accepted"
    | "dismissed";

export type CoachingReviewDecision = "accepted" | "dismissed";

export interface CoachingSuggestionItem {
    id: string;
    rep_user_id: string;
    opportunity_id: string | null;
    lead_id: string | null;
    suggestion_type: string;
    title: string;
    body: string;
    status: CoachingSuggestionStatus;
    reviewed_by: string | null;
    reviewed_at: string | null;
    created_at: string;
    updated_at: string;
}

export interface CoachingSuggestionListResponse {
    data: CoachingSuggestionItem[];
    meta: Record<string, unknown>;
}

// ---------------------------------------------------------------------------
// API functions
// ---------------------------------------------------------------------------

const COACHING_BASE = "/api/v1/ai/coaching/suggestions";

/**
 * List the coaching suggestion queue.
 *
 * Without a filter the whole manager queue is returned; pass a rep id to
 * scope the view to one rep's suggestions.
 */
export async function listCoachingSuggestions(
    repUserId?: string,
): Promise<CoachingSuggestionListResponse> {
    return apiFetchBody<CoachingSuggestionListResponse>(
        `${COACHING_BASE}${buildQueryString({
            rep_user_id: repUserId ?? null,
        })}`,
    );
}

/**
 * Accept or dismiss a coaching suggestion (manager review).
 */
export async function reviewCoachingSuggestion(
    suggestionId: string,
    status: CoachingReviewDecision,
): Promise<CoachingSuggestionItem> {
    return apiPostBody<CoachingSuggestionItem>(
        `${COACHING_BASE}/${suggestionId}/review`,
        { status },
    );
}