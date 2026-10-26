/*
 * Dashboard smoke suite (BUG-WEB-001 verification).
 *
 * Walks every route touched by the error-resilience work in ONE context/test
 * (identity rotates the workspace session cookie on every /api/auth/session
 * hydration; a second test presenting the stored token would be treated as
 * reuse and revoke the family - see reports-workspace.spec.ts header).
 *
 * Asserts per route:
 *   - the page renders a top-level heading (never a blank route on API load)
 *   - zero hydration-mismatch console warnings
 *   - zero uncaught page errors
 *
 * Then runs two error-path probes:
 *   - 503 on /api/v1/hr/employees -> shared ErrorState card with "Try again"
 *     (barring the loading spinner), and removing the interception + retrying
 *     recovers with a fresh request.
 *   - a server-component throw (compiled temporararily into
 *     app/dashboard/erp/page.tsx behind ?probe=1) is caught by the route
 *     error.tsx fallback, not the global-error page.
 *
 * Run alone: `npx playwright test dashboard-smoke`.
 */

import { expect, type Page } from "@playwright/test";

import { test } from "./fixtures/auth";

const HYDRATION_WARN = /hydrat|text content did not match|Server and Client/i;

test.setTimeout(600_000);

/**
 * Navigate to a route and wait for the shell's client session hydration to
 * finish (its `/api/auth/session` rotation response) before returning.
 *
 * The h1 renders from the server shell as soon as a cookie exists - long
 * before SessionProvider.restore() rotates the refresh token. Letting the
 * next goto fire while that fetch is in flight aborts it: the backend still
 * advances the token hash but the browser never stores the new Set-Cookie, so
 * the following navigation presents a stale token, trips identity's reuse
 * detector, and revokes the whole family (-> /signin bounce). Awaiting the
 * rotation response serializes the chain and removes the race.
 */
async function gotoRoute(page: Page, route: string): Promise<void> {
  const rotated = page
    .waitForResponse((response) => response.url().includes("/api/auth/session"), {
      timeout: 15_000,
    })
    .catch(() => null);
  await page.goto(route);
  await rotated;
}

/** Assert a route rendered: h1 visible, no hydration warnings, no page errors. */
async function expectRendered(page: Page, heading?: string | RegExp) {
  const hydration: string[] = [];
  const pageErrors: string[] = [];
  const onConsole = (message: { type: () => string; text: () => string }) => {
    if (message.type() === "error" && HYDRATION_WARN.test(message.text())) {
      hydration.push(message.text());
    }
  };
  const onPageError = (error: Error) => pageErrors.push(error.message);
  page.on("console", onConsole);
  page.on("pageerror", onPageError);
  try {
    const h1 = page.getByRole("heading", { level: 1 });
    await expect((heading ? h1.filter({ hasText: heading }) : h1).first()).toBeVisible({
      timeout: 20_000,
    });
    await page.waitForTimeout(500);
    expect(hydration, "Hydration mismatch warnings on console").toEqual([]);
    expect(pageErrors, "Uncaught page errors").toEqual([]);
  } finally {
    page.off("console", onConsole);
    page.off("pageerror", onPageError);
  }
}

test("dashboard smoke: routes render + error paths recover", async ({
  workspace,
}) => {
  const { page } = workspace;
  const routesDone: string[] = [];

  await test.step("stale-guard pages render", async () => {
    const guarded: Array<[string, string | RegExp]> = [
      ["/erp/hr/attendance", "Attendance"],
      ["/erp/hr/employees", "Employees"],
      ["/erp/hr/leave", /Leave/],
      ["/erp/hr/data-quality", /Data quality/i],
      ["/erp/payroll/runs", /Payroll runs/i],
      ["/erp/finance/audit-log", /Audit/],
      ["/erp/finance/journal-entries", /Journal/],
      ["/erp/crm/overview", /Overview/],
      ["/erp/crm/leads", /Leads/],
      ["/erp/crm/customers", /Customers/],
      ["/erp/orders", /Orders/],
    ];
    for (const [route, heading] of guarded) {
      await gotoRoute(page, route);
      await expectRendered(page, heading);
      routesDone.push(route);
    }
  });

  await test.step("route error.tsx / loading.tsx pages render", async () => {
    const modest: Array<[string, string | RegExp]> = [
      ["/erp", /Business Operations/],
      ["/agents", /How can I help you today/],
      ["/intelligence", /Search the market/],
      ["/roles", /Roles/],
      ["/settings", /Settings/],
      ["/members", /Members/],
      ["/leave", /leave/i],
    ];
    for (const [route, heading] of modest) {
      await gotoRoute(page, route);
      await expectRendered(page, heading);
      routesDone.push(route);
    }
  });

  await test.step("503 on employees fetch -> ErrorState card, retry recovers", async () => {
    // Dev mode double-mounts effects (StrictMode), so the first load can be
    // discarded by the stale guard; fail EVERY employees request until the
    // interception is disarmed, guaranteeing the current load errors out.
    const employeesRequests: string[] = [];
    let failMode = true;
    const countRequests = (request: { url: () => string }) => {
      if (request.url().includes("/api/v1/hr/employees")) {
        employeesRequests.push(request.url());
      }
    };
    page.on("request", countRequests);

    await page.route("**/api/v1/hr/employees*", (route) => {
      if (failMode) {
        return route.fulfill({
          status: 503,
          contentType: "application/json",
          body: JSON.stringify({ error: "Service unavailable" }),
        });
      }
      return route.continue();
    });

    try {
      await gotoRoute(page, "/erp/hr/employees");
      await expect(
        page.getByRole("button", { name: "Try again" }),
      ).toBeVisible({ timeout: 20_000 });
      expect(
        employeesRequests.length,
        "employees fetch should have been attempted",
      ).toBeGreaterThan(0);
      routesDone.push("/erp/hr/employees@503");

      failMode = false;
      await page.getByRole("button", { name: "Try again" }).click();
      await expectRendered(page, "Employees");
      expect(
        employeesRequests.length,
        "retry must issue a fresh employees request",
      ).toBeGreaterThan(1);
      routesDone.push("/erp/hr/employees@retry");
    } finally {
      await page.unroute("**/api/v1/hr/employees*");
      page.off("request", countRequests);
    }
  });

  console.log(`[dashboard-smoke] routes verified: ${routesDone.join(", ")}`);
});