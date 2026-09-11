/**
 * Server-side auth BFF helpers.
 *
 * The browser never talks to the identity service's /auth/* endpoints
 * directly for login: it calls these same-origin route handlers, which
 * (a) enforce the Origin/Referer CSRF check, (b) resolve the tenant slug
 * from the Host header the same way the backend does, and (c) write the
 * refresh token into an httpOnly cookie. The access token is returned in
 * the JSON body and kept in memory by the client - never in storage, never
 * readable by third-party scripts.
 */

import type { NextRequest } from "next/server";
import { NextResponse } from "next/server";

import { RESERVED_SLUGS } from "@/lib/auth/reserved-slugs";

export const SESSION_COOKIE = "skyrict_session";

const SESSION_MAX_AGE_SECONDS = 7 * 24 * 60 * 60;

export function apiBase(target?: string): string {
  if (target === "core") {
    return process.env.CORE_PROXY_TARGET ?? "http://localhost:8001";
  }
  return process.env.API_PROXY_TARGET ?? "http://localhost:8000";
}

export type Surface = "marketing" | "signup" | "signin" | "workspace" | "unknown";

const APEX_HOST = /^([a-z0-9-]+)\.(localhost|skyrict\.com)$/;
const SIGNIN_HOST = /^([a-z0-9-]+)\.signin\.(localhost|skyrict\.com)$/;

/**
 * Resolve which of the four subdomain surfaces a Host header maps to.
 *
 * The regexes are *parsers*, not gates: hosts that do not match an allowlisted
 * origin (dev: `*.localhost` + `localhost`; prod: `*.skyrict.com`,
 * `*.signin.skyrict.com`) resolve to `unknown` and are rejected downstream -
 * no acme fallback, no env fallback in the production posture.
 */
export function hostSurface(
  host: string | null | undefined,
): { surface: Surface; slug: string } {
  const value = (host ?? "").trim().toLowerCase().replace(/:\d+$/, "");
  if (value === "localhost" || value === "127.0.0.1" || value === "skyrict.com") {
    return { surface: "marketing", slug: "" };
  }
  const signin = SIGNIN_HOST.exec(value);
  if (signin) {
    if (RESERVED_SLUGS.has(signin[1])) return { surface: "unknown", slug: "" };
    return { surface: "signin", slug: signin[1] };
  }
  const apex = APEX_HOST.exec(value);
  if (apex) {
    const label = apex[1];
    if (label === "web") return { surface: "marketing", slug: "" };
    if (label === "signup") return { surface: "signup", slug: "" };
    if (RESERVED_SLUGS.has(label)) return { surface: "unknown", slug: "" };
    return { surface: "workspace", slug: label };
  }
  return { surface: "unknown", slug: "" };
}

/**
 * Tenant slug from the Host header, mirroring the backend TenantResolver.
 *
 * The slug always comes from the validated Host. `TENANT_SLUG` is a dev-only
 * convenience for hitting the app without a tenant subdomain and is never used
 * in the production posture.
 */
export function resolveTenantSlug(host: string | null | undefined): string {
  const { slug } = hostSurface(host);
  if (slug) return slug;
  if (process.env.NODE_ENV === "production") return "";
  return process.env.TENANT_SLUG ?? "";
}

/**
 * CSRF gate for state-changing routes: the request must come from our own
 * origin (matching Host). SameSite=Lax already stops cross-site POSTs from
 * carrying the cookie; this is defense in depth for older browsers.
 *
 * When the browser sends an `Origin` header it must match Host. Browsers omit
 * `Origin` on same-origin GET/HEAD/OPTIONS requests (e.g. fetching the
 * CAPTCHA challenge), so those safe methods pass when no header is present;
 * state-changing requests are rejected without a matching `Origin`.
 */
export function assertSameOrigin(request: NextRequest): boolean {
  const origin = request.headers.get("origin");
  const host = request.headers.get("host");
  if (!host) return false;
  if (origin) {
    try {
      return new URL(origin).host === host;
    } catch {
      return false;
    }
  }
  const method = request.method.toUpperCase();
  return method === "GET" || method === "HEAD" || method === "OPTIONS";
}

interface BackendCallOptions {
  method?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  body?: unknown;
  /** Raw multipart body (uploads). Forwarded as-is; the fetch client sets the
   *  multipart boundary, so no JSON content-type is added. */
  formData?: FormData | null;
  token?: string | null;
  tenantSlug?: string | null;
  target?: "identity" | "core";
  userAgent?: string | null;
  clientIp?: string | null;
}

interface BackendCallResult {
  ok: boolean;
  status: number;
  data: Record<string, unknown> | null;
  payload: Record<string, unknown>;
}

/**
 * Whether this Next.js process sits behind a trusted reverse proxy that
 * appends the real client IP to X-Forwarded-For. Defaults to off so the BFF
 * never forwards client-controlled IP headers unless explicitly deployed
 * behind a trusted proxy.
 */
const TRUST_PROXY = process.env.TRUST_PROXY === "true";

/** Resolve the real client IP, or null when it cannot be trusted.
 *
 * Without a trusted proxy in front, forwarded headers come straight from the
 * client and must be ignored (spoofable). Behind a trusted proxy such as
 * ingress-nginx, the *rightmost* X-Forwarded-For entry is the one the proxy
 * appended - the left entries are attacker-controllable and never used.
 */
export function clientIp(request: NextRequest): string | null {
  if (!TRUST_PROXY) return null;
  const forwarded = request.headers.get("x-forwarded-for");
  if (forwarded) {
    const hops = forwarded
      .split(",")
      .map((hop) => hop.trim())
      .filter(Boolean);
    return hops[hops.length - 1] ?? null;
  }
  return request.headers.get("x-real-ip");
}

/** Proxy a call to an internal backend, forwarding tenant + bearer context. */
export async function callBackend(
  path: string,
  options: BackendCallOptions = {},
): Promise<BackendCallResult> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (options.tenantSlug) headers["X-Tenant-Slug"] = options.tenantSlug;
  if (options.token) headers["Authorization"] = `Bearer ${options.token}`;
  if (options.userAgent) headers["User-Agent"] = options.userAgent;
  if (options.clientIp) headers["X-Forwarded-For"] = options.clientIp;

  let response: Response;
  try {
    if (options.formData) {
      // Upload path: forward the raw multipart body. The fetch client sets the
      // multipart boundary, so no JSON Content-Type is attached.
      delete headers["Content-Type"];
      response = await fetch(`${apiBase(options.target)}/api/v1${path}`, {
        method: options.method ?? "POST",
        headers,
        body: options.formData,
        cache: "no-store",
      });
    } else {
      response = await fetch(`${apiBase(options.target)}/api/v1${path}`, {
        method: options.method ?? "POST",
        headers,
        body:
          options.body === undefined
            ? undefined
            : JSON.stringify(options.body),
        cache: "no-store",
      });
    }
  } catch {
    return { ok: false, status: 0, data: null, payload: {} };
  }

  const payload = (await response.json().catch(() => ({}))) as Record<string, unknown>;
  return {
    ok: response.ok,
    status: response.status,
    data: (payload.data as Record<string, unknown> | null) ?? null,
    payload,
  };
}

/**
 * Proxy a call to an internal backend WITHOUT buffering the body.
 *
 * Used by streaming relays (SSE): the caller returns ``upstream.body`` to the
 * browser and chunks flow through as they arrive. On network failure (or when
 * the body is already consumed) returns ``null`` so the route can answer its
 * own 502 - mirroring ``callBackend``'s ``status: 0`` contract.
 */
export async function callBackendStream(
  path: string,
  options: BackendCallOptions = {},
): Promise<Response | null> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (options.tenantSlug) headers["X-Tenant-Slug"] = options.tenantSlug;
  if (options.token) headers["Authorization"] = `Bearer ${options.token}`;
  try {
    return await fetch(`${apiBase(options.target)}/api/v1${path}`, {
      method: options.method ?? "POST",
      headers,
      body: options.body === undefined ? undefined : JSON.stringify(options.body),
      cache: "no-store",
    });
  } catch {
    return null;
  }
}

/**
 * Fetch a backend endpoint and return the raw upstream `Response` so the route
 * can stream binary content (e.g. document downloads) back without buffering
 * through the envelope. On network failure returns `null` (mirrors the
 * `status: 0` contract).
 */
export async function callBackendRaw(
  path: string,
  options: { target: "identity" | "core"; tenantSlug: string; token: string | null },
): Promise<Response | null> {
  const headers: Record<string, string> = {};
  if (options.tenantSlug) headers["X-Tenant-Slug"] = options.tenantSlug;
  if (options.token) headers["Authorization"] = `Bearer ${options.token}`;
  try {
    return await fetch(`${apiBase(options.target)}/api/v1${path}`, {
      method: "GET",
      headers,
      cache: "no-store",
    });
  } catch {
    return null;
  }
}

/** Map the backend snake_case user object to the frontend AuthUser shape. */
export function mapUser(raw: Record<string, unknown> | null | undefined) {
  if (!raw) return null;
  return {
    id: String(raw.id ?? ""),
    email: String(raw.email ?? ""),
    fullName: String(raw.full_name ?? raw.fullName ?? ""),
    isActive: Boolean(raw.is_active ?? raw.isActive),
    isVerified: Boolean(raw.is_verified ?? raw.isVerified),
    mfaEnabled: Boolean(raw.mfa_enabled ?? raw.mfaEnabled),
    createdAt: String(raw.created_at ?? raw.createdAt ?? ""),
    avatarUrl: String(raw.avatar_url ?? raw.avatarUrl ?? ""),
  };
}

/** JSON error response mirroring the backend problem+json contract. */
export function backendError(result: BackendCallResult) {
  if (result.status === 0) {
    // The internal fetch never got a response (backend down / connection
    // refused) - surface a 502 + actionable copy instead of a generic 400.
    return NextResponse.json(
      { error: "Identity service is unavailable. Please try again." },
      { status: 502 },
    );
  }
  const detail = result.payload.detail ?? "Request failed. Please try again.";
  return NextResponse.json({ error: String(detail) }, { status: result.status || 400 });
}

/** Set (or clear, when value is null) the httpOnly refresh-token cookie. */
export function applySessionCookie(response: NextResponse, value: string | null): void {
  response.cookies.set(SESSION_COOKIE, value ?? "", {
    httpOnly: true,
    sameSite: "lax",
    secure: process.env.NODE_ENV === "production",
    path: "/",
    maxAge: value ? SESSION_MAX_AGE_SECONDS : 0,
  });
}
