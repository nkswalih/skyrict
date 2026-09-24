/*
 * Shared authentication flow primitives for the multi-tenant E2E harness.
 *
 * Centralizes the sign-in form flow, the mandatory-MFA enrollment and challenge
 * paths, the TOTP fill helper, and the persisted-secret reader so the setup
 * project, the worker-scoped auth fixture, and the tenant fixture all walk the
 * same flows against the same components.
 *
 * Every helper drives the real BFF (/api/auth/*) and the signin surface - no
 * direct identity calls, no bypassed CSRF, no mock storage.
 */

import { readFileSync } from "node:fs";

import { expect, type Page, type Request } from "@playwright/test";

import { totp } from "./totp";

export const TOTP_SECRET_FILE = "e2e/.auth/totp-secret";

/** The enrolled TOTP secret: env override wins, else the persisted file. */
export function readEnrolledSecret(secretFile = TOTP_SECRET_FILE): string {
    const fromEnv = process.env.E2E_TOTP_SECRET;
    if (fromEnv) return fromEnv;
    try {
        return readFileSync(secretFile, "utf8").trim();
    } catch {
        return "";
    }
}

/** Fill each OtpInput digit box (aria-label "<label> digit N"). */
export async function fillOtp(
    page: Page,
    label: string,
    code: string,
): Promise<void> {
    // Under parallel load the MFA form can mount after the challenge heading
    // resolves; a blind sequential fill then waits on digit 1 while the rest of
    // the form is mid-render. Wait for the FULL digit form (exact count) to be
    // attached BEFORE filling so every fill targets a settled, complete form.
    await expect(
        page.locator(`input[aria-label^="${label} digit "]`),
    ).toHaveCount(code.length);
    for (let i = 0; i < code.length; i += 1) {
        await page
            .locator(`input[aria-label="${label} digit ${i + 1}"]`)
            .fill(code[i]!);
    }
}

/**
 * Submit the sign-in form on the signin surface. The page must already be on
 * {slug}.signin.{apex}/signin; email is always re-filled because the signin
 * surface's auto-completed email would otherwise be stale.
 */
export async function signInWithPassword(
    page: Page,
    email: string,
    password: string,
): Promise<void> {
    await page.getByLabel("Email").fill(email);
    await page.getByLabel("Password").fill(password);
    await page.getByRole("button", { name: "Sign in" }).click();
}

export type MfaPath = "enrollment" | "challenge";

/**
 * Detect which mandatory-MFA path the sign-in flow takes: the account either
 * lands on /setup-mfa (first enrollment) or is challenged for a TOTP code on
 * the login form (already enrolled). Fighting over the same timer is the
 * established pattern - both waits observe the same page and the winner
 * resolves first.
 */
export async function whichMfaPath(
    page: Page,
    timeoutMs = 15_000,
): Promise<MfaPath> {
    return new Promise<MfaPath>((resolve, reject) => {
        let settled = false;
        const finish = (path: MfaPath) => {
            if (settled) return;
            settled = true;
            clearTimeout(timer);
            resolve(path);
        };
        // Neither arm resolving means sign-in never reached an MFA surface -
        // e.g. the handoff bounced back with ?error=... Reject with the URL
        // instead of hanging until the whole test times out.
        const timer = setTimeout(() => {
            if (settled) return;
            settled = true;
            reject(
                new Error(
                    `MFA path not detected within ${timeoutMs}ms; current URL: ${page.url()}`,
                ),
            );
        }, timeoutMs + 500);
        void page
            .waitForURL("**/setup-mfa", { timeout: timeoutMs })
            .then(() => finish("enrollment"))
            .catch(() => {});
        void page
            .getByRole("heading", { name: "Two-factor check" })
            .waitFor({ timeout: timeoutMs })
            .then(() => finish("challenge"))
            .catch(() => {});
    });
}

/**
 * One full TOTP challenge round: try the current, previous, and next 30s
 * windows. Returns true when the handoff landed on the workspace host - or
 * when the form visibly rejected the code (the caller treats both as "attempt
 * consumed"; a rejection is detected so the next round can start from a clean
 * form instead of waiting out the handoff that will never happen).
 */
async function playChallengeRound(
    page: Page,
    secret: string,
): Promise<boolean> {
    for (const offset of [0, -1, 1]) {
        await fillOtp(page, "Two-factor code", totp(secret, offset));
        const landed = page
            .waitForURL((url) => !url.hostname.includes(".signin."), {
                timeout: 10_000,
            })
            .then(() => true)
            .catch(() => false);
        const rejected = page
            .getByText("That code didn't match")
            .waitFor({ timeout: 10_000 })
            .then(() => false)
            .catch(() => false);
        if (await Promise.race([landed, rejected])) {
            return true;
        }
    }
    return false;
}

/**
 * Complete the TOTP challenge on the login form and wait for the handoff to
 * the workspace host. The OTP form submits itself as soon as the last digit is
 * filled, so no click is needed - and none is safe (the button is mid-flight
 * disabled).
 */
export async function completeMfaChallenge(
    page: Page,
    secret: string,
): Promise<void> {
    // Try the current, previous, and next 30s windows. A single-window code
    // races the TOTP boundary (and a code already consumed earlier in the same
    // window by the setup project); when it is stale the form rejects it
    // inline and then waits forever for a handoff that never happens.
    if (await playChallengeRound(page, secret)) {
        return;
    }

    // All three windows rejected. Two distinct root causes are possible under
    // parallel workers on a fresh stack:
    //   1. a TOTP clock boundary crossed between code generation and the
    //      form's own verify (a reload opens a fresh 30s window); or
    //   2. a divergent enrollment state - the persisted secret belongs to a
    //      DIFFERENT enrollment than the server's current one, or the server
    //      thinks the admin is NOT enrolled at all while the harness expected
    //      a challenge (the previous attempt's enrollment never committed).
    // Reload the signin surface (the server re-drives the correct MFA surface)
    // and re-detect the path instead of bouncing with a confusing handoff
    // error for a stale secret. The capture listener must attach BEFORE the
    // reload: a redirect to /setup-mfa calls the MFA setup API on mount.
    const getMfaSecret = installMfaSecretCapture(page);
    await page.reload({ waitUntil: "domcontentloaded" });

    let path: MfaPath;
    try {
        path = await whichMfaPath(page, 10_000);
    } catch {
        await waitForWorkspace(page);
        return;
    }

    if (path === "enrollment") {
        // The server wants a fresh enrollment (the admin's MFA never
        // committed). Complete the REAL path; the persisted-secret fallback
        // still lets the verify loop land if the capture races the reload.
        await expect(
            page.getByRole("heading", { name: "Protect your account" }),
        ).toBeVisible({ timeout: 10_000 });
        await enrollMfaAndFinish(page, {
            secretGetter: getMfaSecret,
            knownSecret: secret,
        });
        return;
    }

    // Still a challenge: give the reloaded form one more full round before
    // reporting the MFA rejection.
    if (await playChallengeRound(page, secret)) {
        return;
    }
    await waitForWorkspace(page);
}

/**
 * Capture the raw TOTP secret the browser receives from the MFA setup API.
 * Attach BEFORE navigating to /setup-mfa - the setup page calls the API on
 * mount, so a late listener would miss the only response that carries the
 * secret. A response listener is used instead of route interception because
 * route.fetch() re-issues the request through Node, which cannot resolve the
 * *.localhost host (only the browser can).
 *
 * Returns a getter that reflects the latest captured value (or null before the
 * response lands).
 */
export function installMfaSecretCapture(page: Page): () => string | null {
    let mfaSecret: string | null = null;
    page.on("response", async (response) => {
        if (!response.url().includes("/api/auth/mfa/setup")) return;
        const body = (await response.json().catch(() => ({}))) as Record<
            string,
            unknown
        >;
        mfaSecret = typeof body.secret === "string" ? body.secret : null;
    });
    return () => mfaSecret;
}

/**
 * Complete mandatory MFA enrollment on /setup-mfa: wait for (or reuse) the
 * TOTP secret, verify a code generated from it, acknowledge the recovery
 * codes, finish setup, and wait for the handoff to the workspace host.
 *
 * Callers pass a `secretGetter` from installMfaSecretCapture() when the secret
 * is unknown ahead of time, and/or a `knownSecret` fallback (e.g. the
 * persisted secret from a previous run). `onWritten` is invoked with the
 * resolved secret BEFORE the TOTP loop so a clock-boundary failure still
 * leaves a recoverable secret. Returns the resolved secret.
 */
export async function enrollMfaAndFinish(
    page: Page,
    options: {
        secretGetter?: () => string | null;
        knownSecret?: string;
        onWritten?: (secret: string) => void;
    } = {},
): Promise<string> {
    if (options.secretGetter) {
        await expect
            .poll(() => options.secretGetter?.() ?? null, {
                timeout: 10_000,
                message: "MFA setup response did not include a TOTP secret.",
            })
            .toBeTruthy();
    }

    const secret = options.secretGetter?.() ?? options.knownSecret ?? "";
    expect(secret, "MFA setup secret is missing.").toBeTruthy();
    options.onWritten?.(secret);

    // Verify a TOTP code generated from the secret. Try the current, previous,
    // and next 30s windows to dodge clock boundaries.
    let verified = false;
    for (const offset of [0, -1, 1]) {
        await fillOtp(page, "Authenticator code", totp(secret, offset));
        await page.getByRole("button", { name: "Verify and continue" }).click();

        const success = page
            .getByText("Authenticator verified")
            .waitFor({ timeout: 4_000 })
            .then(() => true)
            .catch(() => false);
        const failure = page
            .getByText("That code doesn't match")
            .waitFor({ timeout: 4_000 })
            .then(() => false)
            .catch(() => false);
        if (await Promise.race([success, failure])) {
            verified = true;
            break;
        }
    }
    expect(
        verified,
        "TOTP enrollment failed across the current, previous, and next windows.",
    ).toBe(true);

    // Acknowledge and finish; the handoff form-POSTs to the workspace origin
    // and lands on {slug}.localhost (never the signin host).
    await page
        .getByRole("button", {
            name: "I've saved my recovery codes somewhere safe.",
        })
        .click();
    await page.getByRole("button", { name: "Finish setup" }).click();
    // Generous 100s budget: the poll's FIRST invocation starts while the
    // handoff's form-POST 303 -> GET / navigation is still in flight, so the
    // URL check still sees the signin host. The predicate probes are all
    // explicitly bounded (1.5s), so the invocation cannot hang - it returns
    // "pending", the poll re-invokes, and the next iteration's URL check
    // catches the workspace commit. The budget is a backstop, not the normal
    // path: the whole enrollment chain (login -> enroll -> mint -> redeem ->
    // first rotations) completes server-side in ~6s.
    await waitForWorkspace(page, { timeout: 100_000 });
    return secret;
}

/** Wait for the login/MFA handoff to land on the workspace host. */
export async function waitForWorkspace(
    page: Page,
    options: { timeout?: number } = {},
): Promise<void> {
    // A successful handoff navigates off the signin host. A rejected MFA code
    // ("That code didn't match") or a bounced redirect (the login page renders
    // the API error / stripped `?error=` into a role=alert) keeps the URL on
    // the signin host - previously waitForURL just sat out its full timeout and
    // the worker fixture then died with a generic 30s timeout, hiding the
    // actual cause. Fail fast with the URL + visible copy instead.
    //
    // IMPORTANT: the auth pages carry a permanent screen-reader live region
    // (role=alert) that echoes the document <title> (e.g. "Set up two-factor
    // authentication · Skyrict"), so PRESENCE of a role=alert is NOT a failure.
    // Only an alert whose text diverges from the current page title signals a
    // bounced handoff - plus the plain (non-alert) "That code didn't match"
    // copy from the MFA verify form.
    //
    // Every probe inside the predicate is explicitly bounded so a single
    // invocation can never outlive the poll budget: the auto-waiting
    // textContent() probes carry a 1.5s deadline (see the note above - an
    // unbounded probe racing the handoff navigation hung the first poll
    // invocation for the full 100s in CI). The default budget stays generous
    // (45s) as a backstop for genuinely cold stacks; callers with a tighter
    // budget (e.g. the worker fixture's own timeout) pass an explicit
    // `timeout`.
    const timeout = options.timeout ?? 45_000;
    const failedRequests: string[] = [];
    const onRequestFailed = (request: Request) => {
        failedRequests.push(
            `${request.method()} ${request.url()} - ${request.failure()?.errorText ?? "unknown error"}`,
        );
    };
    page.on("requestfailed", onRequestFailed);
    try {
        await expect
            .poll(
                async (): Promise<string | null> => {
                    if (!new URL(page.url()).hostname.includes(".signin.")) {
                        return null; // handoff landed
                    }
                    const title = (await page.title()).trim();
                    const alerts = page.locator('[role="alert"]');
                    const alertCount = await alerts.count();
                    let copy: string | null = null;
                    for (let i = 0; i < alertCount; i++) {
                        // BOUNDED probe: auto-waiting textContent() without a
                        // timeout can hang a whole poll invocation when the
                        // page is mid-handoff navigation (the first invocation
                        // races the form-POST 303 -> GET / commit; the wait then
                        // polls the post-navigation document forever). With a
                        // deadline the predicate always returns and the poll
                        // re-invokes, catching the flipped URL on the next
                        // iteration instead of blocking the full budget.
                        const text =
                            (await alerts
                                .nth(i)
                                .textContent({ timeout: 1_500 })
                                .catch(() => null)) ?? "";
                        if (title && text.trim() && text.trim() !== title) {
                            copy = text;
                            break;
                        }
                    }
                    copy ??=
                        (await page
                            .getByText(/That code didn'?t match/i)
                            .first()
                            .textContent({ timeout: 1_500 })
                            .catch(() => null)) ?? null;
                    if (copy) {
                        throw new Error(
                            `MFA handoff failed at ${page.url()}: ${copy.trim()}`,
                        );
                    }
                    return "pending";
                },
                {
                    timeout,
                    message: "MFA handoff did not reach the workspace",
                },
            )
            .toBe(null);
    } catch (err) {
        if (
            err instanceof Error &&
            err.message.startsWith("MFA handoff failed at")
        ) {
            throw err; // bounced handoff - the copy above is specific enough
        }
        throw new Error(
            [
                "MFA handoff did not reach the workspace.",
                `Final URL: ${page.url()}`,
                `Page title: ${await page.title().catch(() => "<unavailable>")}`,
                failedRequests.length
                    ? `Failed browser requests:\n${failedRequests.join("\n")}`
                    : "No failed browser requests were recorded.",
            ].join("\n"),
            { cause: err },
        );
    } finally {
        page.off("requestfailed", onRequestFailed);
    }
}

/**
 * Re-hydrate the session exactly like the app's own navigation does: a
 * same-origin GET through the BFF rotates the refresh token and the browser
 * stores the new Set-Cookie in its jar. This MUST run in the browser context
 * (page.evaluate) - Playwright's APIRequestContext resolves hostnames through
 * Node, which cannot resolve *.localhost, and issuing the request from the
 * default-origin page would dereference a tenant that does not exist.
 */
export async function refreshSession(page: Page): Promise<void> {
    await page.evaluate(async () => {
        const res = await fetch("/api/auth/session", {
            credentials: "include",
            cache: "no-store",
        });
        if (!res.ok) {
            throw new Error(`Session refresh failed: HTTP ${res.status}`);
        }
    });
}

/**
 * Verify the authenticated session actually authenticates BFF calls before a
 * fixture yields the workspace.
 *
 * The sidebar email only proves the shell hydrated once from a refresh
 * cookie; it says nothing about whether the BFF can forward the session
 * downstream when the browser only sends cookies (no in-memory access token).
 * Hit the identity current-user endpoint through the BFF and require 200:
 * when this fails, every suite would otherwise drown in opaque
 * ``401 Missing Authorization header`` errors from raw page.evaluate fetches.
 *
 * The probe rotates the refresh token once through the BFF - safe here
 * because it runs after waitForWorkspaceSettled() left the shell idle, so it
 * cannot race the app's own single-flight rotation.
 */
export async function assertSessionReachesBff(page: Page): Promise<void> {
    const probe = await page.evaluate(async () => {
        const res = await fetch("/api/v1/users/me", {
            credentials: "include",
            cache: "no-store",
        });
        let body = "";
        try {
            body = (await res.text()).slice(0, 240);
        } catch {
            // keep the body empty when the stream cannot be read
        }
        return { status: res.status, body };
    });
    expect(
        probe.status,
        `BFF session probe to /api/v1/users/me did not authenticate: ` +
            `HTTP ${probe.status} ${probe.body}`,
    ).toBe(200);
}

/**
 * Wait for the workspace shell to finish its initial session hydration.
 *
 * The logo link ("Skyrict dashboard") is part of the SERVER-rendered shell and
 * appears as soon as a session cookie exists - long before the client's
 * SessionProvider.restore() finishes rotating the refresh token on mount.
 * Resolving on the link alone lets the test's first goto abort that in-flight
 * hydration: the backend completes the rotation (advancing the session's token
 * hash) while the browser, whose fetch the navigation killed, never stores the
 * new Set-Cookie. The next page then presents a stale token, the backend's
 * reuse detector revokes the whole session family, and the user is bounced to
 * /signin (see reports-workspace.spec.ts; proven via the identity audit log:
 * auth.refresh.success immediately followed by auth.refresh.reuse_detected).
 *
 * The real readiness signal is the sidebar user menu: it renders the signed-in
 * user's email only after restore() resolves - i.e. the BFF session restore
 * completed AND its Set-Cookie was applied to the cookie jar. Waiting on that
 * after the shell link means the test's first navigation always starts from a
 * settled, current session.
 *
 * Do NOT attach a 401 auto-refresh here: the app's own single-flight recovery
 * (lib/api/http.ts ensureSession) is the only sanctioned rotation source - a
 * parallel /api/auth/session from the harness would race it and revoke the
 * whole token family.
 */
export async function waitForWorkspaceSettled(
    page: Page,
    email?: string,
): Promise<void> {
    await expect(
        page.getByRole("link", { name: "Skyrict dashboard", exact: true }),
    ).toBeVisible({ timeout: 20_000 });
    const expected = email ?? process.env.E2E_ADMIN_EMAIL ?? "admin@skyrict.io";
    await expect(
        page.getByText(expected, { exact: true }).first(),
        "sidebar user menu must render the signed-in user's email after session hydration",
    ).toBeVisible({ timeout: 20_000 });
}

/**
 * First sign-in of a freshly registered tenant owner: mandatory MFA takes the
 * enrollment path (/setup-mfa) because a brand-new account has no authenticator
 * enrolled. Attaches the secret capture BEFORE the BFF login handoff (the setup
 * page calls the API on mount), signs in, asserts the enrollment path, and
 * completes it. Returns the captured TOTP secret so the caller can later play
 * the challenge leg.
 */
export async function firstOwnerSignInAndEnrollMfa(
    page: Page,
    email: string,
    password: string,
): Promise<string> {
    const getMfaSecret = installMfaSecretCapture(page);
    await signInWithPassword(page, email, password);
    expect(await whichMfaPath(page)).toBe("enrollment");
    return enrollMfaAndFinish(page, { secretGetter: getMfaSecret });
}
