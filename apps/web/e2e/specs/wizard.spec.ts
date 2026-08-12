import { expect, test } from "@playwright/test";

import {
  E2E_PASSWORD,
  uniqueEmail,
  uniqueSlug,
} from "../helpers/backend";
import { fillOtp } from "../helpers/browser";
import { watchLogin } from "../helpers/diagnostics";
import { marketingUrl, signupUrl, WEB_PORT } from "../helpers/env";

const signupOrigin = new RegExp(`^http://signup\\.localhost:${WEB_PORT}/signup/?$`);
const signinSurface = new RegExp(`signin\\.localhost:${WEB_PORT}/signin\\?email=`);

test.describe("signup wizard", () => {
  test("marketing sign-up links route to the signup surface", async ({ page }) => {
    await page.goto(marketingUrl("/register"));
    await expect(page).toHaveURL(signupOrigin);

    await page.goto(marketingUrl("/"));
    await page.getByRole("link", { name: "Get started" }).first().click();
    await expect(page).toHaveURL(signupOrigin);
  });

  test("wizard steps without a session show the expired screen", async ({ page }) => {
    for (const path of ["/register/security", "/register/plan", "/register/organization"]) {
      await page.goto(signupUrl(path));
      await expect(
        page.getByRole("heading", { name: "Session expired" }),
      ).toBeVisible();
    }
  });

  test("a visitor can complete the five-step wizard end to end", async ({ page }) => {
    const email = uniqueEmail("wiz");
    const slug = uniqueSlug("wiz");

    // Register the code-send waiter before the step-2 request fires.
    const codeResponse = page.waitForResponse(
      (res) =>
        res.url().includes("/api/auth/code/send") &&
        res.request().method() === "POST",
    );

    await page.goto(signupUrl("/signup"));
    await expect(page.getByRole("heading", { name: "Let's get you set up" })).toBeVisible();
    await expect(page.getByText("Step 1 of 5 · Account")).toBeVisible();

    await page.locator("#email").fill(email);
    await page.getByRole("checkbox", { name: "I'm not a robot" }).check();
    const continueEmail = page.getByRole("button", { name: "Continue with email" });
    await expect(continueEmail).toBeEnabled();
    await continueEmail.click();

    // Step 2 — verification (the code is auto-sent on mount).
    await expect(page.getByRole("heading", { name: "Check your inbox" })).toBeVisible();
    await expect(page.getByText("Step 2 of 5 · Verification")).toBeVisible();
    const sent = (await (await codeResponse).json()) as { code: string | null };
    expect(sent.code, "plaintext OTP is only present with IDENTITY_ENVIRONMENT=test").toBeTruthy();
    await fillOtp(page, "Verification code", sent.code!);

    // Step 3 — security (password + text captcha). The captcha challenge GET
    // fires when the CaptchaChallenge mounts (step 3), so register the waiter
    // BEFORE the step-2 -> step-3 transition to avoid a race with the mount.
    const captchaResponse = page.waitForResponse(
      (res) =>
        res.url().includes("/api/auth/captcha") &&
        res.request().method() === "GET",
    );
    await expect(page).toHaveURL(/\/register\/security\?/);

    await expect(page.getByRole("heading", { name: "Protect your account" })).toBeVisible();
    await expect(page.getByText("Step 3 of 5 · Security")).toBeVisible();
    await page.locator("#password").fill(E2E_PASSWORD);
    await page.locator("#confirmPassword").fill(E2E_PASSWORD);
    const captcha = (await (await captchaResponse).json()) as {
      captchaId: string | null;
      answer: string | null;
    };
    expect(captcha.captchaId, "captcha challenge issued").toBeTruthy();
    expect(captcha.answer, "captcha answer is only present with IDENTITY_ENVIRONMENT=test").toBeTruthy();
    await page.locator("#captcha-input").fill(captcha.answer!);
    await page.getByRole("button", { name: "Continue" }).click();

    // Step 4 — plan (Professional is pre-selected).
    await expect(page.getByRole("heading", { name: "Choose your plan" })).toBeVisible();
    await expect(page.getByText("Step 4 of 5 · Plan")).toBeVisible();
    await page.getByRole("button", { name: "Continue with Professional" }).click();

    // Step 5 — organization.
    await expect(
      page.getByRole("heading", { name: "Tell us about your business" }),
    ).toBeVisible();
    await expect(page.getByText("Step 5 of 5 · Organization")).toBeVisible();
    await page.locator("#companyName").fill("E2E Wizard Inc");
    await page.locator("#workspaceSlug").fill(slug);
    await page.locator("#ownerFullName").fill("E2E Wizard Owner");
    await page.locator("#industry").click();
    await page.getByRole("option", { name: "Technology" }).click();
    await page.locator("#phoneNumber").fill("555-0134");
    await page.locator("#addressLine1").fill("100 Market Street");
    await page.locator("#city").fill("San Francisco");
    await page.locator("#state").fill("CA");
    await page.locator("#postalCode").fill("94103");
    await page.getByRole("checkbox", { name: /I agree to Skyrict's Terms/ }).check();
    await page.getByRole("checkbox", { name: /authorized to set up this organization/ }).check();
    await page.getByRole("button", { name: "Create my workspace" }).click();

    // Provisioning (~10.6s) then hand off to the signin surface.
    await expect(
      page.getByRole("heading", { name: "Setting up your workspace" }),
    ).toBeVisible();
    await expect(
      page.getByRole("heading", { name: "Workspace ready" }),
    ).toBeVisible({ timeout: 30_000 });
    await expect(page).toHaveURL(signinSurface, { timeout: 30_000 });
    await expect(page.getByRole("heading", { name: "Sign in to Skyrict" })).toBeVisible();

    // Sign in — the fresh account is forced into MFA setup.
    const dumpLogin = watchLogin(page);
    await page.locator("#password").fill(E2E_PASSWORD);
    await page.getByRole("button", { name: "Sign in" }).click();
    try {
      await expect(page).toHaveURL(/\/setup-mfa$/, { timeout: 30_000 });
    } catch (error) {
      console.log(`LOGIN_DIAG wizard.spec\n${await dumpLogin()}`);
      throw error;
    }
    await expect(page.getByText("Final step")).toBeVisible();
    await expect(page.getByRole("heading", { name: "Protect your account" })).toBeVisible();
    await expect(page.getByText("Mandatory for your security")).toBeVisible();
  });
});
