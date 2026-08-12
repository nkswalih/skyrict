import type { APIRequestContext } from "@playwright/test";

import { API_BASE, signupHost } from "./env";

export class ApiError extends Error {
  readonly status: number;
  readonly type: string | null;
  readonly instance: string | null;

  constructor(
    status: number,
    message: string,
    type: string | null = null,
    instance: string | null = null,
  ) {
    super(message);
    this.status = status;
    this.type = type;
    this.instance = instance;
  }
}

export interface ApiOptions {
  method?: "GET" | "POST" | "PATCH" | "DELETE";
  token?: string;
  slug?: string;
  body?: unknown;
}

/** Call the identity service directly (`/api/v1/...`), decoding the envelope. */
export async function api<T>(
  request: APIRequestContext,
  path: string,
  options: ApiOptions = {},
): Promise<T> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (options.token) headers.Authorization = `Bearer ${options.token}`;
  if (options.slug) headers["X-Tenant-Slug"] = options.slug;

  const response = await request.fetch(`${API_BASE}/api/v1${path}`, {
    method: options.method ?? "POST",
    headers,
    data: options.body === undefined ? undefined : JSON.stringify(options.body),
  });

  const payload = (await response.json().catch(() => ({}))) as {
    data?: T;
    detail?: string;
    type?: string;
    instance?: string;
  };
  if (!response.ok()) {
    throw new ApiError(
      response.status(),
      String(payload.detail ?? `Request failed (${response.status()})`),
      typeof payload.type === "string" ? payload.type : null,
      typeof payload.instance === "string" ? payload.instance : null,
    );
  }
  return payload.data as T;
}

export interface BffOptions {
  method?: "GET" | "POST" | "PATCH" | "DELETE";
  host?: string;
  body?: unknown;
}

/**
 * Call a same-origin web BFF route, faking the browser's Origin/Host so the
 * CSRF gate and host-surface routing behave exactly as in a real browser.
 */
export async function bff<T>(
  request: APIRequestContext,
  path: string,
  options: BffOptions = {},
): Promise<T> {
  const host = options.host ?? signupHost;
  const origin = `http://${host}`;
  const response = await request.fetch(`${origin}${path}`, {
    method: options.method ?? "POST",
    headers: {
      "Content-Type": "application/json",
      Host: host,
      ...(options.method === "GET" ? {} : { Origin: origin }),
    },
    data: options.body === undefined ? undefined : JSON.stringify(options.body),
  });

  const payload = (await response.json().catch(() => ({}))) as {
    error?: string;
  };
  if (!response.ok()) {
    throw new ApiError(
      response.status(),
      String(payload.error ?? `Request failed (${response.status()})`),
    );
  }
  return payload as T;
}
