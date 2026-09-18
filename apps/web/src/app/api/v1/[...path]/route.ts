import type { NextRequest } from "next/server";
import { NextResponse } from "next/server";

import {
  applySessionCookie,
  assertSameOrigin,
  callBackend,
  callBackendRaw,
  resolveTenantSlug,
  sessionAccessToken,
} from "@/lib/server/auth";

export const dynamic = "force-dynamic";

const SAFE_METHODS = new Set(["GET", "HEAD", "OPTIONS"]);

/**
 * Authenticated BFF proxy for internal services' /api/v1/* endpoints.
 *
 * The browser talks to these same-origin handlers instead of the backend:
 * (a) the tenant slug is always derived server-side from the Host header (the
 * client's X-Tenant-Slug is ignored), (b) the access token comes from the
 * client's Bearer header when present, otherwise minted server-side from the
 * httpOnly session cookie (so raw same-origin fetches that only carry cookies
 * still authenticate), and (c) state-changing methods must pass the
 * Origin/Referer CSRF gate. When a token was minted from the session cookie
 * the rotated refresh cookie is written back on the response so the browser
 * keeps a current token for the next cookie-only call.
 */
async function proxy(request: NextRequest) {
  if (SAFE_METHODS.has(request.method.toUpperCase()) === false && !assertSameOrigin(request)) {
    return NextResponse.json({ detail: "Invalid request origin." }, { status: 403 });
  }

  const slug = resolveTenantSlug(request.headers.get("host"));
  const authorization = request.headers.get("authorization");

  // Resolve the access token. Bearer headers (the client's in-memory access
  // token) win; raw same-origin fetches carry only the session cookie, so
  // mint a fresh access token from it server-side - the same silent refresh
  // the /api/auth/refresh route performs, keeping identity's single rotation
  // per request and returning the rotated refresh cookie for write-back.
  let token: string | null = null;
  let rotatedRefreshToken: string | null = null;
  if (authorization?.toLowerCase().startsWith("bearer ")) {
    token = authorization.slice("Bearer ".length);
  } else {
    const session = await sessionAccessToken(request);
    if (!session) {
      return NextResponse.json(
        { detail: "Missing Authorization header" },
        { status: 401 },
      );
    }
    token = session.token;
    rotatedRefreshToken = session.refreshToken;
  }

  const pathname = request.nextUrl.pathname.replace(/^\/api\/v1\//, "");
  const path = `/${pathname}${request.nextUrl.search}`;
  // Segment comes from the pathname only - the query string belongs to the
  // last segment and must not leak into the target selection
  // (e.g. /api/v1/documents?page=1&page_size=20 must route to core, not
  // identity; otherwise backends answer RFC 7807 404 for the missed route).
  const segment = pathname.split("/")[0];

  // Binary file downloads are streamed straight through (the envelope JSON
  // wrappers below would mangle the byte stream).
  if (path.split("?")[0].endsWith("/download")) {
    const raw = await callBackendRaw(path, {
      target: "core",
      tenantSlug: slug,
      token,
    });
    const downloadResponse = async (): Promise<NextResponse> => {
      if (!raw) {
        return NextResponse.json(
          { detail: "Core service is unavailable. Please try again." },
          { status: 502 },
        );
      }
      const body = await raw.arrayBuffer();
      return new NextResponse(body, {
        status: raw.status,
        headers: {
          "Content-Type": raw.headers.get("content-type") ?? "application/octet-stream",
          "Content-Disposition":
            raw.headers.get("content-disposition") ?? 'attachment; filename="download"',
        },
      });
    };
    const response = await downloadResponse();
    if (rotatedRefreshToken) applySessionCookie(response, rotatedRefreshToken);
    return response;
  }

  const target = ["crm", "sales", "finance", "inventory", "hr", "payroll", "portal", "ai", "dashboards", "reports", "documents", "notifications"].includes(
    segment,
  )
    ? "core"
    : "identity";
  const contentType = request.headers.get("content-type") ?? "";
  const isMultipart = contentType.toLowerCase().includes("multipart/form-data");
  // Multipart uploads (documents) are forwarded as FormData; everything else
  // is buffered and re-serialized as JSON.
  const body =
    SAFE_METHODS.has(request.method.toUpperCase())
      ? undefined
      : isMultipart
        ? await request.formData().catch(() => undefined)
        : await request.json().catch(() => undefined);

  const result = await callBackend(path, {
    method: request.method as "GET" | "POST" | "PUT" | "PATCH" | "DELETE",
    body: isMultipart ? undefined : body,
    formData: isMultipart ? (body as FormData | undefined) : undefined,
    tenantSlug: slug,
    token,
    target,
  });

  if (result.status === 0) {
    const service = target === "core" ? "Core service" : "Identity service";
    return NextResponse.json(
      { detail: `${service} is unavailable. Please try again.` },
      { status: 502 },
    );
  }

  const response = NextResponse.json(result.payload, { status: result.status });
  if (result.retryAfter) {
    // Relay the backend rate-limit backoff header (survives identity AND the
    // core -> ai-agent hop for /api/v1/ai/*).
    response.headers.set("Retry-After", result.retryAfter);
  }
  if (rotatedRefreshToken) applySessionCookie(response, rotatedRefreshToken);
  return response;
}

export const GET = proxy;
export const POST = proxy;
export const PUT = proxy;
export const PATCH = proxy;
export const DELETE = proxy;
