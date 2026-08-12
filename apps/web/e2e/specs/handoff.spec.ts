import { expect, test, type Page } from "@playwright/test";

import {
  enrollMfaViaApi,
  login,
  signupAccountViaBff,
  type Account,
} from "../helpers/backend";
import { fillOtp } from "../helpers/browser";
import { totp } from "../helpers/crypto";
import { watchLogin } from "../helpers/diagnostics";
import { signinUrl, WEB_PORT } from "../helpers/env";

const SESSION_COOKIE = "skyrict_session";

function signinOrigin(slug: string): string {
  return `http://${slug}.signin.localhost:${WEB_PORT}`;
}

/** Sign in via the browser and land on the tenant workspace (handoff PRG). */
async function signInAs(page: Page, account: Account, secret: string): Promise<void> {
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
    console.log(`LOGIN_DIAG handoff.spec\n${await dumpLogin()}`);
    throw error;
  }
  await fillOtp(page, "Two-factor code", totp(secret));
  await page.getByRole("button", { name: "Verify code" }).click();

  await expect(page).toHaveURL(new RegExp(`^http://${account.slug}\\.localhost:`), {
    timeout: 30_000,
  });
  await expect(page.getByRole("heading", { name: "Welcome to Skyrict" })).toBeVisible();
}

test.describe.serial("cross-origin handoff", () => {
  let owner: Account;
  let other: Account;
  let ownerSecret = "";
  let refreshToken = "";

  test.beforeAll(async ({ request }) => {
    owner = await signupAccountViaBff(request, "handoff");
    other = await signupAccountViaBff(request, "handoff-other");

    const pending = await login(request, owner);
    expect(pending.next_step).toBe("mfa.setup");
    expect(pending.refresh_token).toBeTruthy();
    refreshToken = pending.refresh_token!;

    ownerSecret = (await enrollMfaViaApi(request, owner)).secret;
  });

  test("sign-in completes through the cross-origin form POST (PRG) and lands on the workspace", async ({
    page,
  }) => {
    await signInAs(page, owner, ownerSecret);

    // The host-scoped session cookie is now set on the workspace origin.
    const cookies = await page.context().cookies(`http://${owner.slug}.localhost:${WEB_PORT}`);
    const session = cookies.find((cookie) => cookie.name === SESSION_COOKIE);
    expect(session, "skyrict_session cookie present on the workspace host").toBeTruthy();

    // The URL bar is the workspace host — never signin.
    expect(page.url()).not.toContain("/signin");
  });

  test("a minted handoff token redeems exactly once", async ({ page }) => {
    // Plant the signin-origin session cookie the mint route reads.
    await page.context().addCookies([
      {
        name: SESSION_COOKIE,
        value: refreshToken,
        domain: `${owner.slug}.signin.localhost`,
        path: "/",
        httpOnly: true,
        sameSite: "Lax",
      },
    ]);

    const origin = signinOrigin(owner.slug);
    const mint = await page.request.post(`${origin}/api/auth/handoff/mint`, {
      headers: { Origin: origin },
      data: { redirect: "/" },
    });
    expect(mint.ok()).toBeTruthy();
    const minted = (await mint.json()) as { token: string; workspaceUrl: string };
    expect(minted.token).toBeTruthy();
    expect(minted.workspaceUrl).toMatch(new RegExp(`^http://${owner.slug}\\.localhost:`));

    const redeem = await page.request.post(
      `${minted.workspaceUrl}/api/auth/handoff`,
      {
        headers: { Origin: origin },
        form: { token: minted.token },
      },
    );
    expect(redeem.ok()).toBeTruthy();
    expect(redeem.url()).toMatch(new RegExp(`^http://${owner.slug}\\.localhost:`));
    expect(redeem.url()).not.toContain("/signin");

    // Replaying the consumed token bounces back to the signin surface.
    const replay = await page.request.post(`${minted.workspaceUrl}/api/auth/handoff`, {
      headers: { Origin: origin },
      form: { token: minted.token },
    });
    expect(replay.url()).toContain(`/${owner.slug}.signin.localhost`);
    expect(replay.url()).toContain("/signin");
  });

  test("a token minted for one tenant cannot be redeemed on another", async ({ page }) => {
    await page.context().addCookies([
      {
        name: SESSION_COOKIE,
        value: refreshToken,
        domain: `${owner.slug}.signin.localhost`,
        path: "/",
        httpOnly: true,
        sameSite: "Lax",
      },
    ]);

    const origin = signinOrigin(owner.slug);
    const mint = await page.request.post(`${origin}/api/auth/handoff/mint`, {
      headers: { Origin: origin },
      data: { redirect: "/" },
    });
    expect(mint.ok()).toBeTruthy();
    const { token } = (await mint.json()) as { token: string };

    // Redeem the owner's token against the *other* tenant's workspace host.
    const wrongTenant = await page.request.post(
      `http://${other.slug}.localhost:${WEB_PORT}/api/auth/handoff`,
      {
        headers: { Origin: origin },
        form: { token },
      },
    );
    expect(wrongTenant.url()).toContain(`/${other.slug}.signin.localhost`);
    expect(wrongTenant.url()).toContain("/signin");
  });
});
