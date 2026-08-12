import type { Page, Response } from "@playwright/test";

/**
 * Watch the browser during a login attempt and produce a diagnostics dump on
 * demand (logged when a login assertion times out). Temporary wiring to
 * surface the exact /api/auth/login failure in CI — remove once the login
 * defect is fixed.
 */
export function watchLogin(page: Page) {
  const requests: { url: string; status: number; body: string }[] = [];
  const pageErrors: string[] = [];
  const requestFailures: string[] = [];
  const consoleErrors: string[] = [];

  page.on("response", (res: Response) => {
    const url = res.url();
    if (!url.includes("/api/auth/login") && !url.includes("/api/auth/mfa")) return;
    void res
      .text()
      .then((body) => requests.push({ url, status: res.status(), body: body.slice(0, 500) }))
      .catch(() => requests.push({ url, status: res.status(), body: "<unreadable>" }));
  });

  page.on("pageerror", (error) => pageErrors.push(String(error)));

  page.on("requestfailed", (request) =>
    requestFailures.push(
      `${request.method()} ${request.url()} :: ${request.failure()?.errorText ?? "?"}`,
    ),
  );

  page.on("console", (message) => {
    if (message.type() === "error") consoleErrors.push(message.text().slice(0, 500));
  });

  return async (): Promise<string> => {
    const alertText = await page
      .locator('[role="alert"]')
      .first()
      .textContent()
      .catch(() => null);
    return JSON.stringify(
      { alertText, requests, pageErrors, requestFailures, consoleErrors },
      null,
      2,
    );
  };
}
