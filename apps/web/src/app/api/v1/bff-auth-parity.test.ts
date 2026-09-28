/**
 * The BFF cookie bridge, asserted on every route that uses it.
 *
 * Pre-release audit finding 26. The BFF documents that a raw same-origin
 * request carrying only the httpOnly session cookie authenticates, because the
 * handler mints an access token server-side. That contract was implemented by
 * copy-pasting ~15 lines into each route handler, and three of the five
 * handlers had silently dropped the cookie fallback: the SSE chat relay, the AI
 * document-pack download, and the conversation-attachment relay all read the
 * Authorization header and then forwarded `token: null` downstream.
 *
 * The audit found the chat-stream instance because that was the one it happened
 * to probe. That is the whole lesson: the bug was never "one route is wrong",
 * it was "the rule is duplicated, so it drifts". Which is why this file does not
 * test one route, and does not assert on /users/me like the original probe did.
 * It walks a representative sample of every shape the BFF has - JSON GET, JSON
 * POST, SSE stream, and binary relays - and requires all of them to behave
 * identically.
 *
 * `@/lib/server/auth` is mocked (it is the transport: it does the fetch and the
 * refresh rotation), but `@/lib/server/bff-auth` is deliberately NOT. The policy
 * under test is the real one, reached across a module boundary, so these
 * assertions cannot pass against a mirror of the implementation that happens to
 * agree with it today.
 *
 * The rule under test, in full:
 *   1. A client Bearer token is used verbatim and is preferred.
 *   2. With no Bearer token, the session cookie mints one server-side.
 *   3. Minting rotates the refresh cookie, so the new value is written back.
 *   4. With neither, the BFF answers 401 itself - it must not forward an
 *      unauthenticated request for the backend to reject opaquely.
 */

import { NextRequest } from "next/server";
import { beforeEach, describe, expect, it, vi } from "vitest";

const callBackend = vi.fn();
const callBackendStream = vi.fn();
const assertSameOrigin = vi.fn();
const resolveTenantSlug = vi.fn();
const sessionAccessToken = vi.fn();
const applySessionCookie = vi.fn();

// Transport only. No `resolveBffAuth` here on purpose - see the file header.
vi.mock("@/lib/server/auth", () => ({
  callBackend: (path: string, options?: unknown) => callBackend(path, options),
  callBackendStream: (path: string, options?: unknown) =>
    callBackendStream(path, options),
  assertSameOrigin: (request: unknown) => assertSameOrigin(request),
  resolveTenantSlug: (host: string | null | undefined) => resolveTenantSlug(host),
  sessionAccessToken: (request: unknown) => sessionAccessToken(request),
  applySessionCookie: (response: unknown, refreshToken: string) =>
    applySessionCookie(response, refreshToken),
}));

import { GET as catchAllGET, POST as catchAllPOST } from "./[...path]/route";
import { POST as reportExportPOST } from "./reports/[...path]/route";
import { POST as chatStreamPOST } from "./ai/agents/chat/stream/route";
import { GET as docPackGET } from "./finance/ai/docs/[docId]/download/route";
import { GET as attachmentGET } from "./agents/conversations/[id]/attachments/[attachmentId]/route";

const ORIGIN = "http://tenant.localhost";
const HOST = "tenant.localhost";

function nextRequest(
  path: string,
  init: {
    method: string;
    headers?: Record<string, string>;
    body?: string;
  },
): NextRequest {
  return new NextRequest(
    `${ORIGIN}${path}`,
    {
      method: init.method,
      headers: { host: HOST, origin: ORIGIN, ...init.headers },
      ...(init.body === undefined ? {} : { body: init.body }),
    } as ConstructorParameters<typeof NextRequest>[1],
  );
}

const SESSION = { token: "minted-from-cookie", refreshToken: "rotated-789" };
const BEARER = "Bearer client-token";
const JSON_HEADERS = { "content-type": "application/json" };

/**
 * Every BFF route, one entry per handler. Each `invoke` takes the request
 * headers so the same route can be driven cookie-only and with a bearer.
 */
interface RouteCase {
  name: string;
  /** The backend helper whose options carry the token. */
  helper: "callBackend" | "callBackendStream";
  invoke: (headers?: Record<string, string>) => Promise<Response>;
}

const ROUTES: RouteCase[] = [
  {
    name: "catch-all JSON GET (identity)",
    helper: "callBackend",
    invoke: (headers) =>
      catchAllGET(nextRequest("/api/v1/users/me", { method: "GET", headers })),
  },
  {
    name: "catch-all JSON POST (core)",
    helper: "callBackend",
    invoke: (headers) =>
      catchAllPOST(
        nextRequest("/api/v1/crm/customers", {
          method: "POST",
          headers: { ...JSON_HEADERS, ...headers },
          body: JSON.stringify({ name: "Acme" }),
        }),
      ),
  },
  {
    name: "reports CSV export relay",
    helper: "callBackendStream",
    invoke: (headers) =>
      reportExportPOST(
        nextRequest("/api/v1/reports/ar_aging/export", {
          method: "POST",
          headers: { ...JSON_HEADERS, ...headers },
          body: "{}",
        }),
      ),
  },
  {
    name: "SSE chat stream relay",
    helper: "callBackendStream",
    invoke: (headers) =>
      chatStreamPOST(
        nextRequest("/api/v1/ai/agents/chat/stream", {
          method: "POST",
          headers: { ...JSON_HEADERS, ...headers },
          body: JSON.stringify({ message: "hi" }),
        }),
      ),
  },
  {
    name: "AI document-pack download relay",
    helper: "callBackendStream",
    invoke: (headers) =>
      docPackGET(
        nextRequest("/api/v1/finance/ai/docs/doc-1/download", {
          method: "GET",
          headers,
        }),
        { params: Promise.resolve({ docId: "doc-1" }) },
      ),
  },
  {
    name: "conversation-attachment relay",
    helper: "callBackendStream",
    invoke: (headers) =>
      attachmentGET(
        nextRequest("/api/v1/agents/conversations/c1/attachments/a1", {
          method: "GET",
          headers,
        }),
        { params: Promise.resolve({ id: "c1", attachmentId: "a1" }) },
      ),
  },
];

const CASES = ROUTES.map((route) => [route.name, route] as const);

describe("BFF cookie bridge parity across every route", () => {
  beforeEach(() => {
    vi.resetAllMocks();
    resolveTenantSlug.mockReturnValue("tenant-acme");
    assertSameOrigin.mockReturnValue(true);
    applySessionCookie.mockImplementation(() => undefined);
    sessionAccessToken.mockResolvedValue({ ...SESSION });

    callBackend.mockResolvedValue({
      ok: true,
      status: 200,
      data: {},
      payload: { success: true },
      retryAfter: null,
    });
    // A real streaming Response, because these routes check `.body` and would
    // take the 502 branch against a stub without one.
    callBackendStream.mockResolvedValue(
      new Response("data: {}\n\n", {
        status: 200,
        headers: { "content-type": "text/event-stream" },
      }),
    );
  });

  describe("cookie-only requests authenticate everywhere", () => {
    // Finding 26 restated as a table. Before the fix, the last four rows
    // forwarded `token: null` and the caller got a relayed 401.
    it.each(CASES)(
      "%s mints a token from the session cookie",
      async (_name, route) => {
        const response = await route.invoke();

        expect(response.status).toBe(200);

        // The load-bearing assertion: a real token reached the backend helper.
        // A 200 alone would not catch this - a handler that sent null against a
        // stubbed backend would also return 200.
        const helper =
          route.helper === "callBackend" ? callBackend : callBackendStream;
        expect(helper).toHaveBeenCalledTimes(1);
        const options = helper.mock.calls[0]![1] as { token: string | null };
        expect(options.token).toBe(SESSION.token);
      },
    );

    it.each(CASES)(
      "%s writes the rotated refresh cookie back",
      async (_name, route) => {
        await route.invoke();

        // Minting rotated the value identity holds. Without the write-back the
        // next cookie-only call re-presents a value that is about to be
        // rejected, so this is what keeps a cookie-only session alive across
        // repeated calls rather than working exactly once.
        expect(applySessionCookie).toHaveBeenCalledTimes(1);
        expect(applySessionCookie.mock.calls[0]![1]).toBe(SESSION.refreshToken);
      },
    );
  });

  describe("a client bearer token is preferred and does not rotate", () => {
    it.each(CASES)(
      "%s forwards the bearer token verbatim",
      async (_name, route) => {
        const response = await route.invoke({ authorization: BEARER });

        expect(response.status).toBe(200);

        const helper =
          route.helper === "callBackend" ? callBackend : callBackendStream;
        const options = helper.mock.calls[0]![1] as { token: string | null };
        expect(options.token).toBe("client-token");

        // sessionAccessToken must not even be consulted: rotating the refresh
        // value on a request that already carries a valid bearer does it for
        // no reason, and a race there can invalidate an active session.
        expect(sessionAccessToken).not.toHaveBeenCalled();
        expect(applySessionCookie).not.toHaveBeenCalled();
      },
    );
  });

  describe("unauthenticated requests are rejected by the BFF itself", () => {
    it.each(CASES)(
      "%s answers 401 without contacting the backend",
      async (_name, route) => {
        sessionAccessToken.mockResolvedValue(null);

        const response = await route.invoke();

        expect(response.status).toBe(401);
        await expect(response.json()).resolves.toEqual({
          detail: "Missing Authorization header",
        });
        // The BFF owns authentication. Forwarding an unauthenticated request
        // and relaying the backend's opaque 401 is what made this bug hard to
        // diagnose from the outside - no backend ever logged the request.
        expect(callBackend).not.toHaveBeenCalled();
        expect(callBackendStream).not.toHaveBeenCalled();
      },
    );
  });
});
