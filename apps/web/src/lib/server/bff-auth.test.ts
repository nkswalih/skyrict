/**
 * Unit tests for the BFF request-authentication policy.
 *
 * `resolveBffAuth` is the single place that decides how a BFF request gets an
 * access token. The route-level parity table
 * (`src/app/api/v1/bff-auth-parity.test.ts`) proves every route applies it; this
 * file pins the policy itself, including the header-parsing edge cases that are
 * awkward to reach through a route handler.
 */

import { NextRequest } from "next/server";
import { beforeEach, describe, expect, it, vi } from "vitest";

const sessionAccessToken = vi.fn();

vi.mock("@/lib/server/auth", () => ({
  sessionAccessToken: (request: unknown) => sessionAccessToken(request),
}));

import { MISSING_AUTH_DETAIL, resolveBffAuth } from "./bff-auth";

function request(headers: Record<string, string> = {}): NextRequest {
  return new NextRequest("http://tenant.localhost/api/v1/users/me", { headers });
}

describe("resolveBffAuth", () => {
  beforeEach(() => {
    vi.resetAllMocks();
    sessionAccessToken.mockResolvedValue({
      token: "from-cookie",
      refreshToken: "rotated-refresh",
    });
  });

  it("uses a client bearer token verbatim and does not rotate", async () => {
    const auth = await resolveBffAuth(
      request({ authorization: "Bearer client-token" }),
    );

    expect(auth).toEqual({
      ok: true,
      token: "client-token",
      rotatedRefreshToken: null,
    });
    // Rotating the refresh value for a request that already has a valid access
    // token is work with no benefit, and a race with the client's own restore()
    // can invalidate an active session.
    expect(sessionAccessToken).not.toHaveBeenCalled();
  });

  it("accepts the scheme case-insensitively, as RFC 7235 requires", async () => {
    const auth = await resolveBffAuth(request({ authorization: "bearer tok" }));

    expect(auth).toEqual({ ok: true, token: "tok", rotatedRefreshToken: null });
    expect(sessionAccessToken).not.toHaveBeenCalled();
  });

  it("mints from the session cookie and reports the rotated refresh token", async () => {
    const auth = await resolveBffAuth(request());

    expect(auth).toEqual({
      ok: true,
      token: "from-cookie",
      rotatedRefreshToken: "rotated-refresh",
    });
  });

  it("reports a null rotated token when identity did not rotate", async () => {
    sessionAccessToken.mockResolvedValue({
      token: "from-cookie",
      refreshToken: null,
    });

    const auth = await resolveBffAuth(request());

    expect(auth).toEqual({
      ok: true,
      token: "from-cookie",
      rotatedRefreshToken: null,
    });
  });

  it("trims the OWS the grammar allows between the scheme and the token", async () => {
    // "Bearer    tok" is a legal credential per RFC 7235, and the Headers layer
    // preserves the internal run of spaces, so the token must be trimmed before
    // it is forwarded - otherwise the backend rejects a valid token.
    const auth = await resolveBffAuth(
      request({ authorization: "Bearer    tok" }),
    );

    expect(auth).toEqual({ ok: true, token: "tok", rotatedRefreshToken: null });
  });

  it.each([
    // No separator at all. The Headers layer strips the trailing ASCII space
    // from "Bearer ", so this arrives as "Bearer" and is rejected by the scheme
    // check - the empty-token guard below is not what handles it.
    ["a bare scheme with no separator", "Bearer"],
    // The reachable path to the empty-token guard: U+00A0 is not HTTP OWS, so
    // the Headers layer keeps it, but String.prototype.trim removes it.
    ["a scheme followed only by a non-OWS space", "Bearer \u00a0"],
  ])(
    "treats %s as no bearer and falls through to the cookie",
    async (_name, header) => {
      // Forwarding an empty token downstream would send a request the backend
      // rejects with an opaque 401, instead of this BFF's own clear one. A
      // caller holding a valid cookie should authenticate either way - it is
      // the same same-origin session, not a privilege escalation.
      const auth = await resolveBffAuth(request({ authorization: header }));

      expect(auth).toEqual({
        ok: true,
        token: "from-cookie",
        rotatedRefreshToken: "rotated-refresh",
      });
      expect(sessionAccessToken).toHaveBeenCalledTimes(1);
    },
  );

  it("ignores a non-Bearer Authorization scheme", async () => {
    // Basic/Digest credentials are not something this BFF accepts; they must
    // not be sliced as if they were a token.
    const auth = await resolveBffAuth(
      request({ authorization: "Basic dXNlcjpwYXNz" }),
    );

    expect(auth).toEqual({
      ok: true,
      token: "from-cookie",
      rotatedRefreshToken: "rotated-refresh",
    });
  });

  it("answers 401 itself when there is no bearer and no usable session", async () => {
    sessionAccessToken.mockResolvedValue(null);

    const auth = await resolveBffAuth(request());

    expect(auth.ok).toBe(false);
    if (auth.ok) throw new Error("unreachable");
    expect(auth.response.status).toBe(401);
    await expect(auth.response.json()).resolves.toEqual({
      detail: MISSING_AUTH_DETAIL,
    });
  });
});
