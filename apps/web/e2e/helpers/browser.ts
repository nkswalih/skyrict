import type { Page } from "@playwright/test";

/**
 * Type a 6-digit code into an OtpInput by focusing the first box and typing,
 * letting the component's per-digit handler advance focus. The inputs are
 * `maxLength=1`, so filling a single box with the whole code does not work.
 */
export async function fillOtp(page: Page, label: string, code: string): Promise<void> {
  const first = page.getByLabel(`${label} digit 1`);
  await first.click();
  await page.keyboard.type(code);
}
