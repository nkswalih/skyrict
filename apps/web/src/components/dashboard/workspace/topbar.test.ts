import { describe, expect, it } from "vitest";

import { resolvePageTitle } from "@/lib/page-title";

describe("resolvePageTitle", () => {
    it("resolves known workspace titles", () => {
        expect(resolvePageTitle("/dashboard")).toBe("Overview");
        expect(resolvePageTitle("/dashboard/erp")).toBe("Business Operations");
        expect(resolvePageTitle("/dashboard/agents")).toBe("AI Agents");
        expect(resolvePageTitle("/dashboard/settings/notifications")).toBe(
            "Notification preferences",
        );
    });

    it("filters hyphenated UUID segments from the breadcrumb", () => {
        const orderId = "13071d6b-8434-460d-9aea-d894debbb8cf";
        expect(resolvePageTitle(`/dashboard/erp/orders/${orderId}`)).toBe(
            "Business Operations · Orders",
        );
        expect(
            resolvePageTitle(`/dashboard/erp/crm/customers/${orderId}`),
        ).toBe("Business Operations · Crm · Customers");
    });

    it("keeps human-readable slugs in the breadcrumb", () => {
        expect(resolvePageTitle("/dashboard/erp/orders/acme-bulk-order")).toBe(
            "Business Operations · Orders · Acme Bulk Order",
        );
    });

    it("keeps short non-UUID segments", () => {
        expect(resolvePageTitle("/dashboard/agents/c/abc")).toBe(
            "AI Agents · C · Abc",
        );
    });

    it("resolves short page-level titles for the public demo", () => {
        expect(resolvePageTitle("/demo")).toBe("Interactive Demo");
        expect(resolvePageTitle("/demo/erp")).toBe("Business Operations");
        expect(resolvePageTitle("/demo/erp/crm/leads")).toBe("Leads");
        expect(resolvePageTitle("/demo/erp/crm/overview")).toBe("CRM Overview");
        expect(resolvePageTitle("/demo/erp/inventory/abc")).toBe("ABC");
        expect(resolvePageTitle("/demo/erp/crm/leads/lead-1")).toBe(
            "Lead Detail",
        );
        expect(resolvePageTitle("/demo/erp/hr/data-quality")).toBe(
            "Data Quality",
        );
    });

    it("resolves account and settings titles for the public demo", () => {
        expect(resolvePageTitle("/demo/erp/profile")).toBe("Profile");
        expect(resolvePageTitle("/demo/erp/settings")).toBe(
            "Profile & settings",
        );
        expect(resolvePageTitle("/demo/erp/settings/appearance")).toBe(
            "Appearance",
        );
        expect(resolvePageTitle("/demo/erp/settings/workspace")).toBe(
            "Workspace preferences",
        );
        expect(resolvePageTitle("/demo/erp/settings/notifications")).toBe(
            "Notification preferences",
        );
        expect(resolvePageTitle("/demo/erp/settings/billing")).toBe(
            "Plans & billing",
        );
        expect(resolvePageTitle("/demo/erp/settings/security")).toBe(
            "Security & access",
        );
        expect(resolvePageTitle("/demo/erp/settings/integrations")).toBe(
            "Integrations",
        );
    });
});
