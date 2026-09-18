/*
 * SKY-108 denial (403) coverage: permission enforcement at the API boundary.
 *
 * Probes that the seeded finance_viewer role can read finance data but is
 * denied payroll (erp.payroll.*) endpoints with 403, and that an anonymous
 * caller gets 401 on the same surface.
 */

import { expect } from "@playwright/test";

import { BffApi } from "../helpers/api";
import { securityTest as test } from "../helpers/security-fixtures";

test.describe("denial / RBAC", () => {
    test("finance viewer can read finance data", async ({ finance }) => {
        const result = await finance.raw("/api/v1/finance/invoices");
        expect(result.status).toBe(200);
    });

    test("finance viewer is denied payroll read with 403", async ({
        finance,
    }) => {
        const result = await finance.raw("/api/v1/payroll/runs");
        expect(result.status).toBe(403);
    });

    test("finance viewer is denied payroll write with 403", async ({
        finance,
    }) => {
        const result = await finance.raw("/api/v1/payroll/runs", {
            method: "POST",
            body: JSON.stringify({}),
        });
        expect(result.status).toBe(403);
    });

    test("anonymous caller is rejected with 401", async ({ playwright }) => {
        const ctx = await playwright.request.newContext({
            baseURL: process.env.E2E_BASE_URL ?? "http://default.localhost:3000",
        });
        try {
            const api = new BffApi(ctx);
            const finance = await api.raw("/api/v1/finance/invoices");
            expect(finance.status).toBe(401);

            const payroll = await api.raw("/api/v1/payroll/runs");
            expect(payroll.status).toBe(401);
        } finally {
            await ctx.dispose();
        }
    });
});