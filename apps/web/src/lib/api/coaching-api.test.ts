import { beforeEach, describe, expect, it, vi } from "vitest";

import {
    listCoachingSuggestions,
    reviewCoachingSuggestion,
} from "@/lib/api/coaching-api";
import type { apiFetchBody } from "@/lib/api/http";

const httpMock = vi.fn<typeof apiFetchBody>();

/**
 * Simulate the real http helpers: both `apiFetchBody` and `apiPostBody`
 * return the full response body, so one mock serves both. `apiPostBody`
 * mirrors the real contract (POST with a JSON-serialized body).
 */
vi.mock("@/lib/api/http", async (importOriginal) => {
    const actual =
        await importOriginal<typeof import("@/lib/api/http")>();
    return {
        ...actual,
        apiFetchBody: async (
            _path: string,
            _options: RequestInit = {},
        ) => httpMock(_path, _options),
        apiPostBody: async (_path: string, _body: unknown) =>
            httpMock(_path, {
                method: "POST",
                body: JSON.stringify(_body),
            }),
    };
});

const SUGGESTION_ID = "11111111-1111-4111-8111-111111111111";
const REP_ID = "22222222-2222-4222-8222-222222222222";

const suggestion = {
    id: SUGGESTION_ID,
    rep_user_id: REP_ID,
    opportunity_id: "33333333-3333-4333-8333-333333333333",
    lead_id: null,
    suggestion_type: "coaching",
    title: "Re-engage the stalled Bradfield deal",
    body: "The opportunity has not moved in 14 days. Suggest a fresh follow-up.",
    status: "pending",
    reviewed_by: null,
    reviewed_at: null,
    created_at: "2026-09-01T08:00:00Z",
    updated_at: "2026-09-01T08:00:00Z",
};

describe("sales coach endpoints", () => {
    beforeEach(() => {
        httpMock.mockReset();
    });

    it("fetches the whole coaching queue", async () => {
        httpMock.mockResolvedValue({ data: [suggestion], meta: { queued: 1 } });

        const result = await listCoachingSuggestions();

        expect(httpMock).toHaveBeenCalledWith(
            "/api/v1/ai/coaching/suggestions",
            {},
        );
        expect(result.data).toEqual([suggestion]);
    });

    it("scopes the queue to a single rep when rep_user_id is given", async () => {
        httpMock.mockResolvedValue({ data: [suggestion], meta: { queued: 1 } });

        await listCoachingSuggestions(REP_ID);

        expect(httpMock).toHaveBeenCalledWith(
            `/api/v1/ai/coaching/suggestions?rep_user_id=${REP_ID}`,
            {},
        );
    });

    it("accepts a suggestion through the review endpoint", async () => {
        const reviewed = {
            ...suggestion,
            status: "accepted",
            reviewed_at: "2026-09-02T09:30:00Z",
        };
        httpMock.mockResolvedValue(reviewed);

        const result = await reviewCoachingSuggestion(
            SUGGESTION_ID,
            "accepted",
        );

        expect(httpMock).toHaveBeenCalledWith(
            `/api/v1/ai/coaching/suggestions/${SUGGESTION_ID}/review`,
            {
                method: "POST",
                body: JSON.stringify({ status: "accepted" }),
            },
        );
        expect(result).toEqual(reviewed);
    });

    it("dismisses a suggestion through the review endpoint", async () => {
        const dismissed = {
            ...suggestion,
            status: "dismissed",
            reviewed_at: "2026-09-02T09:45:00Z",
        };
        httpMock.mockResolvedValue(dismissed);

        const result = await reviewCoachingSuggestion(
            SUGGESTION_ID,
            "dismissed",
        );

        expect(httpMock).toHaveBeenCalledWith(
            `/api/v1/ai/coaching/suggestions/${SUGGESTION_ID}/review`,
            {
                method: "POST",
                body: JSON.stringify({ status: "dismissed" }),
            },
        );
        expect(result).toEqual(dismissed);
    });
});