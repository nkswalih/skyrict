import { beforeEach, describe, expect, it, vi } from "vitest";

import {
    getGuardianReport,
    listGuardianReports,
    reviewGuardianReport,
} from "@/lib/api/guardian-api";
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

const REPORT_ID = "11111111-1111-4111-8111-111111111111";

const report = {
    id: REPORT_ID,
    report_week_start: "2026-08-31",
    report_week_end: "2026-09-06",
    summary: "34 events scanned; 2 high-severity flags on user_accounts.",
    total_events_scanned: 34,
    flagged_count: 2,
    status: "generated",
    generated_at: "2026-09-07T06:00:00Z",
};

describe("audit guardian endpoints", () => {
    beforeEach(() => {
        httpMock.mockReset();
    });

    it("lists weekly integrity reports", async () => {
        httpMock.mockResolvedValue({ data: [report], meta: { count: 1 } });

        const result = await listGuardianReports();

        expect(httpMock).toHaveBeenCalledWith(
            "/api/v1/ai/guardian/reports",
            {},
        );
        expect(result.data).toEqual([report]);
    });

    it("fetches one report with its flagged events and evidence", async () => {
        const detail = {
            ...report,
            events: [
                {
                    id: "22222222-2222-4222-8222-222222222222",
                    source_table: "user_accounts",
                    source_id: "33333333-3333-4333-8333-333333333333",
                    event_action: "user.role_granted",
                    severity: "high",
                    reason: "The admin role grant bypassed an approval flow.",
                    evidence: {
                        actor: "m.swalih",
                        record_url:
                            "https://app.skyrict.example/crm/opportunities/33333333-3333-4333-8333-333333333333",
                    },
                    flagged_at: "2026-09-05T14:22:00Z",
                },
            ],
        };
        httpMock.mockResolvedValue(detail);

        const result = await getGuardianReport(REPORT_ID);

        expect(httpMock).toHaveBeenCalledWith(
            `/api/v1/ai/guardian/reports/${REPORT_ID}`,
            {},
        );
        expect(result.events).toHaveLength(1);
    });

    it("marks a generated report as reviewed", async () => {
        const reviewed = { ...report, status: "reviewed" };
        httpMock.mockResolvedValue(reviewed);

        const result = await reviewGuardianReport(REPORT_ID);

        expect(httpMock).toHaveBeenCalledWith(
            `/api/v1/ai/guardian/reports/${REPORT_ID}/review`,
            {
                method: "POST",
                body: "{}",
            },
        );
        expect(result.status).toBe("reviewed");
    });
});