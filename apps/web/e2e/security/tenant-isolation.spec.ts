/*
 * SKY-108 cross-tenant isolation: a default-tenant admin token must never
 * resolve data on a foreign (unseeded) tenant subdomain.
 *
 * Core derives the tenant from the Host header in middleware and 404s unknown
 * slugs, so any 2xx carrying default-tenant rows here is a leak. The foreign
 * fixture is the same admin bearer presented against `second.localhost`.
 */

import { expect } from "@playwright/test";

import { securityTest as test } from "../helpers/security-fixtures";

test.describe("tenant isolation", () => {
    test("the admin token works on its own tenant", async ({ admin }) => {
        const settings = await admin.api.raw("/api/v1/payroll/settings");
        expect(settings.status).toBe(200);

        const invoices = await admin.api.raw("/api/v1/finance/invoices");
        expect(invoices.status).toBe(200);
    });

    test("a foreign tenant slug is rejected, not silently routed", async ({
        admin,
        foreign,
    }) => {
        const payroll = await foreign.raw("/api/v1/payroll/settings");
        expect(payroll.status).toBeGreaterThanOrEqual(400);
        expect(payroll.status).toBeLessThan(500);

        const finance = await foreign.raw("/api/v1/finance/invoices");
        expect(finance.status).toBeGreaterThanOrEqual(400);
        expect(finance.status).toBeLessThan(500);

        // The failed cross-tenant probe must not have side effects on the
        // home tenant (no cookie/rotation damage, no family revocation).
        const stillHealthy = await admin.api.raw("/api/v1/finance/invoices");
        expect(stillHealthy.status).toBe(200);
    });
});