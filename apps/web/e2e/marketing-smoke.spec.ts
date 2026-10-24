/*
 * Marketing smoke spec (BUG-WEB-001 verification).
 *
 * Walks the public marketing routes in ONE context/test and asserts:
 *   - the page renders a top-level heading (never a blank route),
 *   - zero hydration-mismatch console warnings,
 *   - zero uncaught page errors.
 *
 * This guards the "Demo" -> "Try demo" CTA label change: if server-rendered
 * HTML and client JS ever diverge again (different builds deployed out of
 * sync), React will log a hydration mismatch and this test fails, blocking
 * the production merge.
 *
 * Run alone: `npx playwright test marketing-smoke`.
 */

import { expect, test, type Page } from "@playwright/test";

const HYDRATION_WARN = /hydrat|text content did not match|Server and Client/i;

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

test("marketing smoke: home, pricing, product render without hydration mismatch", async ({
  page,
}) => {
  const routes: Array<[string, string | RegExp]> = [
    ["/", "Run the business"],
    ["/pricing", "Pricing for a business that runs on live records."],
    ["/product", /The work/],
  ];

  for (const [route, heading] of routes) {
    await page.goto(route, { waitUntil: "networkidle" });
    await expectRendered(page, heading);
  }
});
