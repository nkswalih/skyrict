/*
 * Demo ERP end-to-end suite (`pnpm --filter @skyrict/web exec playwright test --project=demo`).
 *
 * What this covers
 * ----------------
 * /demo/erp is a PUBLIC, client-only walkthrough of the ERP on the marketing
 * surface (bare `localhost`, never `{tenant}.localhost`). The suite drives it
 * exactly like a first-time visitor:
 *
 *   - direct entry, `/demo` redirect, every sidebar module deep links
 *   - seeded KPIs, ledger, orders, HR, payroll and inventory records
 *   - interactive CRM CRUD (add / filter / detail / delete / reset)
 *   - kanban stage transitions feeding the CRM overview + dashboard totals
 *   - inventory product creation, filtering and reset
 *   - AI-gated modules and their signup CTA
 *   - mobile drawer navigation
 *   - the "Create real workspace" handoff to the signup surface
 *   - a real 404 for unknown demo paths
 *   - zero /api traffic and a clean console / zero page errors per test
 *
 * Isolation
 * ---------
 * The demo keeps state in localStorage (key `skyrict:demo:v3`). Every test gets
 * a fresh browser context, so tests never share demo state; `reset sample data`
 * is exercised explicitly where it matters. No authenticated fixture is used.
 *
 * The audit + fix history lives in docs/quality/demo-erp-e2e-audit.md.
 */

import {
    expect,
    test as base,
    type Page,
} from "@playwright/test";

const DEMO_STORAGE_KEY = "skyrict:demo:v3";
const BANNER = 'aside[aria-label="Demo environment notice"]';

type Diagnostics = {
    consoleErrors: string[];
    consoleWarnings: string[];
    pageErrors: string[];
    apiRequests: string[];
};

/**
 * Collects everything a demo visitor should never see. The /api tree is
 * *blocked* (not merely observed) so a regression that reaches for the backend
 * fails loudly during the test instead of leaking real traffic.
 */
const test = base.extend<{ diagnostics: Diagnostics }>({
    diagnostics: async ({ page }, use) => {
        const diagnostics: Diagnostics = {
            consoleErrors: [],
            consoleWarnings: [],
            pageErrors: [],
            apiRequests: [],
        };

        page.on("console", (message) => {
            if (message.type() === "error") {
                diagnostics.consoleErrors.push(message.text());
            } else if (message.type() === "warning") {
                diagnostics.consoleWarnings.push(message.text());
            }
        });
        page.on("pageerror", (error) => {
            diagnostics.pageErrors.push(error.message);
        });
        await page.route("**/api/**", (route) => {
            diagnostics.apiRequests.push(route.request().url());
            void route.abort();
        });

        await use(diagnostics);
    },
});

const HYDRATION_ERROR =
    /hydrat|did not match|server rendered|server and client/i;

function hydrationErrors(diagnostics: Diagnostics): string[] {
    return [...diagnostics.consoleErrors, ...diagnostics.pageErrors].filter(
        (message) => HYDRATION_ERROR.test(message),
    );
}

/** Every demo test ends here: local-only, clean console, no uncaught errors. */
function expectClean(diagnostics: Diagnostics): void {
    expect(
        diagnostics.apiRequests,
        "demo must not call /api - all data is client-side",
    ).toEqual([]);
    expect(
        hydrationErrors(diagnostics),
        "hydration mismatch errors on console",
    ).toEqual([]);
    expect(diagnostics.consoleErrors, "console errors").toEqual([]);
    expect(diagnostics.consoleWarnings, "console warnings").toEqual([]);
    expect(diagnostics.pageErrors, "uncaught page errors").toEqual([]);
}

function banner(page: Page) {
    return page.locator(BANNER);
}

function pageHeading(page: Page) {
    return page.locator("main h1").first();
}

async function gotoDemo(page: Page, path: string): Promise<void> {
    const response = await page.goto(path);
    expect(
        response?.status(),
        `${path} should render (demo must never 404)`,
    ).toBe(200);
    await expect(banner(page)).toBeVisible();
    await expect(pageHeading(page)).toBeVisible();
}

async function readDemoState(page: Page) {
    return page.evaluate((key) => {
        const raw = window.localStorage.getItem(key);
        return raw ? JSON.parse(raw) : null;
    }, DEMO_STORAGE_KEY);
}

/**
 * The snapshot is written in a mount effect (DEMO-001 keeps SSR deterministic),
 * so a read that races the first paint can legitimately see `null`. Wait for the
 * seeded version rather than sleeping.
 */
async function waitForDemoState(page: Page) {
    await expect
        .poll(async () => (await readDemoState(page))?.version ?? null)
        .toBe(3);
    const state = await readDemoState(page);
    if (!state) throw new Error("demo snapshot missing after hydration");
    return state;
}

/**
 * Sidebar module → the h1 the demo renders for it. This is also the navigation
 * parity inventory: every ERP sidebar route must land on a real screen.
 */
const MODULE_GROUPS: Array<{ name: string; routes: Array<[string, string]> }> = [
    {
        name: "CRM",
        routes: [
            ["/demo/erp/crm/overview", "CRM Overview"],
            ["/demo/erp/crm/leads", "Leads"],
            ["/demo/erp/crm/opportunities", "Opportunities Kanban"],
            ["/demo/erp/crm/customers", "Customers"],
            ["/demo/erp/crm/contacts", "Contacts"],
            ["/demo/erp/crm/activities", "Activities"],
            [
                "/demo/erp/crm/ai",
                "Autonomous Engine & Machine Intelligence",
            ],
            ["/demo/erp/crm/search", "Search"],
        ],
    },
    {
        name: "Inventory",
        routes: [
            ["/demo/erp/inventory", "Inventory Overview"],
            ["/demo/erp/inventory/products", "Products & Stock"],
            ["/demo/erp/inventory/warehouses", "Warehouses"],
            ["/demo/erp/inventory/stock", "Products & Stock"],
            ["/demo/erp/inventory/movements", "Stock Movements"],
            ["/demo/erp/inventory/alerts", "Stock Alerts"],
            [
                "/demo/erp/inventory/suggestions",
                "Autonomous Engine & Machine Intelligence",
            ],
            [
                "/demo/erp/inventory/anomalies",
                "Autonomous Engine & Machine Intelligence",
            ],
            [
                "/demo/erp/inventory/forecast",
                "Autonomous Engine & Machine Intelligence",
            ],
            [
                "/demo/erp/inventory/abc",
                "Autonomous Engine & Machine Intelligence",
            ],
            ["/demo/erp/inventory/health", "Stock Health"],
        ],
    },
    {
        name: "HR",
        routes: [
            ["/demo/erp/hr", "People & Employees"],
            ["/demo/erp/hr/employees", "People & Employees"],
            ["/demo/erp/hr/departments", "Departments"],
            ["/demo/erp/hr/leave", "Leave"],
            ["/demo/erp/hr/attendance", "Attendance"],
            ["/demo/erp/hr/data-quality", "Data Quality"],
            [
                "/demo/erp/hr/ai-alerts",
                "Autonomous Engine & Machine Intelligence",
            ],
            [
                "/demo/erp/hr/attrition",
                "Autonomous Engine & Machine Intelligence",
            ],
            [
                "/demo/erp/hr/planning",
                "Autonomous Engine & Machine Intelligence",
            ],
            [
                "/demo/erp/hr/compliance",
                "Autonomous Engine & Machine Intelligence",
            ],
            [
                "/demo/erp/hr/correlation",
                "Autonomous Engine & Machine Intelligence",
            ],
        ],
    },
    {
        name: "Finance, payroll, orders, documents",
        routes: [
            ["/demo/erp/finance", "Finance Overview"],
            ["/demo/erp/finance/accounts", "Chart of Accounts"],
            ["/demo/erp/finance/journal-entries", "Journal Entries"],
            ["/demo/erp/finance/fiscal-periods", "Fiscal Periods"],
            ["/demo/erp/finance/invoices", "Invoices"],
            ["/demo/erp/finance/statements", "Financial Statements"],
            ["/demo/erp/finance/controls", "Planning & Policy"],
            ["/demo/erp/finance/audit-log", "Audit Log"],
            [
                "/demo/erp/finance/ai-docs",
                "Autonomous Engine & Machine Intelligence",
            ],
            ["/demo/erp/finance/settings", "Finance Settings"],
            ["/demo/erp/payroll", "Payroll Runs"],
            ["/demo/erp/payroll/runs", "Payroll Runs"],
            ["/demo/erp/payroll/reviews", "Payroll Reviews"],
            ["/demo/erp/payroll/compensation", "Compensation"],
            ["/demo/erp/payroll/settings", "Payroll Settings"],
            [
                "/demo/erp/payroll/automation",
                "Autonomous Engine & Machine Intelligence",
            ],
            [
                "/demo/erp/payroll/anomalies",
                "Autonomous Engine & Machine Intelligence",
            ],
            ["/demo/erp/orders", "Sales Orders"],
            ["/demo/erp/documents", "Documents"],
            ["/demo/erp/documents/list", "All Documents"],
            ["/demo/erp/reports", "Reports"],
        ],
    },
];

/**
 * Account, settings and profile screens. These used to be live-workspace-only,
 * so the demo walkthrough had no way to show the product's admin surface.
 */
const SETTINGS_ROUTES: Array<[string, string]> = [
    ["/demo/erp/settings", "Profile & settings"],
    ["/demo/erp/settings/appearance", "Appearance"],
    ["/demo/erp/settings/workspace", "Workspace preferences"],
    ["/demo/erp/settings/notifications", "Notification preferences"],
    ["/demo/erp/settings/billing", "Plans & billing"],
    ["/demo/erp/settings/security", "Security & access"],
    ["/demo/erp/settings/integrations", "Integrations"],
];

/** AI-gated routes, including the ones the old substring check missed. */
const AI_GATE_ROUTES = [
    "/demo/erp/crm/ai",
    "/demo/erp/inventory/suggestions",
    "/demo/erp/inventory/anomalies",
    "/demo/erp/inventory/forecast",
    "/demo/erp/inventory/abc",
    "/demo/erp/payroll/automation",
    "/demo/erp/payroll/anomalies",
    "/demo/erp/finance/ai-docs",
    "/demo/erp/hr/ai-alerts",
    "/demo/erp/hr/attrition",
    "/demo/erp/hr/planning",
    "/demo/erp/hr/compliance",
    "/demo/erp/hr/correlation",
];

test.describe.configure({ timeout: 180_000 });

test.describe("Demo ERP - public, local-only workspace", () => {
    test("dashboard renders seeded KPIs, navigation and a no-index shell", async ({
        page,
        diagnostics,
    }) => {
        await gotoDemo(page, "/demo/erp");

        await expect(pageHeading(page)).toHaveText("Business Operations");
        await expect(page.locator('meta[name="robots"]')).toHaveAttribute(
            "content",
            /noindex/i,
        );
        await expect(banner(page)).toContainText("Interactive Demo");

        const kpi = (label: string) =>
            page.locator("main div.rounded-xl").filter({ hasText: label });

        // Open pipeline excludes won/lost deals; confirmed orders exclude drafts.
        await expect(kpi("Open Pipeline")).toContainText("₹6,890,000");
        await expect(kpi("Open Pipeline")).toContainText(
            "4 active opportunities",
        );
        await expect(kpi("Confirmed Orders")).toContainText("2");
        await expect(kpi("Confirmed Orders")).toContainText(
            "₹1,605,000 booked volume",
        );
        await expect(kpi("Catalog SKUs")).toContainText("4");
        await expect(kpi("Employees")).toContainText("4");
        await expect(kpi("Employees")).toContainText(
            "4 active of 4 on roster",
        );

        // Quick-access tiles are rewritten from /erp/* to /demo/erp/*.
        for (const tile of [
            "CRM",
            "Orders",
            "Inventory",
            "Finance",
            "HR & Roster",
            "Payroll Runs",
        ]) {
            await expect(
                page.getByRole("link", { name: new RegExp(tile) }).first(),
            ).toHaveAttribute("href", /^\/demo\/erp/);
        }

        // localStorage is seeded, not fetched.
        const state = await waitForDemoState(page);
        expect(state.version).toBe(3);
        expect(state.leads).toHaveLength(4);
        expect(state.opportunities).toHaveLength(5);

        expectClean(diagnostics);
    });

    test("/demo redirects to the workspace walkthrough", async ({
        page,
        diagnostics,
    }) => {
        const response = await page.goto("/demo");
        expect(response?.status()).toBe(200);
        await expect(page).toHaveURL(/\/demo\/erp$/);
        await expect(banner(page)).toBeVisible();
        await expect(pageHeading(page)).toHaveText("Business Operations");

        expectClean(diagnostics);
    });

    test("the demo shell keeps settings, notifications and a demo-safe account menu", async ({
        page,
        diagnostics,
    }) => {
        await gotoDemo(page, "/demo/erp");

        const header = page.getByRole("banner");
        await expect(
            header.getByRole("link", { name: "Settings", exact: true }),
        ).toHaveAttribute("href", "/demo/erp/settings");
        await expect(
            header.getByRole("button", { name: "Notifications (4 unread)" }),
        ).toBeVisible();

        // The demo is not a workspace: no creation affordance in the chrome.
        await expect(
            header.getByRole("button", { name: /Create workspace/ }),
        ).toHaveCount(0);
        await expect(
            header.getByRole("link", { name: /Create workspace/ }),
        ).toHaveCount(0);
        await expect(
            header.getByText("Demo", { exact: true }),
        ).toHaveCount(0);

        // The sidebar footer is the real account row (persona + menu), not a
        // separate demo CTA block.
        const sidebarFooter = page.locator("aside footer");
        await expect(
            sidebarFooter.getByRole("link", { name: /Create real workspace/ }),
        ).toHaveCount(0);
        await expect(
            sidebarFooter.getByRole("link", { name: "Exit demo" }),
        ).toHaveCount(0);

        const account = sidebarFooter.getByRole("button", {
            name: /Priya Sharma/,
        });
        await expect(account).toContainText("priya@skyrict.demo");
        await account.click();

        const menu = page.getByRole("menu", { name: "User menu" });
        await expect(
            menu.getByRole("menuitem", { name: "Profile settings" }),
        ).toHaveAttribute("href", "/demo/erp/settings");
        await expect(
            menu.getByRole("menuitem", { name: "Sign out" }),
        ).toBeVisible();

        // The sample dashboard must not pitch a live deployment.
        await expect(
            page.getByRole("link", { name: /Deploy Live Instance/ }),
        ).toHaveCount(0);

        expectClean(diagnostics);
    });

    test("every settings screen and the profile preview render with the right title", async ({
        page,
        diagnostics,
    }) => {
        for (const [route, heading] of SETTINGS_ROUTES) {
            await gotoDemo(page, route);
            await expect(
                pageHeading(page),
                `${route} should render "${heading}"`,
            ).toHaveText(heading);
            await expect(
                page.locator("header p").first(),
                `${route} topbar title`,
            ).toHaveText(heading);
            await expect(
                page.getByRole("navigation", { name: "Settings sections" }),
            ).toBeVisible();
        }

        // The active section is announced, not just coloured.
        await gotoDemo(page, "/demo/erp/settings/security");
        await expect(
            page
                .getByRole("navigation", { name: "Settings sections" })
                .getByRole("link", { name: "Security" }),
        ).toHaveAttribute("aria-current", "page");

        // The public profile preview is an account screen, not a settings tab.
        await gotoDemo(page, "/demo/erp/profile");
        await expect(pageHeading(page)).toHaveText("Profile");
        await expect(page.locator("header p").first()).toHaveText("Profile");
        await expect(
            page.getByRole("navigation", { name: "Settings sections" }),
        ).toHaveCount(0);

        expectClean(diagnostics);
    });

    test("notification inbox: read, mark all, snooze and preferences links", async ({
        page,
        diagnostics,
    }) => {
        await gotoDemo(page, "/demo/erp");

        const bell = page.getByRole("button", { name: /^Notifications/ });
        await expect(bell).toHaveAccessibleName("Notifications (4 unread)");
        await bell.click();

        const dialog = page.getByRole("dialog");
        await expect(
            dialog.getByRole("heading", { name: "Notifications" }),
        ).toBeVisible();
        const rows = dialog.getByRole("button", {
            name: /^Open notification:/,
        });
        await expect(rows).toHaveCount(6);

        // Opening a notification marks just that one read.
        await rows.first().click();
        await expect(
            dialog.getByRole("heading", { name: "Notification details" }),
        ).toBeVisible();
        let state = await readDemoState(page);
        expect(state.notificationsReadIds).toHaveLength(3);

        await dialog
            .getByRole("button", { name: "Back to all notifications" })
            .click();
        await dialog.getByRole("button", { name: "Mark all read" }).click();
        state = await readDemoState(page);
        expect(state.notificationsReadIds).toHaveLength(6);

        // Closing the modal lets the bell re-render without its badge.
        await page.keyboard.press("Escape");
        await expect(dialog).toBeHidden();
        await expect(bell).toHaveAccessibleName("Notifications");

        // Snoozing removes a row and persists in localStorage.
        await bell.click();
        await expect(rows).toHaveCount(6);
        await dialog
            .getByRole("button", { name: "Snooze", exact: true })
            .first()
            .click();
        await page.getByRole("menuitem", { name: "In 1 hour" }).click();
        await expect(rows).toHaveCount(5);
        state = await readDemoState(page);
        expect(state.notificationsSnoozedIds).toHaveLength(1);

        await expect(
            dialog
                .getByRole("link", { name: "Notification preferences" })
                .last(),
        ).toHaveAttribute("href", "/demo/erp/settings/notifications");

        await page.keyboard.press("Escape");
        await expect(dialog).toBeHidden();

        expectClean(diagnostics);
    });

    test("profile edits save to storage and appear on the public preview", async ({
        page,
        diagnostics,
    }) => {
        await gotoDemo(page, "/demo/erp/settings");

        const name = page.getByLabel("Full name");
        await expect(name).toHaveValue("Priya Sharma");
        await expect(page.getByRole("button", { name: "Save profile" })).toBeDisabled();

        await name.fill("Priya S. Sharma");
        await expect(page.getByRole("button", { name: "Save profile" })).toBeEnabled();
        await page.getByRole("button", { name: "Save profile" }).click();
        await expect(page.getByRole("status")).toContainText(
            "Saved to this browser",
        );

        let state = await readDemoState(page);
        expect(state.profile.fullName).toBe("Priya S. Sharma");

        // The sidebar persona reads the same snapshot.
        await expect(
            page.locator("aside footer").getByRole("button", {
                name: /Priya S\. Sharma/,
            }),
        ).toBeVisible();

        // Persists across a hard reload.
        await page.reload();
        await expect(page.getByLabel("Full name")).toHaveValue("Priya S. Sharma");

        await gotoDemo(page, "/demo/erp/profile");
        await expect(pageHeading(page)).toHaveText("Profile");
        await expect(page.locator("main")).toContainText("Priya S. Sharma");
        await expect(page.locator("main")).toContainText("VP of Operations");

        // Reset restores the seeded persona.
        await banner(page)
            .getByRole("button", { name: /Reset sample data/ })
            .click();
        await expect(page.locator("main")).toContainText("Priya Sharma");
        state = await readDemoState(page);
        expect(state.profile.fullName).toBe("Priya Sharma");

        expectClean(diagnostics);
    });

    test("appearance switches theme, density and motion without touching the live theme", async ({
        page,
        diagnostics,
    }) => {
        await gotoDemo(page, "/demo/erp/settings/appearance");
        await expect(pageHeading(page)).toHaveText("Appearance");

        const shell = page.locator(".theme-demo");
        await expect(shell).toHaveAttribute("data-demo-theme", "light");
        await expect(shell).toHaveAttribute("data-demo-density", "comfortable");
        await expect(shell).toHaveAttribute("data-demo-motion", "full");

        await page.getByRole("radio", { name: /^Dark/ }).click();
        await expect(shell).toHaveAttribute("data-demo-theme", "dark");
        await expect
            .poll(async () =>
                shell.evaluate((element) =>
                    getComputedStyle(element).getPropertyValue("--background").trim(),
                ),
            )
            .toBe("#071b24");

        await page.getByRole("button", { name: "Compact" }).click();
        await expect(shell).toHaveAttribute("data-demo-density", "compact");

        const reduceMotion = page.getByRole("switch", { name: "Reduce motion" });
        await expect(reduceMotion).toHaveAttribute("aria-checked", "false");
        await reduceMotion.click();
        await expect(shell).toHaveAttribute("data-demo-motion", "reduced");

        let state = await readDemoState(page);
        expect(state.preferences.appearance).toEqual({
            theme: "dark",
            density: "compact",
            reduceMotion: true,
        });

        // The choice survives a reload and is restored from the snapshot.
        await page.reload();
        await expect(shell).toHaveAttribute("data-demo-theme", "dark");
        await expect(shell).toHaveAttribute("data-demo-density", "compact");

        // The live workspace theme class is never touched by the demo.
        await expect(page.locator("html")).not.toHaveClass(/\bdark\b/);

        await banner(page)
            .getByRole("button", { name: /Reset sample data/ })
            .click();
        await expect(shell).toHaveAttribute("data-demo-theme", "light");
        await expect(shell).toHaveAttribute("data-demo-motion", "full");
        state = await readDemoState(page);
        expect(state.preferences.appearance.theme).toBe("light");

        expectClean(diagnostics);
    });

    test("workspace settings and notification preferences persist", async ({
        page,
        diagnostics,
    }) => {
        await gotoDemo(page, "/demo/erp/settings/workspace");
        await expect(pageHeading(page)).toHaveText("Workspace preferences");
        await page.getByLabel("Workspace name").fill("Skyrict Demo Holdings");
        await page.getByRole("button", { name: "Save workspace" }).click();
        await expect(page.getByRole("status")).toContainText(
            "Saved to this browser",
        );

        let state = await readDemoState(page);
        expect(state.preferences.workspace.name).toBe("Skyrict Demo Holdings");

        await page.reload();
        await expect(page.getByLabel("Workspace name")).toHaveValue(
            "Skyrict Demo Holdings",
        );
        await expect(
            page.getByText("Skyrict Demo Holdings", { exact: true }).first(),
        ).toBeVisible();

        await gotoDemo(page, "/demo/erp/settings/notifications");
        await expect(pageHeading(page)).toHaveText("Notification preferences");

        const financePush = page.getByRole("switch", {
            name: "Finance & approvals push",
        });
        await expect(financePush).toHaveAttribute("aria-checked", "false");
        await financePush.click();
        await expect(financePush).toHaveAttribute("aria-checked", "true");

        const lockedInApp = page.getByRole("switch", {
            name: "Platform & security in-app",
        });
        await expect(lockedInApp).toBeDisabled();
        await expect(lockedInApp).toHaveAttribute("aria-checked", "true");

        await page.getByRole("button", { name: "Hourly", exact: true }).click();
        await expect(
            page.getByRole("button", { name: "Hourly", exact: true }),
        ).toHaveAttribute("aria-pressed", "true");

        state = await readDemoState(page);
        expect(
            state.preferences.notifications.categories.find(
                (category: { id: string }) => category.id === "finance",
            ).push,
        ).toBe(true);
        expect(state.preferences.notifications.digestFrequency).toBe("hourly");

        // Preferences survive a reload because they are part of the snapshot.
        await page.reload();
        await expect(
            page.getByRole("switch", { name: "Finance & approvals push" }),
        ).toHaveAttribute("aria-checked", "true");

        expectClean(diagnostics);
    });

    test("security revokes a stale session and removes a passkey", async ({
        page,
        diagnostics,
    }) => {
        await gotoDemo(page, "/demo/erp/settings/security");
        await expect(pageHeading(page)).toHaveText("Security & access");

        const staleSession = page.getByRole("button", {
            name: "Revoke session on Surface Laptop 7",
        });
        await expect(staleSession).toBeEnabled();
        await staleSession.click();
        await expect(page.getByRole("status")).toContainText(
            "Session revoked in this demo.",
        );
        await expect(staleSession).toHaveCount(0);

        // The current device can never be revoked from the demo.
        await expect(
            page.getByRole("button", {
                name: "Revoke session on MacBook Pro 16″",
            }),
        ).toBeDisabled();

        let state = await readDemoState(page);
        expect(state.security.sessions).toHaveLength(2);
        expect(state.security.sessions.map((session: { id: string }) => session.id)).not.toContain(
            "sess-windows",
        );

        await page
            .getByRole("button", {
                name: "Remove passkey iPhone 15 Pro · Face ID",
            })
            .click();
        await expect(page.getByRole("status")).toContainText(
            "Passkey removed from this demo.",
        );
        state = await readDemoState(page);
        expect(state.security.passkeys).toHaveLength(1);

        // Two-factor toggles are saved instantly.
        const twoFactor = page.getByRole("switch", {
            name: "Two-factor authentication",
        });
        await expect(twoFactor).toHaveAttribute("aria-checked", "true");
        await twoFactor.click();
        await expect(twoFactor).toHaveAttribute("aria-checked", "false");
        state = await readDemoState(page);
        expect(state.security.twoFactorEnabled).toBe(false);

        expectClean(diagnostics);
    });

    test("integrations connect, filter and stay local", async ({
        page,
        diagnostics,
    }) => {
        await gotoDemo(page, "/demo/erp/settings/integrations");
        await expect(pageHeading(page)).toHaveText("Integrations");
        await expect(page.getByRole("status")).toContainText("6 of 8 connected");

        const logos = page.locator("main article img");
        await expect(logos).toHaveCount(8);
        await expect
            .poll(() =>
                logos.evaluateAll((images) =>
                    images.every((image) => {
                        const img = image as HTMLImageElement;
                        return img.complete && img.naturalWidth > 0;
                    }),
                ),
            )
            .toBe(true);
        const logoBackgrounds = await logos.evaluateAll((images) =>
            images.map(
                (image) =>
                    getComputedStyle(image.parentElement as HTMLElement)
                        .backgroundColor,
            ),
        );
        expect(
            logoBackgrounds.every((background) => background === "rgba(0, 0, 0, 0)"),
            "integration logos must sit on the card, not a tile",
        ).toBe(true);

        await page.getByRole("switch", { name: "Connect Zoho CRM" }).click();
        await expect(page.getByRole("status")).toContainText("7 of 8 connected");
        await expect(
            page.getByRole("switch", { name: "Disconnect Zoho CRM" }),
        ).toHaveAttribute("aria-checked", "true");

        let state = await readDemoState(page);
        expect(
            state.integrations.find(
                (integration: { id: string }) => integration.id === "zoho",
            ).connected,
        ).toBe(true);

        await page.getByRole("button", { name: "Finance", exact: true }).click();
        await expect(
            page.locator("main article").filter({ hasText: "Tally Prime" }),
        ).toHaveCount(1);
        await expect(
            page.locator("main article").filter({ hasText: "Snowflake" }),
        ).toHaveCount(0);

        await page.getByRole("button", { name: "All", exact: true }).click();
        await page.reload();
        await expect(page.getByRole("status")).toContainText("7 of 8 connected");
        state = await readDemoState(page);
        expect(state.integrations).toHaveLength(8);

        expectClean(diagnostics);
    });

    test("demo sign-out confirms, exits to the marketing site and never calls the API", async ({
        page,
    }) => {
        const logoutCalls: string[] = [];
        page.on("request", (request) => {
            if (request.url().includes("/api/auth/logout")) {
                logoutCalls.push(request.url());
            }
        });
        // The harness aborts /api by default; answer it so leaving the demo
        // does not spam console errors while still proving logout is unused.
        await page.route("**/api/**", (route) => {
            if (route.request().url().includes("/api/auth/logout")) {
                logoutCalls.push(route.request().url());
                void route.abort();
                return;
            }
            void route.fulfill({
                status: 200,
                contentType: "application/json",
                body: "{}",
            });
        });

        await gotoDemo(page, "/demo/erp");
        const account = page
            .locator("aside footer")
            .getByRole("button", { name: /Priya Sharma/ });

        await account.click();
        await page.getByRole("menuitem", { name: "Sign out" }).click();
        const dialog = page.getByRole("dialog");
        await expect(
            dialog.getByRole("heading", { name: "Sign out?" }),
        ).toBeVisible();
        await expect(dialog).toContainText(
            "Your sample edits stay saved in this browser",
        );

        // Cancelling keeps the visitor inside the walkthrough.
        await dialog.getByRole("button", { name: "Cancel" }).click();
        await expect(dialog).toBeHidden();
        await expect(page).toHaveURL(/\/demo\/erp$/);

        await account.click();
        await page.getByRole("menuitem", { name: "Sign out" }).click();
        await Promise.all([
            page.waitForURL((url) => new URL(url).pathname === "/"),
            dialog.getByRole("button", { name: "Sign out", exact: true }).click(),
        ]);

        expect(logoutCalls, "demo sign-out must not POST /api/auth/logout").toEqual(
            [],
        );
        // Demo edits are intentionally kept in this browser.
        const stored = await page.evaluate(
            (key) => window.localStorage.getItem(key),
            DEMO_STORAGE_KEY,
        );
        expect(stored).not.toBeNull();
    });

    test("the topbar shows the current page and the page has one h1", async ({
        page,
        diagnostics,
    }) => {
        await gotoDemo(page, "/demo/erp/crm/leads");
        await expect(page.locator("header p").first()).toHaveText("Leads");
        await expect(page.locator("h1")).toHaveCount(1);
        await expect(pageHeading(page)).toHaveText("Leads");

        expectClean(diagnostics);
    });

    for (const group of MODULE_GROUPS) {
        test(`every ${group.name} module deep-links without a session`, async ({
            page,
            diagnostics,
        }) => {
            for (const [route, heading] of group.routes) {
                await gotoDemo(page, route);
                await expect(
                    pageHeading(page),
                    `${route} should render "${heading}"`,
                ).toHaveText(heading);
                await expect(
                    page.getByText("This page could not be found."),
                ).toHaveCount(0);
            }
            expectClean(diagnostics);
        });
    }

    test("CRM leads: add, filter, open detail, delete and reset", async ({
        page,
        diagnostics,
    }) => {
        await gotoDemo(page, "/demo/erp/crm/leads");

        const leadName = `E2E Lead ${Date.now()}`;
        const rows = page.locator("main tbody tr");
        const filter = page.getByPlaceholder("Filter leads by name/company...");

        await expect(rows).toHaveCount(4);

        await page.getByPlaceholder("Lead contact name").fill(leadName);
        await page.getByRole("button", { name: "Add Lead" }).click();
        await expect(rows).toHaveCount(5);
        await expect(rows.first()).toContainText(leadName);
        await expect(rows.first()).toContainText("New Business Inquiry");

        // The add is written through to localStorage.
        let state = await readDemoState(page);
        expect(
            state.leads.map((lead: { name: string }) => lead.name),
        ).toContain(leadName);

        // Filter by name and by company, then show an empty result set.
        await filter.fill("Aarav");
        await expect(rows).toHaveCount(1);
        await expect(rows.first()).toContainText("Aarav Sharma");
        await filter.fill(leadName);
        await expect(rows).toHaveCount(1);
        await filter.fill("no-such-lead-in-the-demo");
        await expect(rows).toHaveCount(0);
        await expect(page.getByText("No leads match this filter.")).toBeVisible();
        await filter.fill("");

        // Detail route.
        await rows.filter({ hasText: leadName }).getByText(leadName).click();
        await expect(page).toHaveURL(/\/demo\/erp\/crm\/leads\/lead-[\w-]+$/);
        await expect(pageHeading(page)).toHaveText(leadName);
        await expect(page.locator("main")).toContainText("New Business Inquiry");
        await expect(page.locator("main")).toContainText("@example.demo");

        await page.getByRole("button", { name: /Back to Leads/ }).click();
        await expect(page).toHaveURL(/\/demo\/erp\/crm\/leads$/);
        await expect(rows).toHaveCount(5);

        // Row deletion is labelled for assistive tech.
        const row = rows.filter({ hasText: leadName });
        await expect(
            row.getByRole("button", { name: `Delete lead ${leadName}` }),
        ).toBeVisible();
        await row.getByRole("button", { name: `Delete lead ${leadName}` }).click();
        await expect(rows).toHaveCount(4);
        state = await readDemoState(page);
        expect(
            state.leads.map((lead: { name: string }) => lead.name),
        ).not.toContain(leadName);

        // Reset from the demo banner restores every seeded lead.
        await banner(page)
            .getByRole("button", { name: /Reset sample data/ })
            .click();
        await expect(rows).toHaveCount(4);
        await expect(page.locator("main")).toContainText("Aarav Sharma");
        await expect(page.locator("main")).toContainText("Ananya Iyer");

        expectClean(diagnostics);
    });

    test("an unknown lead shows a clear not-found state", async ({
        page,
        diagnostics,
    }) => {
        await gotoDemo(page, "/demo/erp/crm/leads/lead-does-not-exist");
        await expect(pageHeading(page)).toHaveText("Lead not found");
        await expect(
            page.getByRole("button", { name: /Back to Leads/ }),
        ).toBeVisible();

        expectClean(diagnostics);
    });

    test("opportunities move through the kanban and agree with the dashboard", async ({
        page,
        diagnostics,
    }) => {
        await gotoDemo(page, "/demo/erp/crm/opportunities");

        const deal = "Raw Material Logistics Contract";
        const card = page
            .locator("main div.rounded-lg")
            .filter({ hasText: deal });

        await expect(page.getByText("prospecting (1)")).toBeVisible();
        await expect(page.getByText("qualified (1)")).toBeVisible();
        await expect(page.getByText("proposal (1)")).toBeVisible();
        await expect(page.getByText("negotiation (1)")).toBeVisible();

        await card.getByRole("button", { name: /Qualify/ }).click();
        await expect(page.getByText("prospecting (0)")).toBeVisible();
        await expect(page.getByText("qualified (2)")).toBeVisible();

        await card.getByRole("button", { name: /Proposal/ }).click();
        await expect(page.getByText("proposal (2)")).toBeVisible();

        await card.getByRole("button", { name: /Negotiate/ }).click();
        await expect(page.getByText("negotiation (2)")).toBeVisible();

        await card.getByRole("button", { name: /Win deal/ }).click();
        await expect(page.getByText("negotiation (1)")).toBeVisible();
        await expect(page.getByText(deal)).toHaveCount(0);

        const state = await readDemoState(page);
        expect(
            state.opportunities.find(
                (opportunity: { name: string }) => opportunity.name === deal,
            ).stage,
        ).toBe("won");

        // Client-side navigation: the demo provider carries the transition and
        // the demo dashboard uses the same open-pipeline definition as CRM.
        const nav = page.getByRole("navigation", { name: "Dashboard" });
        await nav.getByRole("link", { name: "Dashboard", exact: true }).click();
        await expect(page).toHaveURL(/\/demo\/erp$/);

        const dashboardKpi = page
            .locator("main div.rounded-xl")
            .filter({ hasText: "Open Pipeline" });
        await expect(dashboardKpi).toContainText("₹6,170,000");
        await expect(dashboardKpi).toContainText("3 active opportunities");

        await nav.getByRole("link", { name: "CRM", exact: true }).click();
        await expect(page).toHaveURL(/\/demo\/erp\/crm\/overview$/);

        const crmKpi = page
            .locator("main div.rounded-xl")
            .filter({ hasText: "Open Pipeline" });
        // Won: seeded ₹550,000 + this ₹720,000 deal.
        await expect(crmKpi).toContainText("₹6,170,000");
        await expect(crmKpi).toContainText("5 total deals");

        expectClean(diagnostics);
    });

    test("inventory: add and filter a product, persist it to storage and reset", async ({
        page,
        diagnostics,
    }) => {
        await gotoDemo(page, "/demo/erp/inventory/products");

        const rows = page.locator("main tbody tr");
        const name = `E2E Widget ${Date.now()}`;
        await expect(rows).toHaveCount(4);

        await page.getByPlaceholder("Product name to add...").fill(name);
        await page.getByRole("button", { name: "Add Product" }).click();
        await expect(rows).toHaveCount(5);
        await expect(rows.first()).toContainText(name);
        await expect(rows.first()).toContainText("IND-SKU-");

        const state = await readDemoState(page);
        expect(
            state.products.map((product: { name: string }) => product.name),
        ).toContain(name);

        const filter = page.getByPlaceholder("Filter products by name/SKU...");
        await filter.fill(name);
        await expect(rows).toHaveCount(1);
        await expect(rows.first()).toContainText(name);
        await filter.fill("no-such-product-in-the-demo");
        await expect(rows).toHaveCount(0);
        await expect(
            page.getByText("No products match this filter."),
        ).toBeVisible();
        await filter.fill("");

        await banner(page)
            .getByRole("button", { name: /Reset sample data/ })
            .click();
        await expect(rows).toHaveCount(4);
        await expect(page.locator("main")).not.toContainText(name);

        expectClean(diagnostics);
    });

    test("finance, orders, HR and payroll render the seeded records", async ({
        page,
        diagnostics,
    }) => {
        await gotoDemo(page, "/demo/erp/finance");
        await expect(page.locator("main")).toContainText("Revenue Received");
        await expect(page.locator("main")).toContainText("₹1,180,000");
        await expect(page.locator("main")).toContainText(
            "Overdue Receivables",
        );
        await expect(page.locator("main")).toContainText("₹340,000");
        await expect(page.locator("main")).toContainText("JE-2026-104");

        await gotoDemo(page, "/demo/erp/finance/invoices");
        await expect(page.locator("main")).toContainText("INV-2026-042");
        await expect(page.locator("main")).toContainText("overdue");
        await expect(page.locator("main")).toContainText("Global TransLogix");

        await gotoDemo(page, "/demo/erp/orders");
        await expect(page.locator("main")).toContainText("SO-2026-089");
        await expect(page.locator("main")).toContainText(
            "Vastraline Industries Ltd",
        );
        await expect(page.locator("main")).toContainText("passed");

        await gotoDemo(page, "/demo/erp/hr");
        await expect(page.locator("main")).toContainText("EMP-001");
        await expect(page.locator("main")).toContainText("Priya Sharma");
        await expect(page.locator("main")).toContainText("₹285,000");

        await gotoDemo(page, "/demo/erp/payroll");
        await expect(page.locator("main")).toContainText("PR-2026-10");
        await expect(page.locator("main")).toContainText("PR-2026-09");
        // Derived from the editable active roster (285k + 165k + 95k + 125k).
        await expect(page.locator("main")).toContainText("₹670,000");

        expectClean(diagnostics);
    });

    test("AI modules show the gated preview instead of calling the AI stack", async ({
        page,
        diagnostics,
    }) => {
        for (const route of AI_GATE_ROUTES) {
            await gotoDemo(page, route);
            await expect(
                page.getByText("Autonomous AI & Orchestration"),
            ).toBeVisible();
            await expect(
                page.getByRole("heading", {
                    name: "SkyAgent Production Orchestration",
                }),
            ).toBeVisible();
            await expect(
                page
                    .locator("main")
                    .getByRole("link", { name: /Enable on your live workspace/ }),
            ).toHaveAttribute("href", "/signup");
        }

        expectClean(diagnostics);
    });

    test("mobile: banner and sidebar drawer expose the demo modules", async ({
        page,
        diagnostics,
    }) => {
        await page.setViewportSize({ width: 390, height: 844 });
        await gotoDemo(page, "/demo/erp");

        await expect(banner(page)).toBeVisible();
        const openMenu = page.getByRole("button", { name: "Open sidebar" });
        await expect(openMenu).toBeVisible();
        await openMenu.click();

        const nav = page.getByRole("navigation", { name: "Dashboard" });
        await expect(nav.getByRole("link", { name: "CRM", exact: true })).toBeVisible();
        await nav.getByRole("link", { name: "CRM", exact: true }).click();

        await expect(page).toHaveURL(/\/demo\/erp\/crm\/overview$/);
        await expect(pageHeading(page)).toHaveText("CRM Overview");
        await expect(banner(page)).toBeVisible();

        expectClean(diagnostics);
    });

    test("the banner CTA hands off to the signup surface", async ({ page }) => {
        await gotoDemo(page, "/demo/erp");

        const cta = banner(page).getByRole("link", {
            name: /Create real workspace/,
        });
        await expect(cta).toHaveAttribute("href", "/signup");

        await Promise.all([
            page.waitForURL(/\/signup$/),
            cta.click(),
        ]);
        await expect(
            page.getByRole("heading", { name: "Try Skyrict for free" }),
        ).toBeVisible();
    });

    test("unknown demo paths return a real 404", async ({ page }) => {
        const response = await page.goto("/demo/erp/does-not-exist");
        expect(response?.status()).toBe(404);
        await expect(
            page.getByRole("heading", {
                name: "This page could not be found.",
            }),
        ).toBeVisible();
    });

    test("edits survive a full reload without a hydration mismatch", async ({
        page,
        diagnostics,
    }) => {
        await gotoDemo(page, "/demo/erp/crm/leads");
        const name = `Reload Probe ${Date.now()}`;
        await page.getByPlaceholder("Lead contact name").fill(name);
        await page.getByRole("button", { name: "Add Lead" }).click();
        await expect(page.locator("main tbody tr")).toHaveCount(5);

        await page.reload();
        await expect(page.locator("main tbody tr")).toHaveCount(5);
        await expect(page.locator("main")).toContainText(name);

        expect(hydrationErrors(diagnostics), "hydration mismatch on reload").toEqual(
            [],
        );
        expectClean(diagnostics);
    });
});
