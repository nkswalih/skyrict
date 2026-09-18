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
import { captureBffException } from "@/lib/server/sentry";

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
  /** Upstream Retry-After on 429s, relayed so clients can back off. */
  retryAfter: string | null;
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
  } catch (error) {
    // Network failure reaching the backend. The route answers a generic
    // status-0 result; report the underlying reason to Sentry so a backend
    // outage is visible instead of surfacing only as a bare 502.
    captureBffException(error, path, options.target ?? "identity");
    return { ok: false, status: 0, data: null, payload: {}, retryAfter: null };
  }

  const payload = (await response.json().catch(() => ({}))) as Record<string, unknown>;
  return {
    ok: response.ok,
    status: response.status,
    data: (payload.data as Record<string, unknown> | null) ?? null,
    payload,
    retryAfter: response.headers.get("retry-after"),
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
  } catch (error) {
    captureBffException(error, path, options.target ?? "identity");
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
  } catch (error) {
    captureBffException(error, path, options.target);
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
  const response = NextResponse.json(
    { error: String(detail) },
    { status: result.status || 400 },
  );
  if (result.retryAfter) {
    // Relay the upstream rate-limit backoff so clients can schedule retries.
    response.headers.set("Retry-After", result.retryAfter);
  }
  return response;
}

/**
 * Secure-flag for the session cookie. Defaults to the production posture
 * (Secure only when NODE_ENV=production). The E2E stack serves plain HTTP on
 * loopback-only origins (*.localhost), where Chromium drops Secure cookies, so
 * the CI workflow sets SESSION_COOKIE_SECURE=false for exactly that stack - the
 * loopback transport is explicitly not the boundary under test. Forcing true
 * on a public HTTP origin (or false on a public HTTPS origin) is a
 * misconfiguration and is left to deployment review.
 */
function resolveSessionCookieSecure(): boolean {
  const override = process.env.SESSION_COOKIE_SECURE;
  if (override === "false") return false;
  if (override === "true") return true;
  return process.env.NODE_ENV === "production";
}

/** Set (or clear, when value is null) the httpOnly refresh-token cookie. */
export function applySessionCookie(response: NextResponse, value: string | null): void {
  response.cookies.set(SESSION_COOKIE, value ?? "", {
    httpOnly: true,
    sameSite: "lax",
    secure: resolveSessionCookieSecure(),
    path: "/",
    maxAge: value ? SESSION_MAX_AGE_SECONDS : 0,
  });
}

export interface SessionAccess {
  /** Fresh access token minted by rotating the httpOnly refresh cookie. */
  token: string;
  /** Rotated refresh token to store back in the cookie, when identity rotates. */
  refreshToken: string | null;
  /** Access-token lifetime reported by identity (seconds). */
  expiresIn: number;
}

interface RotatedRefresh {
  /** Fresh access + rotated refresh token when the backend answered OK. */
  access: SessionAccess | null;
  /** The full upstream outcome, for routes that branch on status/detail. */
  result: BackendCallResult;
}

/**
 * Memoized single-flight refresh-token rotation keyed by its value.
 *
 * Identity rotates the refresh token on every hydration and revokes the whole
 * token family if a value is ever presented more than once (reuse detection).
 * The httpOnly cookie is the only cross-request carrier of the refresh value,
 * so several BFF requests that race the same page load - the client's own
 * single-flight ``restore()`` plus a cookie-only /api/v1 call from a
 * component mounted before restore resolves - can carry the same value.
 *
 * Every consumer routes its rotation through this helper: concurrent requests
 * coalesce onto one in-flight call, and the outcome is MEMOIZED (not evicted
 * on settle) so a request arriving after the rotation completed answers from
 * cache instead of re-presenting an already-rotated value to identity. Each
 * refresh value therefore reaches ``/auth/refresh`` exactly once per process.
 * The cache is bounded by a FIFO cap; a fresh cookie value still rotates
 * normally.
 */
const ROTATION_CACHE_MAX = 64;
const refreshRotations = new Map<string, Promise<RotatedRefresh>>();

export function rotateRefreshToken(
  refreshToken: string,
  tenantSlug: string,
): Promise<RotatedRefresh> {
  const key = `${tenantSlug}:${refreshToken}`;
  const pending = refreshRotations.get(key);
  if (pending) return pending;

  const started = callBackend("/auth/refresh", {
    body: { refresh_token: refreshToken },
    tenantSlug,
  }).then((result) => {
    const data = result.data;
    return {
      access:
        result.ok && data && data.access_token
          ? {
              token: String(data.access_token),
              refreshToken:
                typeof data.refresh_token === "string" && data.refresh_token
                  ? data.refresh_token
                  : null,
              expiresIn: typeof data.expires_in === "number" ? data.expires_in : 0,
            }
          : null,
      result,
    } satisfies RotatedRefresh;
  });

  refreshRotations.set(key, started);
  if (refreshRotations.size > ROTATION_CACHE_MAX) {
    const oldest = refreshRotations.keys().next().value;
    if (oldest !== undefined) refreshRotations.delete(oldest);
  }
  return started;
}

/**
 * Resolve a fresh access token from the httpOnly session cookie.
 *
 * Raw same-origin requests (server-side fetches from the BFF proxy, E2E
 * ``page.evaluate`` calls) carry cookies but never an Authorization header.
 * This exchanges the refresh cookie for an access token exactly like
 * ``POST /api/auth/refresh`` does - rotating the refresh cookie - so the
 * caller can forward the token downstream and store the rotated refresh
 * cookie back on the response. Returns null when no cookie exists or the
 * refresh failed; the caller must answer 401.
 *
 * The rotation is the memoized single-flight ``rotateRefreshToken`` shared
 * with the /api/auth/session and /api/auth/refresh routes, so a cookie-only
 * BFF call that races the client's own restore() never re-presents a refresh
 * value identity is already rotating.
 */
export async function sessionAccessToken(
  request: NextRequest,
): Promise<SessionAccess | null> {
  const refreshToken = request.cookies.get(SESSION_COOKIE)?.value;
  if (!refreshToken) return null;

  const slug = resolveTenantSlug(request.headers.get("host"));
  const rotated = await rotateRefreshToken(refreshToken, slug);
  return rotated.access;
}
