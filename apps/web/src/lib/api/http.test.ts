/**
 * Tests for the session-hydration contract of the authenticated fetch wrapper.
 *
 * On a fresh page load the access token lives only in the httpOnly session
 * cookie, so firing the first API call blind guaranteed a 401 plus a full
 * retry - one wasted round trip per page load. These tests pin the
 * replacement behaviour: hydrate first, exactly one `/api/auth/session` per
 * page load, and never a blind retry.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError, apiFetch, apiPost, PERMISSION_DENIED_MESSAGE } from "@/lib/api/http";
import {
    RATE_LIMITED_MESSAGE,
    SERVICE_UNAVAILABLE_MESSAGE,
    TIMEOUT_MESSAGE,
} from "@/lib/api/error-messages";
import { getAccessToken, setAccessToken } from "@/lib/auth/session-store";

interface RecordedRequest {
    url: string;
    method: string;
    authorization: string | null;
}

const requests: RecordedRequest[] = [];

function json(body: unknown, status = 200): Response {
    return new Response(JSON.stringify(body), {
        status,
        headers: { "Content-Type": "application/json" },
    });
}

let respond: (url: string, authorization: string | null) => Response;

beforeEach(() => {
    setAccessToken(null);
    requests.length = 0;
    respond = () => json({ data: null });
    vi.stubGlobal(
        "fetch",
        async (input: RequestInfo | URL, init?: RequestInit) => {
            const url = String(input);
            const authorization = new Headers(init?.headers).get(
                "Authorization",
            );
            requests.push({
                url,
                method: init?.method ?? "GET",
                authorization,
            });
            return respond(url, authorization);
        },
    );
});

afterEach(() => {
    vi.unstubAllGlobals();
    setAccessToken(null);
});

function sessionCalls(): RecordedRequest[] {
    return requests.filter((request) => request.url === "/api/auth/session");
}

describe("fetchWithSession hydration", () => {
    it("hydrates the session before the first request instead of eating a 401", async () => {
        respond = (url) =>
            url === "/api/auth/session"
                ? json({
                      authenticated: true,
                      accessToken: "tok-1",
                      user: { id: "u1" },
                  })
                : json({ data: { ok: true } });

        await expect(apiFetch("/api/v1/roles/me")).resolves.toEqual({
            ok: true,
        });

        // Hydration, then ONE authenticated request - no blind 401 first.
        expect(requests.map((request) => request.url)).toEqual([
            "/api/auth/session",
            "/api/v1/roles/me",
        ]);
        expect(requests[1].authorization).toBe("Bearer tok-1");
        expect(getAccessToken()).toBe("tok-1");
    });

    it("uses an in-memory token without a hydration round trip", async () => {
        setAccessToken("tok-9");
        respond = () => json({ data: { ok: true } });

        await apiFetch("/api/v1/roles/me");

        expect(sessionCalls()).toHaveLength(0);
        expect(requests).toHaveLength(1);
        expect(requests[0].authorization).toBe("Bearer tok-9");
    });

    it("does not re-hydrate after a 401 when hydration found no session", async () => {
        respond = (url) =>
            url === "/api/auth/session"
                ? json({ authenticated: false })
                : json({ detail: "Missing Authorization header" }, 401);

        await expect(apiFetch("/api/v1/roles/me")).rejects.toThrow(
            "Missing Authorization header",
        );

        // Hydration + the single request. The previous implementation fired the
        // request blind, absorbed a 401, then hydrated and retried.
        expect(sessionCalls()).toHaveLength(1);
        expect(requests).toHaveLength(2);
    });

    it("refreshes and retries once when an in-memory token is rejected", async () => {
        setAccessToken("stale-token");
        respond = (url, authorization) => {
            if (url === "/api/auth/refresh") {
                return json({
                    status: "authenticated",
                    accessToken: "fresh-token",
                });
            }
            return authorization === "Bearer fresh-token"
                ? json({ data: { ok: true } })
                : json({ detail: "Token expired" }, 401);
        };

        await expect(apiFetch("/api/v1/roles/me")).resolves.toEqual({
            ok: true,
        });

        expect(requests.map((request) => request.url)).toEqual([
            "/api/v1/roles/me",
            "/api/auth/refresh",
            "/api/v1/roles/me",
        ]);
        expect(requests[1].method).toBe("POST");
        expect(getAccessToken()).toBe("fresh-token");
    });
});

describe("permission-denied errors", () => {
    beforeEach(() => {
        vi.spyOn(console, "warn").mockImplementation(() => {});
    });

    afterEach(() => {
        vi.restoreAllMocks();
    });

    it("hides the internal permission key behind a user-safe message", async () => {
        respond = () =>
            json({ detail: "Missing required permission: erp.crm.read" }, 403);

        const error = await apiFetch("/api/v1/crm/leads").then(
            () => null,
            (err: unknown) => err as ApiError,
        );

        expect(error).not.toBeNull();
        expect(error!.status).toBe(403);
        expect(error!.permissionDenied).toBe(true);
        // Page UI renders `message`: it must not name internal keys.
        expect(error!.message).toBe(PERMISSION_DENIED_MESSAGE);
        expect(error!.message).not.toContain("erp.crm.read");
        // The raw detail stays available for logs and debugging.
        expect(error!.detail).toBe("Missing required permission: erp.crm.read");
        expect(console.warn).toHaveBeenCalledWith(
            expect.stringContaining("Missing required permission: erp.crm.read"),
        );
    });

    it("keeps every other failure diagnosable", async () => {
        respond = () => json({ detail: "Only a tenant owner can manage billing" }, 403);

        const error = await apiFetch("/api/v1/billing/plan").then(
            () => null,
            (err: unknown) => err as ApiError,
        );

        expect(error!.permissionDenied).toBe(false);
        expect(error!.message).toBe("Only a tenant owner can manage billing");
    });

    it("does not treat a non-403 failure as a permission denial", async () => {
        respond = () => json({ detail: "Missing required permission: x" }, 400);

        const error = await apiFetch("/api/v1/crm/leads").then(
            () => null,
            (err: unknown) => err as ApiError,
        );

        expect(error!.permissionDenied).toBe(false);
        expect(error!.message).toBe("Missing required permission: x");
    });
});

describe("transport/server failure sanitization", () => {
    beforeEach(() => {
        // Skip session hydration: every /api/v1 call goes straight to `respond`.
        setAccessToken("tok-1");
        vi.spyOn(console, "warn").mockImplementation(() => {});
    });

    afterEach(() => {
        vi.restoreAllMocks();
    });

    it("replaces 503 backend detail with safe copy, keeping detail for logs", async () => {
        respond = () =>
            json(
                { detail: "Identity service is unavailable. Please try again." },
                503,
            );

        const error = await apiFetch("/api/v1/billing/signup/plans").then(
            () => null,
            (err: unknown) => err as ApiError,
        );

        expect(error).not.toBeNull();
        expect(error!.status).toBe(503);
        expect(error!.kind).toBe("service_unavailable");
        // Page UI renders `message`: it must never name internal services.
        expect(error!.message).toBe(SERVICE_UNAVAILABLE_MESSAGE);
        expect(error!.message).not.toContain("Identity service");
        // The raw detail stays available for logs and debugging.
        expect(error!.detail).toBe(
            "Identity service is unavailable. Please try again.",
        );
        expect(console.warn).toHaveBeenCalledWith(
            expect.stringContaining("Identity service is unavailable"),
        );
    });

    it("replaces 500 with safe copy", async () => {
        respond = () => json({ detail: "internal error: traceback ..." }, 500);

        const error = await apiFetch("/api/v1/billing/plan").then(
            () => null,
            (err: unknown) => err as ApiError,
        );

        expect(error!.kind).toBe("server_error");
        expect(error!.message).toBe(SERVICE_UNAVAILABLE_MESSAGE);
        expect(error!.message).not.toContain("traceback");
        expect(error!.detail).toBe("internal error: traceback ...");
    });

    it("replaces 408 and 429 with their safe copies", async () => {
        respond = () => json({ detail: "request timed out" }, 408);

        const timeout = await apiFetch("/api/v1/analytics/timeouts").then(
            () => null,
            (err: unknown) => err as ApiError,
        );
        expect(timeout!.kind).toBe("timeout");
        expect(timeout!.message).toBe(TIMEOUT_MESSAGE);

        respond = () => json({ detail: "Too many requests" }, 429);
        const limited = await apiFetch("/api/v1/analytics/rate").then(
            () => null,
            (err: unknown) => err as ApiError,
        );
        expect(limited!.kind).toBe("rate_limited");
        expect(limited!.message).toBe(RATE_LIMITED_MESSAGE);
    });

    it("keeps backend messages for validation, conflict, and not-found", async () => {
        respond = () => json({ detail: "Email is required" }, 422);
        const validation = await apiFetch("/api/v1/crm/leads").then(
            () => null,
            (err: unknown) => err as ApiError,
        );
        expect(validation!.kind).toBe("validation");
        expect(validation!.message).toBe("Email is required");

        respond = () => json({ detail: "Rule already exists" }, 409);
        const conflict = await apiFetch("/api/v1/automations").then(
            () => null,
            (err: unknown) => err as ApiError,
        );
        expect(conflict!.kind).toBe("conflict");
        expect(conflict!.message).toBe("Rule already exists");

        respond = () => json({ detail: "Not found" }, 404);
        const missing = await apiFetch("/api/v1/invoices/xyz").then(
            () => null,
            (err: unknown) => err as ApiError,
        );
        expect(missing!.kind).toBe("not_found");
        expect(missing!.message).toBe("Not found");
    });

    it("derives kind on directly-constructed ApiErrors (no signature change)", () => {
        const error = new ApiError(403, "forbidden");
        expect(error.kind).toBe("forbidden");
        expect(error.message).toBe("forbidden");
    });
});

describe("in-flight GET deduplication", () => {
    it("coalesces concurrent identical GETs into one network request", async () => {
        setAccessToken("tok-1");
        respond = () => json({ data: { ok: true } });

        await expect(
            Promise.all([
                apiFetch("/api/v1/roles"),
                apiFetch("/api/v1/roles"),
            ]),
        ).resolves.toEqual([{ ok: true }, { ok: true }]);

        expect(
            requests.filter((request) => request.url === "/api/v1/roles"),
        ).toHaveLength(1);
    });

    it("keeps distinct query strings distinct", async () => {
        setAccessToken("tok-1");
        respond = () => json({ data: [] });

        await Promise.all([
            apiFetch("/api/v1/roles?limit=10"),
            apiFetch("/api/v1/roles?limit=20"),
        ]);

        expect(
            requests.filter((request) => request.url.startsWith("/api/v1/roles?")),
        ).toHaveLength(2);
    });

    it("never dedupes POSTs", async () => {
        setAccessToken("tok-1");
        respond = () => json({ data: { ok: true } });

        await Promise.all([
            apiPost("/api/v1/roles", {}),
            apiPost("/api/v1/roles", {}),
        ]);

        expect(
            requests.filter((request) => request.url === "/api/v1/roles"),
        ).toHaveLength(2);
    });

    it("does not reuse a settled GET", async () => {
        setAccessToken("tok-1");
        respond = () => json({ data: { ok: true } });

        await apiFetch("/api/v1/roles");
        await apiFetch("/api/v1/roles");

        expect(
            requests.filter((request) => request.url === "/api/v1/roles"),
        ).toHaveLength(2);
    });

    it("hydrates once when coalescing concurrent calls on a cold token", async () => {
        respond = (url) =>
            url === "/api/auth/session"
                ? json({
                      authenticated: true,
                      accessToken: "tok-1",
                      user: { id: "u1" },
                  })
                : json({ data: { ok: true } });

        await expect(
            Promise.all([
                apiFetch("/api/v1/roles/me"),
                apiFetch("/api/v1/roles/me"),
            ]),
        ).resolves.toEqual([{ ok: true }, { ok: true }]);

        // One hydration round trip and ONE data request - no 401-retry storm.
        expect(sessionCalls()).toHaveLength(1);
        expect(
            requests.filter((request) => request.url === "/api/v1/roles/me"),
        ).toHaveLength(1);
    });

    it("does not poison retries after a rejection", async () => {
        setAccessToken("tok-1");
        let failing = true;
        respond = () =>
            failing ? json({ detail: "boom" }, 500) : json({ data: { ok: true } });

        await expect(apiFetch("/api/v1/roles")).rejects.toThrow(ApiError);

        failing = false;
        await expect(apiFetch("/api/v1/roles")).resolves.toEqual({ ok: true });

        expect(
            requests.filter((request) => request.url === "/api/v1/roles"),
        ).toHaveLength(2);
    });
});