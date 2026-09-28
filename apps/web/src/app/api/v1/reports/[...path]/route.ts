/**
 * Reports BFF proxy segment (RPT-BE-001).
 *
 * ``/api/v1/reports/**`` is forwarded to the Core service like every other ERP
 * segment. The one extra behavior: when the Core service is unreachable, a
 * GET of the bare list (``/api/v1/reports``) answers with the sample
 * ``reportsKpis`` payload so the ERP reports widget still renders during local
 * development with the backend down - every other reports call returns the
 * standard 502. The fallback is marked with ``X-Mock-Fallback: true`` so the
 * UI (and tests) can tell sample data from live data.
 */

import type { NextRequest } from "next/server";
import { NextResponse } from "next/server";

import { reportsKpis } from "@/lib/mock/erp";
import { resolveBffAuth } from "@/lib/server/bff-auth";
import {
  applySessionCookie,
  assertSameOrigin,
  callBackend,
  callBackendStream,
  resolveTenantSlug,
} from "@/lib/server/auth";

export const dynamic = "force-dynamic";

const SAFE_METHODS = new Set(["GET", "HEAD", "OPTIONS"]);

function isBareListRequest(path: string, method: string): boolean {
  const withoutQuery = path.split("?")[0].replace(/\/$/, "");
  return method === "GET" && withoutQuery === "/reports";
}

/**
 * CSV export (`POST /reports/{slug}/export`) is the only reports response
 * that is not JSON: Core streams `text/csv` with a Content-Disposition
 * attachment. Buffering it through `callBackend`'s JSON parser would turn the
 * CSV body into `{}` (a downloaded file containing only braces), so this
 * branch is relayed with the raw upstream response instead.
 */
function isExportRequest(path: string, method: string): boolean {
  const withoutQuery = path.split("?")[0].replace(/\/$/, "");
  return method === "POST" && /^\/reports\/[^/]+\/export$/.test(withoutQuery);
}

async function reportsProxy(request: NextRequest): Promise<Response> {
  if (SAFE_METHODS.has(request.method.toUpperCase()) === false && !assertSameOrigin(request)) {
    return NextResponse.json({ detail: "Invalid request origin." }, { status: 403 });
  }

  const path = `/${request.nextUrl.pathname.replace(/^\/api\/v1\//, "")}${request.nextUrl.search}`;
  const body =
    SAFE_METHODS.has(request.method.toUpperCase()) || !request.body
      ? undefined
      : await request.json().catch(() => undefined);

  // Resolve the access token. Bearer headers (the client's in-memory access
  // token) win; raw same-origin fetches carry only the session cookie, so
  // mint a fresh access token from it server-side and write the rotated
  // refresh cookie back on the response. Shared with every other BFF route -
  // see pre-release audit finding 26.
  const auth = await resolveBffAuth(request);
  if (!auth.ok) return auth.response;
  const { token, rotatedRefreshToken } = auth;
  const tenantSlug = resolveTenantSlug(request.headers.get("host"));

  // Relay CSV exports without buffering the body: only the download-relevant
  // headers survive, the upstream body streams to the browser as-is.
  if (isExportRequest(path, request.method)) {
    const upstream = await callBackendStream(path, {
      method: "POST",
      body,
      tenantSlug,
      token,
      target: "core",
    });
    if (!upstream || !upstream.body) {
      return NextResponse.json(
        { detail: "Core service is unavailable. Please try again." },
        { status: 502 },
      );
    }
    const headers = new Headers();
    for (const name of [
      "Content-Type",
      "Content-Disposition",
      "X-Report-Rows",
      "X-Report-Period",
    ]) {
      const value = upstream.headers.get(name);
      if (value) headers.set(name, value);
    }
    const response = new NextResponse(upstream.body, {
      status: upstream.status,
      headers,
    });
    if (rotatedRefreshToken) applySessionCookie(response, rotatedRefreshToken);
    return response;
  }

  const result = await callBackend(path, {
    method: request.method as "GET" | "POST" | "PUT" | "PATCH" | "DELETE",
    body,
    tenantSlug,
    token,
    target: "core",
  });

  if (result.status === 0) {
    let response: NextResponse;
    if (isBareListRequest(path, request.method)) {
      response = NextResponse.json(
        {
          data: { kpis: reportsKpis },
          message: "Core service is unavailable. Showing sample report metrics.",
        },
        { status: 200, headers: { "X-Mock-Fallback": "true" } },
      );
    } else {
      response = NextResponse.json(
        { detail: "Core service is unavailable. Please try again." },
        { status: 502 },
      );
    }
    if (rotatedRefreshToken) applySessionCookie(response, rotatedRefreshToken);
    return response;
  }

  const response = NextResponse.json(result.payload, { status: result.status });
  if (rotatedRefreshToken) applySessionCookie(response, rotatedRefreshToken);
  return response;
}

export const GET = reportsProxy;
export const POST = reportsProxy;
export const PUT = reportsProxy;
export const PATCH = reportsProxy;
export const DELETE = reportsProxy;
