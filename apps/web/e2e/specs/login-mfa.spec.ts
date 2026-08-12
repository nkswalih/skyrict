import { expect, test } from "@playwright/test";

import {
  login,
  signupAccountViaBff,
  uniqueEmail,
  verifyMfaChallenge,
  type Account,
} from "../helpers/backend";
import { fillOtp } from "../helpers/browser";
import { normalizeSecret, totp } from "../helpers/crypto";
import { watchLogin } from "../helpers/diagnostics";
import { signinUrl } from "../helpers/env";

const LOGIN_FAILED_MESSAGE = "Invalid email or password.";
const AUTH_ERROR_TYPE = "https://api.skyrict.io/problems/authentication-error";
const RATE_LIMIT_TYPE = "https://api.skyrict.io/problems/rate-limit-exceeded";
const BACKUP_CODE_RE = /^[a-f0-9]{16}$/;

// Must match IDENTITY_RATE_LIMIT_LOGIN in the e2e environment (defaults to 5).
// The e2e env bumps it so serial suites that log in ~6x per account don't 429.
const LOGIN_RATE_LIMIT = Number(process.env.E2E_LOGIN_RATE_LIMIT ?? 5);

test.describe("login hardening", () => {
  test("failed logins expose no account oracle", async ({ request }) => {
    const account = await signupAccountViaBff(request, "harden-msg");

    const known = await login(request, {
      email: account.email,
      password: "definitely-wrong!",
      slug: account.slug,
    }).catch((e) => e);
    expect(known).toMatchObject({
      status: 401,
      message: LOGIN_FAILED_MESSAGE,
      type: AUTH_ERROR_TYPE,
    });

    const unknown = await login(request, {
      email: uniqueEmail("ghost"),
      password: "definitely-wrong!",
      slug: account.slug,
    }).catch((e) => e);
    expect(unknown).toMatchObject({
      status: 401,
      message: LOGIN_FAILED_MESSAGE,
      type: AUTH_ERROR_TYPE,
    });
  });

  test("exhausting the login attempt budget throttles the account for the window", async ({
    request,
  }) => {
    const account = await signupAccountViaBff(request, "harden-limit");

    for (let i = 0; i < LOGIN_RATE_LIMIT; i += 1) {
      const res = await login(request, {
        email: account.email,
        password: `wrong-${i}!`,
        slug: account.slug,
      }).catch((e) => e);
      expect(res, `attempt ${i + 1} should be a uniform 401`).toMatchObject({
        status: 401,
        message: LOGIN_FAILED_MESSAGE,
      });
    }

    const throttled = await login(request, {
      email: account.email,
      password: "wrong-final!",
      slug: account.slug,
    }).catch((e) => e);
    expect(throttled).toMatchObject({ status: 429, type: RATE_LIMIT_TYPE });

    const correct = await login(request, account).catch((e) => e);
    expect(correct, "even the correct password is blocked while throttled").toMatchObject({
      status: 429,
      type: RATE_LIMIT_TYPE,
    });
  });
});

test.describe.serial("MFA enrollment and verification", () => {
  let account: Account;
  let secret = "";
  const backupCodes: string[] = [];

  test.beforeAll(async ({ request }) => {
    account = await signupAccountViaBff(request, "mfa");
  });

  test("a fresh account must enroll MFA before the workspace opens", async ({ page }) => {
    const dumpLogin = watchLogin(page);
    await page.goto(
      signinUrl(account.slug, `/signin?email=${encodeURIComponent(account.email)}`),
    );
    await expect(page.getByRole("heading", { name: "Sign in to Skyrict" })).toBeVisible();

    await page.locator("#password").fill(account.password);
    await page.getByRole("button", { name: "Sign in" }).click();

    // Login reports next_step=mfa.setup and redirects to the enrollment page.
    try {
      await expect(page).toHaveURL(/\/setup-mfa$/, { timeout: 30_000 });
    } catch (error) {
      console.log(`LOGIN_DIAG login-mfa.spec\n${await dumpLogin()}`);
      throw error;
    }
    await expect(page.getByText("Final step")).toBeVisible();
    await expect(page.getByRole("heading", { name: "Protect your account" })).toBeVisible();
    await expect(page.getByText("Mandatory for your security")).toBeVisible();

    // The displayed base32 secret drives the authenticator app.
    const displayed = await page.locator("code").first().textContent();
    expect(displayed).toBeTruthy();
    secret = normalizeSecret(displayed!);
    expect(secret.length).toBeGreaterThanOrEqual(16);

    // A wrong code is rejected without consuming the enrollment.
    await fillOtp(page, "Authenticator code", totp(secret, Date.now() - 30_000));
    await page.getByRole("button", { name: "Verify and continue" }).click();
    await expect(page.getByText("That code doesn't match. Try again.")).toBeVisible();

    await fillOtp(page, "Authenticator code", totp(secret));
    await page.getByRole("button", { name: "Verify and continue" }).click();
    await expect(page.getByText("Authenticator verified. Back up your recovery codes.")).toBeVisible();

    const codes = await page.locator("code").allTextContents();
    expect(codes).toHaveLength(10);
    for (const code of codes) {
      expect(code).toMatch(BACKUP_CODE_RE);
      backupCodes.push(code);
    }

    await page
      .getByRole("button", { name: /I've saved my recovery codes somewhere safe\./ })
      .click();
    await page.getByRole("button", { name: "Finish setup" }).click();

    await expect(page).toHaveURL(new RegExp(`^http://${account.slug}\\.localhost:`), {
      timeout: 30_000,
    });
    await expect(page.getByRole("heading", { name: "Welcome to Skyrict" })).toBeVisible();
  });

  test("sign-in with a TOTP code (wrong code shown, then the right one)", async ({ page }) => {
    expect(secret).toBeTruthy();
    await page.goto(
      signinUrl(account.slug, `/signin?email=${encodeURIComponent(account.email)}`),
    );
    await page.locator("#password").fill(account.password);
    await page.getByRole("button", { name: "Sign in" }).click();

    await expect(page.getByRole("heading", { name: "Two-factor check" })).toBeVisible();

    await fillOtp(page, "Two-factor code", totp(secret, Date.now() - 30_000));
    await page.getByRole("button", { name: "Verify code" }).click();
    await expect(page.getByText("That code didn't match. Try again.")).toBeVisible();

    await fillOtp(page, "Two-factor code", totp(secret));
    await page.getByRole("button", { name: "Verify code" }).click();
    await expect(page).toHaveURL(new RegExp(`^http://${account.slug}\\.localhost:`), {
      timeout: 30_000,
    });
    await expect(page.getByRole("heading", { name: "Welcome to Skyrict" })).toBeVisible();
  });

  test("sign-in with a backup code", async ({ page }) => {
    expect(backupCodes.length).toBe(10);
    await page.goto(
      signinUrl(account.slug, `/signin?email=${encodeURIComponent(account.email)}`),
    );
    await page.locator("#password").fill(account.password);
    await page.getByRole("button", { name: "Sign in" }).click();

    await expect(page.getByRole("heading", { name: "Two-factor check" })).toBeVisible();
    await page.getByRole("button", { name: "Use a backup code" }).click();
    await page.getByLabel("Backup code").fill(backupCodes[0]);
    await page.getByRole("button", { name: "Verify code" }).click();

    await expect(page).toHaveURL(new RegExp(`^http://${account.slug}\\.localhost:`), {
      timeout: 30_000,
    });
    await expect(page.getByRole("heading", { name: "Welcome to Skyrict" })).toBeVisible();
  });

  test("backup codes are single-use", async ({ request }) => {
    // backupCodes[0] was consumed by the browser sign-in above.
    const first = await login(request, account);
    expect(first.next_step).toBe("mfa.verify");
    await expect(
      verifyMfaChallenge(request, {
        mfaToken: first.mfa_token!,
        code: backupCodes[0],
        slug: account.slug,
      }),
    ).rejects.toMatchObject({ status: 401 });

    // A fresh code from the same list still works.
    const second = await login(request, account);
    const ok = await verifyMfaChallenge(request, {
      mfaToken: second.mfa_token!,
      code: backupCodes[1],
      slug: account.slug,
    });
    expect(ok.access_token).toBeTruthy();
    expect(ok.refresh_token).toBeTruthy();
  });
});
