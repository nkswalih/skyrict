/**
 * Authenticated fetch wrapper for /api/v1 calls.
 *
 * Attaches the in-memory Bearer token and X-Tenant-Slug, and on a 401
 * performs a single-flight silent refresh through the BFF (the refresh token
 * lives in an httpOnly cookie the browser cannot read), then retries once.
 */

import {
  classifyError,
  errorUserMessage,
  type ErrorKind,
} from "@/lib/api/error-messages";
import { getAccessToken, getTenantSlug, setAccessToken } from "@/lib/auth/session-store";
import { browserSigninUrl } from "@/lib/auth/client-urls";

export class ApiError extends Error {
  readonly status: number;
  /**
   * Normalized failure category (see `classifyError` in error-messages).
   * Lets error surfaces decide copy/retry policy without string-matching.
   */
  readonly kind: ErrorKind;
  /**
   * The raw backend detail, kept for logs and devtools. Never render this
   * directly - `message` is already user-safe (see `toApiError`).
   */
  readonly detail: string;
  /** True when the backend refused the call because a permission key is missing. */
  readonly permissionDenied: boolean;

  constructor(
    status: number,
    message: string,
    options: { detail?: string; permissionDenied?: boolean } = {},
  ) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.kind = classifyError(status);
    this.detail = options.detail ?? message;
    this.permissionDenied = options.permissionDenied ?? false;
  }
}

/**
 * What a user sees when the backend refuses a call for a missing permission.
 *
 * The raw detail ("Missing required permission: erp.crm.read") names internal
 * permission keys - developer/audit information. It is logged through
 * `console.warn` and kept on `ApiError.detail`, never used as page UI.
 */
export const PERMISSION_DENIED_MESSAGE =
  "You don't have permission to access this. Ask a workspace owner for access.";

/** The backends' missing-permission refusal, across the error shapes they emit. */
function isPermissionDenial(detail: string): boolean {
  return (
    /missing required permission/i.test(detail) ||
    /insufficient[_\s-]?permissions/i.test(detail)
  );
}

/**
 * Build the error for a failed response. A 403 that is the backend's
 * missing-permission refusal is normalized to a user-safe message. Transport
 * failures (5xx/408/429) get a status-safe copy so raw backend detail never
 * reaches the UI - it can name internal services or leak stack fragments -
 * while the raw text stays on `ApiError.detail` and is logged. Every other
 * failure keeps its own detail so genuine causes stay diagnosable.
 *
 * This is a UX/leak guard, NOT authorization: the backend still decides, and a
 * caller that needs the key (debugging, telemetry) reads `ApiError.detail`.
 */
function toApiError(status: number, detail: string): ApiError {
  if (status === 403 && isPermissionDenial(detail)) {
    console.warn(`[api] permission denied: ${detail}`);
    return new ApiError(status, PERMISSION_DENIED_MESSAGE, {
      detail,
      permissionDenied: true,
    });
  }
  const userMessage = errorUserMessage(status);
  if (userMessage !== null) {
    console.warn(`[api] ${classifyError(status)}: ${detail}`);
    return new ApiError(status, userMessage, { detail });
  }
  return new ApiError(status, detail, { detail });
}

export interface PaginationMeta {
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

let refreshPromise: Promise<boolean> | null = null;

let sessionLostRedirectPending = false;

/**
 * The session has definitively ended - the refresh token was rejected or
 * revoked. Clear the in-memory access token and leave the workspace origin
 * for the tenant's signin surface exactly once, so the app never keeps
 * retrying a dead session (which re-arms the backend's reuse detector and
 * re-logs the same revocation on every attempt).
 */
export function handleSessionLost(): void {
  if (typeof window === "undefined" || sessionLostRedirectPending) return;
  const target = browserSigninUrl();
  if (target === window.location.href) return;
  sessionLostRedirectPending = true;
  setAccessToken(null);
  window.location.assign(target);
}

function refreshAccessToken(): Promise<boolean> {
  if (!refreshPromise) {
    refreshPromise = fetch("/api/auth/refresh", { method: "POST", cache: "no-store" })
      .then(async (response) => {
        if (!response.ok) {
          if (response.status === 401) handleSessionLost();
          return false;
        }
        const payload = (await response.json().catch(() => ({}))) as {
          status?: string;
          accessToken?: string | null;
        };
        if (payload.status === "authenticated" && payload.accessToken) {
          setAccessToken(payload.accessToken);
          return true;
        }
        return false;
      })
      .finally(() => {
        refreshPromise = null;
      });
  }
  return refreshPromise;
}

interface HydratedSession {
  accessToken: string;
  user: Record<string, unknown> | null;
}

let sessionPromise: Promise<HydratedSession | null> | null = null;

/**
 * Restore the in-memory access token from the httpOnly session cookie via
 * /api/auth/session, single-flight. Every consumer (SessionProvider and the
 * authenticated /api/v1 client) shares one request so that exactly one
 * server-side refresh-token rotation happens per page load - concurrent
 * rotations from the same token would be flagged as reuse and revoke the
 * whole token family.
 */
export function ensureSession(): Promise<HydratedSession | null> {
  if (getAccessToken()) {
    return Promise.resolve({ accessToken: getAccessToken() as string, user: null });
  }
  if (!sessionPromise) {
    sessionPromise = fetch("/api/auth/session", { cache: "no-store" })
      .then(async (response) => {
        if (response.status === 401) handleSessionLost();
        const payload = (await response.json().catch(() => ({}))) as {
          authenticated?: boolean;
          accessToken?: string | null;
          user?: Record<string, unknown> | null;
        };
        if (response.ok && payload.authenticated && payload.accessToken) {
          setAccessToken(payload.accessToken);
          return { accessToken: payload.accessToken, user: payload.user ?? null };
        }
        return null;
      })
      .finally(() => {
        sessionPromise = null;
      });
  }
  return sessionPromise;
}

async function toResult<T>(response: Response): Promise<T> {
  return readPayload<T>(response).then(({ data }) => data);
}

interface Envelope<T> {
  data: T;
  meta: PaginationMeta | null;
}

interface ValidationIssue {
  loc?: unknown[];
  msg?: string;
}

async function readPayload<T>(response: Response): Promise<Envelope<T>> {
  const payload = (await response.json().catch(() => ({}))) as {
    data?: T | null;
    meta?: PaginationMeta | null;
    detail?:
      | { error?: { message?: string }; message?: string }
      | string
      | ValidationIssue[];
  };
  if (!response.ok) {
    throw toApiError(response.status, extractErrorMessage(payload.detail));
  }
  const hasData = payload && "data" in payload;
  return {
    data: (hasData ? payload.data : (payload as unknown)) as T,
    meta: payload.meta ?? null,
  };
}

/**
 * Normalize every error shape the backends produce into one human message:
 * the envelope's `{error: {message}}`, plain strings, and FastAPI's 422
 * validation array (`[{loc: ["body", "email"], msg: "…"}]`).
 *
 * Exported for `onApiError` in @/lib/api/error-toast so the toast surface
 * shows the exact same message the inline error states render.
 */
export function extractErrorMessage(
  detail:
    | { error?: { message?: string }; message?: string }
    | string
    | ValidationIssue[]
    | undefined,
): string {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    const issues = detail
      .map((issue) => {
        const field = Array.isArray(issue.loc)
          ? issue.loc.filter((part) => part !== "body").join(".")
          : "";
        const text = issue.msg ?? "invalid value";
        return field ? `${field}: ${text}` : text;
      })
      .join("; ");
    return issues || "Request failed. Please try again.";
  }
  if (typeof detail === "object" && detail !== null) {
    return detail.error?.message ?? detail.message ?? "Request failed. Please try again.";
  }
  return "Request failed. Please try again.";
}

/**
 * In-flight GET coalescing for the JSON client (see PERF-WEB-002).
 *
 * Identical concurrent GETs share ONE network request and the same parsed
 * result. In-flight only: a settled request is never reused (freshness is
 * owned by resource-cache/modules TTLs), and failures are not cached so the
 * next caller retries. Raw-Response consumers (apiFetchRaw, fetchWithSession,
 * SSE streams) are intentionally excluded: a Response body is
 * single-consumption and streams may carry their own AbortSignal.
 */
const inFlightGets = new Map<string, Promise<unknown>>();

function getDedupeKey(path: string, options: RequestInit): string | null {
  const method = (options.method ?? "GET").toUpperCase();
  if (method !== "GET") return null; // mutations are never coalesced
  if (options.signal) return null; // abort-capable callers own their request
  return `GET ${path}`;
}

function dedupeGet<T>(path: string, options: RequestInit, run: () => Promise<T>): Promise<T> {
  const key = getDedupeKey(path, options);
  if (!key) return run();
  const pending = inFlightGets.get(key);
  if (pending) return pending as Promise<T>;
  const promise = run().finally(() => {
    if (inFlightGets.get(key) === promise) inFlightGets.delete(key);
  });
  inFlightGets.set(key, promise);
  return promise;
}

/**
 * Fetch a `/api/v1` endpoint with session hydration/refresh, returning the
 * full (unparsed) `Response`.
 *
 * Exported so streaming consumers (SSE chat) reuse the exact same token
 * hydration/refresh path as the JSON API client instead of duplicating it.
 */
export async function fetchWithSession(path: string, options: RequestInit): Promise<Response> {
  const headers = new Headers(options.headers);
  headers.set("X-Tenant-Slug", getTenantSlug());

  // Hydrate the in-memory access token BEFORE the first request.
  //
  // On a fresh page load the access token exists only in the httpOnly session
  // cookie, so firing blind guarantees a 401 + full retry on the very first
  // call of every page load. `ensureSession` is single-flight and memoized, so
  // this costs nothing after the first call and preserves the "exactly one
  // server-side rotation per page load" invariant.
  //
  // The outcome is recorded so the 401 handler below never repeats a hydration
  // we already performed:
  //   "ok"      -> a token was obtained and attached
  //   "none"    -> hydration resolved and there is no session (redirect below)
  //   "unknown" -> hydration could not complete (transport error)
  let hydrated: "ok" | "none" | "unknown" | null = null;
  if (!getAccessToken()) {
    try {
      const session = await ensureSession();
      hydrated = session ? "ok" : "none";
      if (session) {
        headers.set("Authorization", `Bearer ${session.accessToken}`);
      }
    } catch {
      // A hydration transport failure must not mask the request itself: fall
      // through, let the endpoint answer, and leave the 401 to the caller.
      hydrated = "unknown";
    }
  }

  const token = getAccessToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (options.body != null && !headers.has("Content-Type")) {
    // Let the browser set the multipart boundary for FormData bodies instead
    // of forcing application/json (which would break uploads).
    if (!(options.body instanceof FormData)) {
      headers.set("Content-Type", "application/json");
    }
  }

  let response = await fetch(path, { ...options, headers });

  // A 401 means the access token is missing (fresh page load on the workspace
  // origin, where the token only lives in memory) or stale. Hydrate/refresh
  // silently through the BFF - the refresh token lives in an httpOnly cookie -
  // then retry once. If the refresh itself fails the session is gone and the
  // caller surfaces the 401. Both recovery paths are single-flight so exactly
  // one server-side token rotation happens at a time.
  if (response.status === 401) {
    if (token) {
      const refreshed = await refreshAccessToken();
      if (refreshed) {
        const fresh = getAccessToken();
        headers.set("Authorization", `Bearer ${fresh ?? ""}`);
        response = await fetch(path, { ...options, headers });
      } else {
        setAccessToken(null);
      }
    } else if (hydrated === "none") {
      // Hydration already told us there is no session to recover - go straight
      // to the lost-session exit instead of repeating the round trip.
      setAccessToken(null);
      handleSessionLost();
    } else if (hydrated === null) {
      // No hydration was attempted (an access token was present but was
      // cleared concurrently): hydrate once, then retry.
      const session = await ensureSession();
      if (session) {
        headers.set("Authorization", `Bearer ${session.accessToken}`);
        response = await fetch(path, { ...options, headers });
      } else {
        setAccessToken(null);
        handleSessionLost();
      }
    }
    // hydrated === "unknown": the session could not be checked (transport
    // failure). Surface the endpoint's own error rather than bouncing a user
    // with a valid session to the sign-in surface.
  }

  return response;
}

export async function apiFetch<T>(path: string, options: RequestInit = {}): Promise<T> {
  return dedupeGet(path, options, () =>
    fetchWithSession(path, options).then((response) => toResult<T>(response)),
  );
}

/**
 * Bare authenticated fetch for binary responses (PDFs, files). Same session
 * hydration/refresh chain as `apiFetch`, but returns the raw `Response` so the
 * caller can read a blob instead of an envelope body.
 */
export async function apiFetchRaw(path: string, options: RequestInit = {}): Promise<Response> {
  return fetchWithSession(path, options);
}

export async function apiFetchWithMeta<T>(
  path: string,
  options: RequestInit = {},
): Promise<Envelope<T>> {
  return dedupeGet(path, options, () =>
    fetchWithSession(path, options).then((response) => readPayload<T>(response)),
  );
}

export { apiFetchWithMeta as apiFetchEnvelope };

async function readBody<T>(response: Response): Promise<T> {
  const payload = (await response.json().catch(() => ({}))) as {
    data?: unknown;
    meta?: PaginationMeta | null;
    detail?: { error?: { message?: string }; message?: string } | string;
  };
  if (!response.ok) {
    const message =
      (typeof payload.detail === "object" && payload.detail?.error?.message) ||
      (typeof payload.detail === "object" && payload.detail?.message) ||
      (typeof payload.detail === "string" ? payload.detail : null) ||
      "Request failed. Please try again.";
    throw toApiError(response.status, message);
  }
  return payload as T;
}

/** Fetch a `/api/v1` endpoint and return the FULL response body (no envelope unwrap). */
export async function apiFetchBody<T>(path: string, options: RequestInit = {}): Promise<T> {
  return dedupeGet(path, options, () =>
    fetchWithSession(path, options).then((response) => readBody<T>(response)),
  );
}

export async function apiPost<T>(path: string, body: unknown): Promise<T> {
  return apiFetch<T>(path, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

/** POST a `/api/v1` endpoint and return the FULL response body (no envelope unwrap). */
export async function apiPostBody<T>(path: string, body: unknown): Promise<T> {
  return apiFetchBody<T>(path, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function apiPatch<T>(path: string, body: unknown): Promise<T> {
  return apiFetch<T>(path, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

export async function apiDelete<T>(path: string): Promise<T> {
  return apiFetch<T>(path, { method: "DELETE" });
}

export interface Paginated<T> {
  items: T[];
  meta: PaginationMeta;
}

/**
 * Serialize a query-string record, dropping null/undefined/empty values so a
 * cleared filter is simply omitted rather than sent as a falsy literal.
 */
export function buildQueryString(
  params: Record<string, string | number | boolean | null | undefined>,
): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === "") continue;
    search.set(key, String(value));
  }
  const query = search.toString();
  return query ? `?${query}` : "";
}

/**
 * Fetch a list endpoint with the backend's `limit`/`offset` pagination and
 * synthesize a frontend `PaginationMeta`.
 *
 * The core backend returns bare arrays (no envelope meta), so the client
 * probes with `limit + 1` to detect a following page. When a full page is
 * returned the probe reveals exactly one extra row - enough to know there IS a
 * next page - and `total`/`total_pages` are reported honestly ("at least this
 * many") rather than guessed. The probe is clamped to the backend's limit cap
 * of 100, so page sizes at the cap report a single page.
 */
export async function apiList<T>(
  path: string,
  input: {
    page?: number;
    pageSize?: number;
    query?: Record<string, string | number | boolean | null | undefined>;
  } = {},
): Promise<Paginated<T>> {
  const page = Math.max(1, input.page ?? 1);
  const pageSize = Math.max(1, Math.min(input.pageSize ?? 20, 100));
  const offset = (page - 1) * pageSize;
  const probeLimit = Math.min(pageSize + 1, 100);

  const rows = await apiFetch<T[]>(
    `${path}${buildQueryString({
      limit: probeLimit,
      offset,
      ...input.query,
    })}`,
  );
  const all = rows ?? [];
  const hasMore = all.length > pageSize;
  const items = hasMore ? all.slice(0, pageSize) : all;

  return {
    items,
    meta: {
      total: offset + all.length,
      page,
      page_size: pageSize,
      total_pages: hasMore ? page + 1 : page,
    },
  };
}
