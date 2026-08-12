import { expect, test, type Page } from "@playwright/test";

import {
  enrollMfaViaApi,
  signupAccountViaBff,
  uniqueEmail,
  type Account,
} from "../helpers/backend";
import { fillOtp } from "../helpers/browser";
import { totp } from "../helpers/crypto";
import { watchLogin } from "../helpers/diagnostics";
import { signinUrl, workspaceUrl } from "../helpers/env";

/** Sign in via the browser and land on the tenant workspace (handoff PRG). */
async function signInAs(page: Page, account: Account, secret: string) {
  const dumpLogin = watchLogin(page);
  await page.goto(
    signinUrl(account.slug, `/signin?email=${encodeURIComponent(account.email)}`),
  );
  await expect(page.getByRole("heading", { name: "Sign in to Skyrict" })).toBeVisible();
  await page.locator("#password").fill(account.password);
  await page.getByRole("button", { name: "Sign in" }).click();

  try {
    await expect(page.getByRole("heading", { name: "Two-factor check" })).toBeVisible();
  } catch (error) {
    console.log(`LOGIN_DIAG dashboard.spec\n${await dumpLogin()}`);
    throw error;
  }
  await fillOtp(page, "Two-factor code", totp(secret));
  await page.getByRole("button", { name: "Verify code" }).click();

  await expect(page).toHaveURL(new RegExp(`^http://${account.slug}\\.localhost:`), {
    timeout: 30_000,
  });
  await expect(page.getByRole("heading", { name: "Welcome to Skyrict" })).toBeVisible();
}

test.describe.serial("workspace dashboard", () => {
  let owner: Account;
  let ownerSecret = "";

  test.beforeAll(async ({ request }) => {
    owner = await signupAccountViaBff(request, "dash");
    const enrolled = await enrollMfaViaApi(request, owner);
    ownerSecret = enrolled.secret;
  });

  test("the owner reaches the dashboard via handoff and the nav is present", async ({
    page,
  }) => {
    await signInAs(page, owner, ownerSecret);

    // The URL bar is the workspace host — never signin.
    await expect(page).toHaveURL(new RegExp(`^http://${owner.slug}\\.localhost:`));
    expect(page.url()).not.toContain("/signin");

    for (const label of ["Overview", "Members", "AI Agents", "ERP", "Intelligence"]) {
      await expect(page.getByRole("link", { name: label })).toBeVisible();
    }

    await page.getByRole("link", { name: "AI Agents" }).click();
    await expect(page.getByRole("heading", { name: "AI Agents" })).toBeVisible();

    await page.goto(workspaceUrl(owner.slug, "/dashboard/erp"));
    await expect(page.getByRole("heading", { name: "ERP" })).toBeVisible();

    await page.goto(workspaceUrl(owner.slug, "/dashboard/intelligence"));
    await expect(page.getByRole("heading", { name: "Market Intelligence" })).toBeVisible();
  });

  test("members page creates, lists, and expires an invitation", async ({ page }) => {
    await signInAs(page, owner, ownerSecret);
    await page.goto(workspaceUrl(owner.slug, "/dashboard/members"));
    await expect(page.getByRole("heading", { name: "Members" })).toBeVisible();
    await expect(page.getByText("Invite a member")).toBeVisible();

    const email = uniqueEmail("member");
    await page.locator("#invite-email").fill(email);
    await page.selectOption("#invite-role", "standard_user");
    await page.getByRole("button", { name: "Send invite" }).click();

    await expect(
      page.getByText(`Invitation sent to ${email} as standard_user`),
    ).toBeVisible();
    await expect(
      page.getByText(new RegExp(`${owner.slug}\\.signin\\.localhost:?\\d*/invite\\?token=`)),
    ).toBeVisible();

    const row = page.locator("li", { hasText: email });
    await expect(row.getByText("Pending")).toBeVisible();
    await row.getByRole("button", { name: "Expire" }).click();
    await expect(row.getByText("Expired")).toBeVisible();
  });
});
