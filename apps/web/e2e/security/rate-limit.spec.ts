/*
 * SKY-108 rate limiting (429 + Retry-After) coverage.
 *
 * Two deterministic windows are exercised end to end (BFF -> backend, header
 * relayed):
 *   1. Login: `rate-limit-probe@skyrict.io` is a dedicated throwaway email -
 *      wrong-password attempts burn only its OWN account bucket, leaving the
 *      real admin/finance budgets alone. RATE_LIMIT_LOGIN=5 (tight stack):
 *      attempts 1-5 pass the limiter, attempt 6 is 429 with Retry-After.
 *   2. AI inventory search: one admin token, RATE_LIMIT_INV_SEARCH_PER_MIN=2 -
 *      two searches answer 2xx, the third is 429 with Retry-After.
 *
 * Retries are impossible by construction here (project retries=0, CI passes
 * --retries=0); a replay would land inside a spent window and flip the count.
 */

import { expect } from "@playwright/test";

import { securityTest as test } from "../helpers/security-fixtures";

const PROBE_EMAIL = "rate-limit-probe@skyrict.io";

function expectRetryAfter(retryAfter: string | null): void {
    expect(retryAfter).not.toBeNull();
    const seconds = Number(retryAfter);
    expect(seconds).toBeGreaterThan(0);
    expect(Number.isFinite(seconds)).toBe(true);
}

test.describe("rate limiting", () => {
    test("login is rate limited and returns Retry-After", async ({
        playwright,
    }) => {
        const ctx = await playwright.request.newContext({
            baseURL: process.env.E2E_BASE_URL ?? "http://default.localhost:3000",
        });
        try {
            for (let attempt = 1; attempt <= 5; attempt += 1) {
                const response = await ctx.post("/api/auth/login", {
                    data: { email: PROBE_EMAIL, password: "wrong-password" },
                    headers: { Origin: "http://default.localhost:3000" },
                });
                expect(
                    response.status(),
                    `attempt ${attempt} hit the limiter early`,
                ).not.toBe(429);
            }

            const limited = await ctx.post("/api/auth/login", {
                data: { email: PROBE_EMAIL, password: "wrong-password" },
                headers: { Origin: "http://default.localhost:3000" },
            });
            expect(limited.status()).toBe(429);
            expectRetryAfter(
                limited.headers()["retry-after"] ?? null,
            );
        } finally {
            await ctx.dispose();
        }
    });

    test("AI inventory search is rate limited and returns Retry-After", async ({
        admin,
    }) => {
        const queries = ["desk", "chair", "monitor"];
        for (const [index, query] of queries.entries()) {
            const result = await admin.api.raw(
                `/api/v1/ai/inventory/search?q=${encodeURIComponent(query)}`,
            );
            if (index < 2) {
                expect(result.status).toBe(200);
            } else {
                expect(result.status).toBe(429);
                expectRetryAfter(result.retryAfter);
            }
        }
    });
});