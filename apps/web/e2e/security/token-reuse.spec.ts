/*
 * SKY-108 refresh-token reuse: presenting a rotated token is treated as theft
 * and kills the whole session family.
 *
 * The tight stack boots with IDENTITY_REFRESH_REUSE_GRACE_SECONDS=0, so the
 * identity grace window that tolerates legitimate double-presentation is gone:
 *   R0 (login) --refresh--> R1, then replaying R0 must 401 AND revoke the
 *   family, which also kills R1 for subsequent refreshes.
 *
 * This spec owns its own login context on purpose - the shared worker fixture
 * must not advance its rotation chain.
 *
 * The attacker replays R0 against IDENTITY directly, not through the BFF: the
 * BFF single-flights refresh rotations in-process (rotateRefreshToken's memo
 * keyed by tenant+token), so a same-process replay would return the cached R1
 * pair and never arm identity's reuse detector. Identity is published on
 * :8000 by the E2E compose stack; hitting it directly is the true replay
 * boundary.
 */

import { expect } from "@playwright/test";

import { readEnrolledSecret } from "../helpers/auth-flow";
import { BffApi } from "../helpers/api";
import {
    ADMIN_EMAIL,
    ADMIN_PASSWORD,
    BASE_URL,
    apiSignIn,
    readSessionCookie,
} from "../helpers/security";
import { securityTest as test } from "../helpers/security-fixtures";

test("presenting a rotated refresh token revokes the session family", async ({
    playwright,
}) => {
    const home = await playwright.request.newContext({ baseURL: BASE_URL });
    try {
        const session = await apiSignIn(
            home,
            ADMIN_EMAIL,
            ADMIN_PASSWORD,
            readEnrolledSecret(),
        );
        expect(session.refreshCookie, "login must set a refresh cookie").not.toBeNull();
        const r0 = session.refreshCookie as string;

        const api = new BffApi(home, {
            bearerToken: session.accessToken ?? undefined,
        });
        const rotated = await api.raw("/api/auth/refresh", { method: "POST" });
        expect(rotated.status).toBe(200);
        const r1 = await readSessionCookie(home);
        expect(r1).not.toBeNull();
        expect(r1).not.toBe(r0);

        // The attacker replays the OLD token straight at identity (bypassing
        // the BFF memo) on a separate client.
        const identityUrl =
            process.env.E2E_IDENTITY_URL ?? "http://localhost:8000";
        const attacker = await playwright.request.newContext({
            baseURL: identityUrl,
        });
        try {
            const reuse = await attacker.post("/api/v1/auth/refresh", {
                headers: { "X-Tenant-Slug": "default" },
                data: { refresh_token: r0 },
            });
            expect(reuse.status()).toBe(401);

            // Family kill: the rotated token is dead too.
            const afterKill = await new BffApi(home).raw("/api/auth/refresh", {
                method: "POST",
            });
            expect(afterKill.status).toBe(401);
        } finally {
            await attacker.dispose();
        }
    } finally {
        await home.dispose();
    }
});