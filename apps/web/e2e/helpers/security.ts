/*
 * API-level auth + security helpers for the SKY-108 E2E security suite.
 *
 * Sign-in happens straight through the BFF (like helpers/api.ts) so the
 * rate-limit and token-reuse specs can burn sessions deterministically without
 * touching the browser-based crm-finance journeys. Every helper is stack
 * agnostic: it handles both the enrolled (mfa.verify) and the fresh
 * (mfa.setup) login paths, so the suite runs against the normal compose stack
 * AND the tightened one (docker-compose.e2e.security.yml).
 */

import type { APIRequestContext } from "@playwright/test";

import { BffApi, BffError } from "./api";
import { totp } from "./totp";

export const BASE_URL =
    process.env.E2E_BASE_URL ?? "http://default.localhost:3000";
// A tenant slug that is never seeded. Core derives the tenant from the Host
// header and rejects unknown slugs with 404, so this is the cross-tenant leak
// probe surface.
export const FOREIGN_URL = "http://second.localhost:3000";

export const ADMIN_EMAIL =
    process.env.E2E_ADMIN_EMAIL ?? "admin@skyrict.io";
export const ADMIN_PASSWORD =
    process.env.E2E_ADMIN_PASSWORD ?? "Admin123!";
export const FINANCE_EMAIL = "finance@skyrict.io";
export const FINANCE_PASSWORD = "Finance123!";

export const SESSION_COOKIE = "skyrict_session";

export interface ApiSession {
    accessToken: string | null;
    refreshCookie: string | null;
}

export async function readSessionCookie(
    ctx: APIRequestContext,
): Promise<string | null> {
    const state = await ctx.storageState();
    return state.cookies.find((c) => c.name === SESSION_COOKIE)?.value ?? null;
}

/**
 * Sign in through the BFF with the password + MFA challenge path. When the
 * account already has MFA enrolled, `totpSecret` is required to complete the
 * challenge; otherwise the first-sign-in (mfa.setup) path returns an access
 * token without one.
 */
export async function apiSignIn(
    ctx: APIRequestContext,
    email: string,
    password: string,
    totpSecret?: string,
): Promise<ApiSession> {
    const api = new BffApi(ctx);
    const login = await api.raw<Record<string, unknown>>("/api/auth/login", {
        method: "POST",
        body: JSON.stringify({ email, password }),
    });
    if (!login.ok) {
        throw new BffError(login.status, `login failed (${login.status})`);
    }

    let accessToken: string | null = null;
    switch (login.payload.status) {
        case "mfa_setup":
        case "authenticated":
            accessToken = (login.payload.accessToken as string | null) ?? null;
            break;
        case "mfa_challenge": {
            if (!totpSecret) {
                throw new BffError(
                    401,
                    `mfa challenge but no TOTP secret for ${email}`,
                );
            }
            const challenge = login.payload.mfaToken as string | undefined;
            const verify = await api.raw<Record<string, unknown>>(
                "/api/auth/mfa/verify",
                {
                    method: "POST",
                    body: JSON.stringify({
                        mfa_token: challenge,
                        code: totp(totpSecret),
                    }),
                },
            );
            if (!verify.ok) {
                throw new BffError(
                    verify.status,
                    `mfa verify failed (${verify.status})`,
                );
            }
            accessToken = (verify.payload.accessToken as string | null) ?? null;
            break;
        }
        default:
            throw new BffError(
                login.status,
                `unexpected login status: ${String(login.payload.status)}`,
            );
    }

    return {
        accessToken,
        refreshCookie: await readSessionCookie(ctx),
    };
}