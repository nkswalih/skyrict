import { beforeEach, describe, expect, it, vi } from "vitest";

import { getRevenueForecast } from "@/lib/api/finance-api";
import type { apiFetch } from "@/lib/api/http";

const apiFetchMock = vi.fn<typeof apiFetch>();

vi.mock("@/lib/api/http", () => ({
    apiFetch: (...args: unknown[]) =>
        apiFetchMock(...(args as Parameters<typeof apiFetch>)),
    apiFetchWithMeta: (...args: unknown[]) =>
        apiFetchMock(...(args as Parameters<typeof apiFetch>)),
    apiFetchEnvelope: (...args: unknown[]) =>
        apiFetchMock(...(args as Parameters<typeof apiFetch>)),
    apiPost: (...args: unknown[]) =>
        apiFetchMock(...(args as Parameters<typeof apiFetch>)),
}));

const WIRE_PAYLOAD = {
    model_version: "holt-damped-v1.4",
    backtest_mape: "17.8200",
    sigma: "27257.5800",
    points: [
        {
            month: "2026-09-01",
            predicted: "573221.4286",
            baseline: "54421.4286",
            pipeline: "518800.0000",
            lower_bound: null,
            upper_bound: null,
            deals: [
                {
                    id: "deal-1000",
                    name: "Big Co",
                    amount: "1000000.0000",
                    probability: 60,
                    expected_close_date: "2026-09-15",
                    weighted: "600000.0000",
                    health: "green",
                    confidence: "0.9",
                    factor: "1.0000",
                    adjusted: "600000.0000",
                },
                {
                    id: "deal-2000",
                    name: "Wobble Co",
                    amount: "80000.0000",
                    probability: 30,
                    expected_close_date: "2026-09-22",
                    weighted: "24000.0000",
                    health: "red",
                    confidence: "1.0",
                    factor: "0.3500",
                    adjusted: "8400.0000",
                },
            ],
        },
        {
            month: "2026-10-01",
            predicted: "133225.7143",
            baseline: "57950.7143",
            pipeline: "75275.0000",
            lower_bound: null,
            upper_bound: null,
            deals: [],
        },
        {
            month: "2026-11-01",
            predicted: "71927.0714",
            baseline: "61127.0714",
            pipeline: "10800.0000",
            lower_bound: null,
            upper_bound: null,
            deals: [],
        },
    ],
    history: [{ month: "2026-08-01", actual: "38000.0000" }],
    pipeline_value: "604875.0000",
} as const;

describe("getRevenueForecast", () => {
    beforeEach(() => {
        apiFetchMock.mockReset();
        apiFetchMock.mockResolvedValue(WIRE_PAYLOAD as never);
    });

    it("coerces Decimal strings to numbers so ordering is numeric not lexical", async () => {
        const forecast = await getRevenueForecast();

        expect(forecast.points.map((point) => point.predicted)).toEqual([
            573221.4286, 133225.7143, 71927.0714,
        ]);
        expect(forecast.points.map((point) => point.pipeline)).toEqual([
            518800, 75275, 10800,
        ]);
        expect(forecast.backtest_mape).toBe(17.82);
        expect(forecast.sigma).toBe(27257.58);
        expect(forecast.pipeline_value).toBe(604875);
        expect(forecast.history[0].actual).toBe(38000);
    });

    it("coerces per-deal health fields and normalizes months without deals", async () => {
        const forecast = await getRevenueForecast();

        const deals = forecast.points[0].deals;
        expect(deals.map((deal) => deal.adjusted)).toEqual([600000, 8400]);
        expect(deals[0].health).toBe("green");
        expect(deals[0].factor).toBe(1);
        expect(deals[1].health).toBe("red");
        expect(deals[1].factor).toBe(0.35);
        expect(forecast.points[1].deals).toEqual([]);
        expect(forecast.points[2].deals).toEqual([]);
    });

    it("picks the true largest forecast and pipeline months after coercion", async () => {
        const forecast = await getRevenueForecast();
        const points = forecast.points;

        const biggestForecast = points.reduce((best, point) =>
            point.predicted > best.predicted ? point : best,
        );
        expect(biggestForecast.month).toBe("2026-09-01");
        expect(biggestForecast.predicted).toBe(573221.4286);

        const biggestPipeline = points.reduce((best, point) =>
            Number(point.pipeline) > Number(best.pipeline) ? point : best,
        );
        expect(biggestPipeline.month).toBe("2026-09-01");
        expect(biggestPipeline.pipeline).toBe(518800);
    });
});
