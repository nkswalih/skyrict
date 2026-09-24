/*
 * BFF API helper for E2E tests.
 *
 * Wraps page.request (which shares the browser-context cookie jar) and
 * lazily hydrates the access token via GET /api/auth/session.  Every
 * non-safe method sends an explicit Origin header so the BFF's CSRF gate
 * (assertSameOrigin) passes — Playwright's APIRequestContext omits Origin
 * by default.
 *
 * All rotations (API /api/auth/session, page hydration) MUST stay strictly
 * sequential in one test() body — never present the same refresh token twice
 * within the same session family.
 */

import type { APIRequestContext } from "@playwright/test";

const BASE_URL = process.env.E2E_BASE_URL ?? "http://default.localhost:3000";

// ---------------------------------------------------------------------------
// Error helpers
// ---------------------------------------------------------------------------

export class BffError extends Error {
    readonly status: number;
    constructor(status: number, message: string) {
        super(message);
        this.status = status;
    }
}

function extractMessage(detail: unknown): string {
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail)) {
        return detail
            .map((d: unknown) =>
                typeof d === "string"
                    ? d
                    : ((d as Record<string, unknown>)?.msg ?? ""),
            )
            .join("; ");
    }
    if (detail && typeof detail === "object") {
        const rec = detail as Record<string, unknown>;
        if (typeof rec.message === "string") return rec.message;
    }
    return "";
}

// ---------------------------------------------------------------------------
// BffApi
// ---------------------------------------------------------------------------

interface Envelope<T> {
    data?: T;
    meta?: unknown;
    detail?: unknown;
}

export class BffApi {
    private token: string | null = null;
    private tokenPromise: Promise<string | null> | null = null;
    private readonly origin: string;
    private readonly fixedToken: string | null;

    constructor(
        private readonly request: APIRequestContext,
        options: { origin?: string; bearerToken?: string | null } = {},
    ) {
        // `origin` drives the CSRF Origin header and must match the Host the
        // request actually hits (e.g. http://second.localhost:3000 for
        // cross-tenant isolation tests).
        this.origin = options.origin ?? BASE_URL;
        this.fixedToken = options.bearerToken ?? null;
    }

    private async accessToken(): Promise<string | null> {
        if (this.fixedToken) return this.fixedToken;
        if (!this.tokenPromise) {
            this.tokenPromise = this.fetchAccessToken().finally(() => {
                this.tokenPromise = null;
            });
        }
        return this.tokenPromise;
    }

    /** GET /api/auth/session through the shared cookie jar. */
    private async readSession(): Promise<{
        body: { accessToken?: string | null; authenticated?: boolean };
    }> {
        const response = await this.request.get("/api/auth/session");
        if (!response.ok()) {
            // 401/500 from the session route is the signature of a revoked or
            // unusable refresh family - surface it now instead of sending an
            // unauthenticated request that fails later with the backend's
            // generic 401.
            throw new Error(
                `Session restore failed with HTTP ${response.status()}` +
                    ` (${await response.text().catch(() => "")})`,
            );
        }
        return {
            body: (await response.json().catch(() => ({}))) as {
                accessToken?: string | null;
                authenticated?: boolean;
            },
        };
    }

    private async fetchAccessToken(): Promise<string | null> {
        let { body } = await this.readSession();

        if (!body.accessToken) {
            // The BFF returns 200 {authenticated:false} in two very different
            // situations: (1) the refresh rotation succeeded but the /users/me
            // profile probe blipped - the rotated refresh cookie is STILL in
            // the jar, so a retry succeeds; or (2) identity rejected the
            // refresh (reuse/revoke or a network dead-end) and the BFF cleared
            // the cookie, so the retry fails fast with the same body. Retry
            // once with a short backoff so a transient cold-stack probe
            // failure cannot kill the whole worker run; the cleared-cookie
            // case is unchanged in outcome.
            await new Promise((resolve) => setTimeout(resolve, 500));
            body = (await this.readSession()).body;
        }

        // Authenticated workspace calls run under the username fixture, so a
        // session response with no access token is a real failure. Throw with
        // the payload and the jar state so CI pins down whether identity
        // rejected the refresh, the /users/me probe failed, or the cookie was
        // cleared - not the misleading downstream 401.
        const token = body.accessToken ?? null;
        if (!token) {
            const state = await this.request.storageState().catch(() => null);
            const sessionCookiePresent =
                state?.cookies.some(
                    (cookie) => cookie.name === "skyrict_session",
                ) ?? false;
            throw new Error(
                `Authenticated session returned no access token` +
                    ` (session: ${JSON.stringify(body)}, ` +
                    `sessionCookiePresent: ${sessionCookiePresent})`,
            );
        }
        this.token = token;
        return token;
    }

    async raw<T>(
        path: string,
        init: RequestInit = {},
    ): Promise<{ ok: boolean; status: number; retryAfter: string | null; payload: T }> {
        const token = await this.accessToken();
        const method = (init.method ?? "GET").toUpperCase();
        const headers: Record<string, string> = {};
        if (init.headers) {
            const h = init.headers;
            if (h instanceof Headers) {
                h.forEach((value, key) => {
                    headers[key] = value;
                });
            } else if (Array.isArray(h)) {
                for (const [key, value] of h) headers[key] = value;
            } else {
                Object.assign(headers, h);
            }
        }
        if (token) headers["Authorization"] = `Bearer ${token}`;
        if (init.body != null && !headers["Content-Type"]) {
            headers["Content-Type"] = "application/json";
        }
        if (method !== "GET" && method !== "HEAD" && method !== "OPTIONS") {
            headers["Origin"] = this.origin;
        }

        const response = await this.request.fetch(path, {
            method,
            headers,
            // Playwright posts `data` as the raw body; JSON strings keep our
            // content-type while staying inside Playwright's option shape.
            data: init.body ?? undefined,
        });
        const payload = (await response
            .json()
            .catch(() => ({}))) as Envelope<unknown>;

        return {
            ok: response.ok(),
            status: response.status(),
            retryAfter: response.headers()["retry-after"] ?? null,
            payload: ("data" in payload ? payload.data : payload) as T,
        };
    }

    async call<T>(path: string, init: RequestInit = {}): Promise<T> {
        const { ok, status, payload } = await this.raw<T>(path, init);
        if (!ok) {
            const detail = (
                payload as unknown as { detail?: unknown }
            )?.detail;
            const message =
                extractMessage(detail) ?? `Request failed (${status})`;
            throw new BffError(status, message);
        }
        return payload;
    }

    get<T>(path: string): Promise<T> {
        return this.call<T>(path, { method: "GET" });
    }

    post<T>(path: string, body?: unknown): Promise<T> {
        return this.call<T>(path, {
            method: "POST",
            body: body === undefined ? undefined : JSON.stringify(body),
        });
    }
}

// ---------------------------------------------------------------------------
// Seed helpers
// ---------------------------------------------------------------------------

export const todayIsoDate = (): string => new Date().toISOString().slice(0, 10);

export const unique = (tag: string): string => `${tag}-${Date.now()}`;

// -- Finance types ---------------------------------------------------------

export interface LedgerAccount {
    id: string;
    code: string;
    name: string;
    is_active: boolean;
    currency: string;
}

export interface JournalLine {
    id: string;
    account_id: string;
    debit: string | null;
    credit: string | null;
}

export interface JournalEntry {
    id: string;
    entry_date: string;
    memo: string | null;
    status: string;
    lines: JournalLine[];
}

export interface CustomerFinance {
    id: string;
    name: string;
    customer_code: string;
    currency: string;
}

export interface Invoice {
    id: string;
    invoice_number: string;
    invoice_date: string;
    due_date: string;
    status: string;
    total: string;
    currency: string;
    customer_id: string;
}

// -- CRM types -------------------------------------------------------------

export interface Opportunity {
    id: string;
    name: string;
    stage: string;
    leadId?: string | null;
    amount?: string | null;
    currency?: string | null;
    lostReason?: string | null;
}

// -- Factory functions -----------------------------------------------------

export async function createCustomer(
    api: BffApi,
    name: string,
): Promise<CustomerFinance> {
    return api.post<CustomerFinance>("/api/v1/crm/customers", {
        name,
        currency: "USD",
    });
}

export async function seedBalancedEntry(
    api: BffApi,
    memo: string,
): Promise<JournalEntry> {
    return api.post<JournalEntry>("/api/v1/finance/journal-entries", {
        entry_date: todayIsoDate(),
        memo,
        lines: [
            { account_code: "1200", debit: "1250.00" },
            { account_code: "4000", credit: "1250.00" },
        ],
    });
}

/** Single debit-only line — valid draft, will fail the post balance check. */
export async function seedUnbalancedDraft(
    api: BffApi,
    memo: string,
): Promise<JournalEntry> {
    return api.post<JournalEntry>("/api/v1/finance/journal-entries", {
        entry_date: todayIsoDate(),
        memo,
        lines: [{ account_code: "1200", debit: "100.00" }],
    });
}

export async function seedInvoice(
    api: BffApi,
    customerId: string,
    opts?: { date?: string; due?: string },
): Promise<Invoice> {
    return api.post<Invoice>("/api/v1/finance/invoices", {
        customer_id: customerId,
        invoice_date: opts?.date ?? todayIsoDate(),
        due_date: opts?.due ?? todayIsoDate(),
        currency: "USD",
        lines: [
            {
                description: "E2E test line",
                account_code: "4000",
                quantity: 1,
                unit_price: 1250,
            },
        ],
    });
}

export async function seedLead(
    api: BffApi,
    name: string,
): Promise<{ id: string }> {
    return api.post<{ id: string }>("/api/v1/crm/leads", {
        first_name: name,
        company: name,
    });
}

export async function qualifyLead(
    api: BffApi,
    leadId: string,
): Promise<Opportunity> {
    return api.post<Opportunity>(`/api/v1/crm/leads/${leadId}/qualify`, {
        amount: 25000,
        currency: "USD",
        probability: 0,
        expected_close_date: todayIsoDate(),
    });
}

export async function changeOpportunityStage(
    api: BffApi,
    opportunityId: string,
    stage: string,
): Promise<Opportunity> {
    // The /stage endpoint returns { opportunity, customer } — unwrap the
    // opportunity so callers read `.stage` directly.
    const result = await api.post<{ opportunity: Opportunity }>(
        `/api/v1/crm/opportunities/${opportunityId}/stage`,
        { stage },
    );
    return result.opportunity;
}

export async function getOpportunity(
    api: BffApi,
    opportunityId: string,
): Promise<Opportunity> {
    const raw = await api.get<Record<string, unknown>>(
        `/api/v1/crm/opportunities/${opportunityId}`,
    );
    return {
        id: String(raw.id ?? ""),
        name: String(raw.name ?? ""),
        stage: String(raw.stage ?? ""),
        lostReason: (raw.lost_reason as string | null | undefined) ?? null,
    };
}
