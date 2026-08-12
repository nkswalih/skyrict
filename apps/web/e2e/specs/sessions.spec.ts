import { expect, test } from "@playwright/test";

import {
  listSessions,
  login,
  loginVerified,
  logout,
  mfaSetupApi,
  mfaVerifyApi,
  refresh,
  revokeSession,
  signupAccountViaBff,
  trustSession,
  type Account,
} from "../helpers/backend";
import { totp } from "../helpers/crypto";

const MFA_REQUIRED_TYPE = "https://api.skyrict.io/problems/mfa-required";
const SESSION_NOT_FOUND_TYPE = "https://api.skyrict.io/problems/session-not-found";
const REUSE_TYPE = "https://api.skyrict.io/problems/token-reuse-detected";

test.describe.serial("session management", () => {
  let account: Account;
  let preEnrollAccess = "";
  let secret = "";

  test.beforeAll(async ({ request }) => {
    account = await signupAccountViaBff(request, "session");
    const pending = await login(request, account);
    expect(pending.next_step).toBe("mfa.setup");
    expect(pending.access_token).toBeTruthy();
    preEnrollAccess = pending.access_token!;
  });

  test("tenant APIs are blocked until MFA is enrolled", async ({ request }) => {
    const res = await listSessions(request, {
      accessToken: preEnrollAccess,
      slug: account.slug,
    }).catch((e) => e);
    expect(res).toMatchObject({ status: 403, type: MFA_REQUIRED_TYPE });
  });

  test("enroll MFA and list sessions", async ({ request }) => {
    const setup = await mfaSetupApi(request, {
      accessToken: preEnrollAccess,
      slug: account.slug,
    });
    secret = setup.secret;
    await mfaVerifyApi(request, {
      accessToken: preEnrollAccess,
      slug: account.slug,
      code: totp(secret),
    });

    const first = await loginVerified(request, account, secret);
    const sessions = await listSessions(request, {
      accessToken: first.access_token!,
      slug: account.slug,
    });
    // The pre-enrollment mfa.setup login created one session; this login another.
    expect(sessions.total).toBeGreaterThanOrEqual(2);
    expect(sessions.sessions[0].status).toBe("active");
  });

  test("the newest session can be marked trusted", async ({ request }) => {
    expect(secret).toBeTruthy();
    const current = await loginVerified(request, account, secret);
    const before = await listSessions(request, {
      accessToken: current.access_token!,
      slug: account.slug,
    });
    const sessionId = before.sessions[0].id;
    expect(sessionId).toBeTruthy();

    await trustSession(request, {
      accessToken: current.access_token!,
      slug: account.slug,
      sessionId,
    });

    const after = await listSessions(request, {
      accessToken: current.access_token!,
      slug: account.slug,
    });
    const trusted = after.sessions.find((s) => s.id === sessionId);
    expect(trusted?.is_trusted).toBe(true);
  });

  test("revoking a session invalidates its refresh token", async ({ request }) => {
    expect(secret).toBeTruthy();
    const session = await loginVerified(request, account, secret);
    const list = await listSessions(request, {
      accessToken: session.access_token!,
      slug: account.slug,
    });
    const sessionId = list.sessions[0].id;

    await revokeSession(request, {
      accessToken: session.access_token!,
      slug: account.slug,
      sessionId,
    });
    await expect(
      revokeSession(request, {
        accessToken: session.access_token!,
        slug: account.slug,
        sessionId,
      }),
    ).rejects.toMatchObject({ status: 404, type: SESSION_NOT_FOUND_TYPE });

    const after = await listSessions(request, {
      accessToken: session.access_token!,
      slug: account.slug,
    });
    expect(after.sessions.some((s) => s.id === sessionId)).toBe(false);

    await expect(
      refresh(request, {
        refreshToken: session.refresh_token!,
        slug: account.slug,
      }),
    ).rejects.toMatchObject({ status: 401, type: REUSE_TYPE });
  });

  test("refresh rotation makes the old token useless and kills the family", async ({
    request,
  }) => {
    expect(secret).toBeTruthy();
    const session = await loginVerified(request, account, secret);
    const rotated = await refresh(request, {
      refreshToken: session.refresh_token!,
      slug: account.slug,
    });
    expect(rotated.access_token).toBeTruthy();
    expect(rotated.refresh_token).toBeTruthy();

    await expect(
      refresh(request, {
        refreshToken: session.refresh_token!,
        slug: account.slug,
      }),
    ).rejects.toMatchObject({ status: 401, type: REUSE_TYPE });

    // The whole family is dead: even the freshly-rotated token is rejected.
    await expect(
      refresh(request, {
        refreshToken: rotated.refresh_token!,
        slug: account.slug,
      }),
    ).rejects.toMatchObject({ status: 401, type: REUSE_TYPE });
  });

  test("logout revokes the session", async ({ request }) => {
    expect(secret).toBeTruthy();
    const session = await loginVerified(request, account, secret);
    await logout(request, {
      refreshToken: session.refresh_token!,
      accessToken: session.access_token!,
      slug: account.slug,
    });

    await expect(
      refresh(request, {
        refreshToken: session.refresh_token!,
        slug: account.slug,
      }),
    ).rejects.toMatchObject({ status: 401, type: REUSE_TYPE });
  });
});
