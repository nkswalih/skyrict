/*
 * Worker-scoped API fixtures for the SKY-108 security suite.
 *
 * One authenticated admin session per worker (one login, one token family):
 * the specs share it read-only, which keeps the admin login count inside the
 * tightened RATE_LIMIT_LOGIN budget. Token-reuse tests sign in through their
 * own context instead so they own the full refresh chain.
 */

import { test as base } from "@playwright/test";

import { BffApi } from "./api";
import { readEnrolledSecret } from "./auth-flow";
import {
    ADMIN_EMAIL,
    ADMIN_PASSWORD,
    BASE_URL,
    FINANCE_EMAIL,
    FINANCE_PASSWORD,
    FOREIGN_URL,
    apiSignIn,
} from "./security";

interface SecurityFixtures {
    admin: { api: BffApi; token: string };
    finance: BffApi;
    foreign: BffApi;
}

export const securityTest = base.extend<{}, SecurityFixtures>({
    admin: [
        async ({ playwright }, use) => {
            const ctx = await playwright.request.newContext({
                baseURL: BASE_URL,
            });
            try {
                const session = await apiSignIn(
                    ctx,
                    ADMIN_EMAIL,
                    ADMIN_PASSWORD,
                    readEnrolledSecret(),
                );
                if (!session.accessToken) {
                    throw new Error("admin sign-in returned no access token");
                }
                const api = new BffApi(ctx, {
                    bearerToken: session.accessToken,
                });
                await use({ api, token: session.accessToken });
            } finally {
                await ctx.dispose();
            }
        },
        { scope: "worker" },
    ],
    finance: [
        async ({ playwright }, use) => {
            const ctx = await playwright.request.newContext({
                baseURL: BASE_URL,
            });
            try {
                // On a fresh stack the seeded finance_viewer is not MFA-enrolled,
                // so apiSignIn takes the mfa.setup path and needs no secret.
                const session = await apiSignIn(
                    ctx,
                    FINANCE_EMAIL,
                    FINANCE_PASSWORD,
                );
                if (!session.accessToken) {
                    throw new Error(
                        "finance sign-in returned no access token",
                    );
                }
                await use(new BffApi(ctx, { bearerToken: session.accessToken }));
            } finally {
                await ctx.dispose();
            }
        },
        { scope: "worker" },
    ],
    foreign: [
        // The same admin token, but presented against a foreign (unseeded)
        // tenant subdomain. Core rejects unknown slugs in middleware, so any
        // response other than a failure here is a slice of a leak.
        async ({ playwright, admin }, use) => {
            const ctx = await playwright.request.newContext({
                baseURL: FOREIGN_URL,
            });
            try {
                await use(
                    new BffApi(ctx, {
                        origin: FOREIGN_URL,
                        bearerToken: admin.token,
                    }),
                );
            } finally {
                await ctx.dispose();
            }
        },
        { scope: "worker" },
    ],
});