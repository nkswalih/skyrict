/*
 * Reports workspace smoke suite (RPT-UI-001).
 *
 * Runs against a fully seeded stack (nginx + identity + core). Identity
 * rotates and invalidates the workspace session cookie on every
 * /api/auth/session hydration, and presenting an already-rotated token is
 * treated as reuse, which revokes the whole session family.
 *
 * The suite uses the worker-scoped `workspace` fixture from fixtures/auth.ts
 * (real UI sign-in as the seeded admin + MFA), then runs as ONE test with
 * sequential page.goto() calls so the same page object walks the rotation
 * chain T0 -> T1 -> ... within a single browser context. Splitting into
 * separate tests (even with a shared worker-scoped context) breaks the chain
 * because Playwright does not propagate cookie-jar updates reliably across
 * page lifecycle events in the rotation window.
 */

import { readFile } from "node:fs/promises";

import { expect, type Page } from "@playwright/test";

import { test } from "./fixtures/auth";

/** Wait for a successful report run result (table with rows, or empty state). */
async function waitForResult(page: Page) {
  await page
    .locator("table")
    .or(page.getByRole("heading", { name: "No rows" }))
    .first()
    .waitFor({ state: "visible", timeout: 20_000 });
}

test("reports workspace smoke: auth, live catalog, and report run", async ({
  workspace,
}) => {
  const { page } = workspace;

  // ── workspace listing ────────────────────────────────────────────────
  await test.step("page loads authenticated", async () => {
    await page.goto("/dashboard/erp/reports");

    // The top bar shows the current page as plain text (not a heading), so
    // match the page heading exactly.
    await expect(
      page.getByRole("heading", { level: 1, name: "Reports", exact: true }),
    ).toBeVisible();

    // Sidebar is present, confirming authentication.
    await expect(
      page.getByRole("link", { name: "Dashboard", exact: true }),
    ).toBeVisible();

    // KPI section is rendered (even if metrics show unavailable).
    await expect(page.getByRole("region", { name: "Report KPIs" })).toBeVisible();
  });

  // ── live catalog ─────────────────────────────────────────────────────
  await test.step("live report catalog loads from Core (no mock fallback)", async () => {
    // The catalog is served from the seeded erp_report_definitions table, so
    // the sample-data banner must NOT be shown and a known report must appear.
    await expect(
      page.getByRole("link", { name: /Pipeline value by stage/ }),
    ).toBeVisible({ timeout: 20_000 });

    // The mock-fallback banner ("Live report data is currently unavailable")
    // must be absent now that the Core data layer is seeded.
    await expect(
      page.getByText(/Live report data is currently unavailable/),
    ).toHaveCount(0);
  });

  // ── parameter-less report run ─────────────────────────────────────────
  await test.step("parameter-less report auto-runs and renders results", async () => {
    await page
      .getByRole("link", { name: /Pipeline value by stage/ })
      .first()
      .click();

    // Report detail heading (the client-side router has already landed on the
    // detail route at this point). The top bar carries the dynamic
    // "· Pipeline value by stage" text, so the match must be exact.
    await expect(
      page.getByRole("heading", {
        level: 1,
        name: "Pipeline value by stage",
        exact: true,
      }),
    ).toBeVisible({ timeout: 15_000 });

    // Pipeline value by stage only declares tenant_id (a server param), which
    // is filtered out of the form, so it auto-runs on first load. Await a
    // rendered results table (with rows) or the "No rows" empty state.
    await waitForResult(page);
  });

  // ── CSV export ───────────────────────────────────────────────────────
  await test.step("CSV export downloads real CSV content (not an empty {})", async () => {
    // Regression: the BFF proxy used to JSON-wrap the text/csv body, so the
    // "downloaded" file contained only "{}". The body must now be the real
    // CSV - at minimum the header row, whether or not the tenant has data.
    const downloadPromise = page.waitForEvent("download", { timeout: 20_000 });
    await page.getByRole("button", { name: "Export CSV" }).click();
    const download = await downloadPromise;

    // Content-Disposition from Core ("attachment; filename=slug-period.csv").
    expect(download.suggestedFilename()).toMatch(/^pipeline_value_by_stage-.+\.csv$/);

    const content = await readFile(await download.path(), "utf8");
    expect(content).toBeTruthy();
    expect(content).not.toBe("{}");
    expect(content).toContain("stage");
    expect(content).toContain("opportunity_count");
    expect(content).toContain("pipeline_value");
  });
});