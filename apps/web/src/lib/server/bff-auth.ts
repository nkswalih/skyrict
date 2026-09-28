/**
 * The BFF's request-authentication policy.
 *
 * One rule, one implementation: a client-supplied Bearer token is used
 * verbatim, and when there is none the httpOnly session cookie mints an access
 * token server-side.
 *
 * This rule used to be copy-pasted into five route handlers, and three of the
 * five had silently dropped the cookie fallback - the SSE chat relay, the AI
 * document-pack download, and the conversation-attachment relay all read the
 * Authorization header and then forwarded `token: null` downstream, so a
 * cookie-only caller received a relayed 401 while the BFF's documented contract
 * said it would authenticate. The pre-release audit
 * (`docs/runbooks/pre-release-audit-2026-09.md`, finding 26) caught only one of
 * the three, because only that one happened to be probed. That is the real
 * lesson: triplicated auth logic drifts, and the drift stays invisible until
 * something asserts the contract on every route at once.
 *
 * It lives apart from `auth.ts` so that `sessionAccessToken` is reached across a
 * module boundary. Vitest cannot intercept a same-module function reference, so
 * had this stayed in `auth.ts`, the only way to test it would have been to
 * re-implement it as a mock inside every route test - which is precisely the
 * duplication that caused the bug. Here, a test mocks `@/lib/server/auth` and
 * exercises this file for real.
 */

import type { NextRequest } from "next/server";
import { NextResponse } from "next/server";

import { sessionAccessToken } from "@/lib/server/auth";

/** `detail` returned by the BFF when it cannot authenticate a request itself. */
export const MISSING_AUTH_DETAIL = "Missing Authorization header";

/**
 * Outcome of authenticating a BFF request: either a token to forward, or the
 * response the route should return verbatim.
 */
export type BffAuth =
  | { ok: true; token: string; rotatedRefreshToken: string | null }
  | { ok: false; response: NextResponse };

/** Read a client Bearer token, or null when the header carries no usable one. */
function readBearerToken(request: NextRequest): string | null {
  const authorization = request.headers.get("authorization");
  if (!authorization?.toLowerCase().startsWith("bearer ")) return null;

  // OWS between the scheme and the token is legal in the grammar and the
  // Headers layer preserves it, so the token is trimmed before use:
  // "Bearer    tok" arrives verbatim and must yield "tok".
  const token = authorization.slice("Bearer ".length).trim();

  // The two ways a "bearer with nothing after it" can reach this point are
  // worth distinguishing, because they are handled by different checks:
  //
  //  - "Bearer " and "Bearer   " are already rejected above. The Headers layer
  //    strips trailing ASCII whitespace from a value, so they arrive as
  //    "Bearer", which has no space and therefore no scheme separator.
  //  - "Bearer <U+00A0>" survives that stripping (U+00A0 is not HTTP OWS) but is
  //    removed by trim(), so it reaches this line and lands here.
  //
  // This guard exists for the second case. Do not delete it as unreachable.
  return token === "" ? null : token;
}

/**
 * Authenticate a BFF request, preferring the client's Bearer token.
 *
 * Minting from the cookie rotates the refresh value identity holds, so the
 * returned `rotatedRefreshToken` must be written back onto the response or the
 * next cookie-only call re-presents a value identity is about to reject.
 *
 * A malformed `Authorization: Bearer ` (present but empty) is treated as absent
 * rather than as a deliberate empty token. Forwarding it would send a
 * headerless request downstream and surface the backend's opaque 401 instead of
 * this BFF's own clear one, and a caller holding a valid cookie should
 * authenticate either way - it is the same same-origin session, not a privilege
 * escalation.
 */
export async function resolveBffAuth(request: NextRequest): Promise<BffAuth> {
  // `!== null` rather than a truthiness check, so "no usable bearer" has exactly
  // one definition. A truthiness test here would silently re-accept the empty
  // token that readBearerToken deliberately rejected, and the two would drift.
  const bearer = readBearerToken(request);
  if (bearer !== null) {
    return { ok: true, token: bearer, rotatedRefreshToken: null };
  }

  const session = await sessionAccessToken(request);
  if (!session) {
    return {
      ok: false,
      response: NextResponse.json(
        { detail: MISSING_AUTH_DETAIL },
        { status: 401 },
      ),
    };
  }
  return {
    ok: true,
    token: session.token,
    rotatedRefreshToken: session.refreshToken,
  };
}
