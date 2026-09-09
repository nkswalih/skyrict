import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "@/lib/api/http";
import {
    getL3Narrative,
    getLeavePayCorrelation,
    refreshL3Narrative,
} from "@/lib/api/hr-api";

const httpFetch = vi.fn();

/**
 * Mirror the real http helpers: `apiFetch` unwraps `{data}` only when the
 * envelope has it (the L3 relay is a FLAT body — no `data` key), and
 * `apiPost` returns the full response body.
 */
vi.mock("@/lib/api/http", () => ({
    apiFetch: (path: string, options?: RequestInit) =>
        httpFetch(path, options).then((response: Response) =>
            response
                .json()
                .then((json: Record<string, unknown>) =>
                    "data" in json ? json.data : json,
                ),
        ),
    apiList: () => Promise.reject(new Error("not used in this suite")),
    apiPost: (path: string, body?: unknown) =>
        httpFetch(path, body).then((response: Response) => response.json()),
    apiFetchEnvelope: () => Promise.reject(new Error("not used in this suite")),
    buildQueryString: () => "",
    fetchWithSession: (path: string, options?: RequestInit) =>
        httpFetch(path, options),
    ApiError: class ApiError extends Error {
        constructor(
            public status: number,
            message: string,
        ) {
            super(message);
        }
    },
}));

const FLAT_NARRATIVE = {
    status: "ready",
    source: "llm",
    as_of: "2026-09-09",
    kind: "payroll_cost",
    title: "Payroll cost movement",
    summary: "Payroll net rose 4.2%.",
    points: ["Net rose 4.2% vs the prior run.", "Overtime drove $1,200 of the movement."],
    caveat: "Compare against your own records before acting.",
    generated_at: "2026-09-09T04:00:00Z",
    model_used: "narrator-v1",
    figures: { net_delta_pct: "4.2" },
};

describe("HR AI L3 clients", () => {
    beforeEach(() => {
        httpFetch.mockReset();
    });

    it("maps a flat L3 narrative (no data envelope)", async () => {
        httpFetch.mockResolvedValue({
            ok: true,
            status: 200,
            json: () => Promise.resolve(FLAT_NARRATIVE),
        } as Response);

        const narrative = await getL3Narrative("payroll_cost");

        expect(httpFetch).toHaveBeenCalledWith(
            "/api/v1/ai/l3/payroll_cost",
            {},
        );
        expect(narrative).toEqual({
            status: "ready",
            source: "llm",
            asOf: "2026-09-09",
            kind: "payroll_cost",
            title: "Payroll cost movement",
            summary: "Payroll net rose 4.2%.",
            points: [
                "Net rose 4.2% vs the prior run.",
                "Overtime drove $1,200 of the movement.",
            ],
            caveat: "Compare against your own records before acting.",
            generatedAt: "2026-09-09T04:00:00Z",
            modelUsed: "narrator-v1",
            figures: { net_delta_pct: "4.2" },
        });
    });

    it("defaults missing narrative fields safely", async () => {
        httpFetch.mockResolvedValue({
            ok: true,
            status: 200,
            json: () =>
                Promise.resolve({
                    status: "abstained",
                    as_of: "2026-09-09",
                    kind: "compliance_digest",
                }),
        } as Response);

        const narrative = await getL3Narrative("compliance_digest");

        expect(narrative).toEqual({
            status: "abstained",
            source: "",
            asOf: "2026-09-09",
            kind: "compliance_digest",
            title: null,
            summary: null,
            points: [],
            caveat: null,
            generatedAt: null,
            modelUsed: null,
            figures: {},
        });
    });

    it("throws a readable error when the management permission is missing", async () => {
        httpFetch.mockResolvedValue({
            ok: false,
            status: 403,
            json: () => Promise.resolve({ detail: "forbidden" }),
        } as Response);

        await expect(getL3Narrative("compliance_digest")).rejects.toThrow(
            /erp\.hr\.ai\.management is required/,
        );
    });

    it("POSTs a refresh and maps the recomputed narrative", async () => {
        httpFetch.mockResolvedValue({
            ok: true,
            status: 200,
            json: () => Promise.resolve(FLAT_NARRATIVE),
        } as Response);

        const narrative = await refreshL3Narrative("payroll_cost");

        expect(httpFetch).toHaveBeenCalledWith(
            "/api/v1/ai/l3/payroll_cost/refresh",
            {},
        );
        expect(narrative.kind).toBe("payroll_cost");
        expect(narrative.figures).toEqual({ net_delta_pct: "4.2" });
    });

    it("normalizes a 403 refresh to the management message", async () => {
        const thrown = new ApiError(403, "forbidden");
        httpFetch.mockRejectedValue(thrown);

        await expect(refreshL3Narrative("payroll_cost")).rejects.toThrow(
            /erp\.hr\.ai\.management is required to refresh/,
        );
    });

    it("unwraps the leave-pay correlation envelope", async () => {
        httpFetch.mockResolvedValue({
            ok: true,
            status: 200,
            json: () =>
                Promise.resolve({
                    data: {
                        pairs: [
                            {
                                period_start: "2025-04-01",
                                run_code: "RUN-2504",
                                leave_days: 0,
                                overtime: "120.00",
                            },
                            {
                                period_start: "2025-05-01",
                                run_code: "RUN-2505",
                                leave_days: 2,
                                overtime: "310.00",
                            },
                        ],
                    },
                }),
        } as Response);

        const pairs = await getLeavePayCorrelation();

        expect(httpFetch).toHaveBeenCalledWith(
            "/api/v1/ai/hr/l3/leave-pay-correlation",
            {},
        );
        expect(pairs).toEqual([
            {
                periodStart: "2025-04-01",
                runCode: "RUN-2504",
                leaveDays: 0,
                overtime: "120.00",
            },
            {
                periodStart: "2025-05-01",
                runCode: "RUN-2505",
                leaveDays: 2,
                overtime: "310.00",
            },
        ]);
    });

    it("returns an empty pair list when the envelope omits pairs", async () => {
        httpFetch.mockResolvedValue({
            ok: true,
            status: 200,
            json: () => Promise.resolve({ data: {} }),
        } as Response);

        await expect(getLeavePayCorrelation()).resolves.toEqual([]);
    });
});