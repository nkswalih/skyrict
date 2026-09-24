/*
 * Worker-scoped authenticated session fixture for the multi-tenant E2E
 * harness.
 *
 * Every worker gets ONE browser context that signs in as the seeded tenant
 * admin through the real signin surface (BFF login + mandatory MFA whatever
 * path it takes - challenge when already enrolled, fresh enrollment
 * otherwise). Because identity rotates the refresh token on every
 * /api/auth/session hydration and treats an already-rotated token as reuse
 * (revoking the whole session family), each worker walks its OWN token chain
 * inside a single context; never load the same storage-state snapshot into
 * two contexts (see playwright.config.ts).
 *
 * Tests receive the live `page` plus a `refreshSession()` handle that
 * re-hydrates through the BFF for deliberate single rotations. The suite runs
 * as ONE sequential test, so each navigation's own single-flight session
 * restore is the only rotation source - the harness never auto-refreshes
 * alongside the app's 401 recovery (that race revokes the token family).
 */

import { mkdirSync, writeFileSync } from "node:fs";

import {
  expect,
  test as base,
  type BrowserContext,
  type Page,
} from "@playwright/test";

import {
  TOTP_SECRET_FILE,
  assertSessionReachesBff,
  completeMfaChallenge,
  enrollMfaAndFinish,
  installMfaSecretCapture,
  readEnrolledSecret,
  refreshSession,
  signInWithPassword,
  waitForWorkspaceSettled,
  whichMfaPath,
} from "../helpers/auth-flow";
import { signinUrl, workspaceUrl } from "../support/urls";

export interface AuthSession {
  /** Tenant slug the fixture authenticated against. */
  slug: string;
  context: BrowserContext;
  page: Page;
  /** Re-hydrate the session through the BFF (rotates the refresh token). */
  refreshSession(): Promise<void>;
}

const DEFAULT_SLUG = process.env.E2E_TENANT_SLUG ?? "default";

export const test = base.extend<{}, { workspace: AuthSession }>({
  workspace: [
    async ({ browser }, use) => {
      const slug = DEFAULT_SLUG;
      const email = process.env.E2E_ADMIN_EMAIL ?? "admin@skyrict.io";
      const password = process.env.E2E_ADMIN_PASSWORD ?? "Admin123!";
      const enrolledSecret = readEnrolledSecret();

      const context = await browser.newContext({
        baseURL: workspaceUrl(slug),
        viewport: { width: 1280, height: 800 },
      });
      const page = await context.newPage();

      // Capture the MFA setup response before sign-in: the setup-MFA page
      // calls the API on mount, so the fresh-enrollment arm below needs the
      // listener attached before the handoff happens. Harmless on the
      // challenge path.
      const getMfaSecret = installMfaSecretCapture(page);

      await page.goto(`${signinUrl(slug)}/signin`);
      await signInWithPassword(page, email, password);

      const path = await whichMfaPath(page);
      if (path === "challenge") {
        expect(
          enrolledSecret,
          "E2E_TOTP_SECRET must be set when the admin already has MFA enrolled.",
        ).toBeTruthy();
        await completeMfaChallenge(page, enrolledSecret);
      } else {
        // Persist the worker's OWN enrollment secret, mirroring auth.setup.ts:
        // a worker that lands on the enrollment path must leave the persisted
        // secret aligned with the server's, or the NEXT worker's challenge arm
        // verifies a stale secret and bounces with "That code didn't match"
        // for every window.
        mkdirSync("e2e/.auth", { recursive: true });
        await enrollMfaAndFinish(page, {
          secretGetter: getMfaSecret,
          knownSecret: enrolledSecret,
          onWritten: (secret) => writeFileSync(TOTP_SECRET_FILE, secret, "utf8"),
        });
      }

      // Let the workspace shell finish its own session hydration before the
      // test's first navigation: the shell rotates the refresh token once on
      // mount, and a goto that races that rotation would present a consumed
      // token and trip the backend's reuse detector.
      await waitForWorkspaceSettled(page);

      // Fail fast here instead of inside every suite: the raw page.evaluate
      // fetches the suites use carry cookies but no in-memory access token,
      // so prove the BFF can turn this session into an authenticated call
      // before any test runs.
      await assertSessionReachesBff(page);

      const session: AuthSession = {
        slug,
        context,
        page,
        refreshSession: () => refreshSession(page),
      };
      await use(session);
      await context.close();
    },
    // CI boots a fresh stack per phase: sign-in + MFA + session hydration can
    // legitimately exceed the 30s test timeout on cold containers, and the
    // handoff poll alone can take ~20s on the tightened security stack (45s
    // default). 90s gives the fixture room to fail with the waitForWorkspace
    // diagnostics instead of a generic "fixture timeout" mask.
    { scope: "worker", timeout: 90_000 },
  ],
});