import type { NextRequest } from "next/server";
import { NextResponse } from "next/server";

import {
    SESSION_COOKIE,
    applySessionCookie,
    callBackend,
    mapUser,
    resolveTenantSlug,
    rotateRefreshToken,
} from "@/lib/server/auth";

export const dynamic = "force-dynamic";

/**
 * Restore a session: refresh the access token from the httpOnly cookie, then
 * fetch the profile. The browser keeps the access token in memory; this route
 * re-hydrates it on page load and lets server components guard routes.
 */
export async function GET(request: NextRequest) {
    const refreshToken = request.cookies.get(SESSION_COOKIE)?.value;
    if (!refreshToken) {
        return NextResponse.json({ authenticated: false });
    }

    const slug = resolveTenantSlug(request.headers.get("host"));
    const rotated = await rotateRefreshToken(refreshToken, slug);
    if (!rotated.access) {
        const response = NextResponse.json({ authenticated: false });
        if (rotated.result.status === 401 || rotated.result.status === 0)
            applySessionCookie(response, null);
        return response;
    }

    const { token, refreshToken: rotatedToken, expiresIn } = rotated.access;

    // The rotation above is already spent by the time the profile probe runs,
    // so a blip here is expensive: the response carries no access token, the
    // client has nothing to cache, and its next request hydrates AGAIN - a
    // second rotation, with a second chance to collide. On a cold stack (CI
    // boots the cluster and starts driving it within ~2 minutes) the first
    // /users/me after a rotation is exactly the call that has to pay for pool
    // growth and lazy imports. One short retry turns that blip into a normal
    // response instead of the seed of a rotation storm.
    let profile = await callBackend("/users/me", {
        method: "GET",
        token,
        tenantSlug: slug,
    });
    if (!profile.ok && profile.status !== 401 && profile.status !== 404) {
        await new Promise((resolve) => setTimeout(resolve, 250));
        profile = await callBackend("/users/me", {
            method: "GET",
            token,
            tenantSlug: slug,
        });
    }
    if (!profile.ok) {
        console.warn("[auth] session profile probe failed", {
            slug,
            status: profile.status,
        });
    }

    const response = NextResponse.json({
        authenticated: profile.ok,
        accessToken: profile.ok ? token : null,
        expiresIn,
        user: profile.ok ? mapUser(profile.data) : null,
    });
    // Identity rotates the refresh token unconditionally on /auth/refresh, so
    // always write the rotated cookie back - even when the /users/me probe
    // transiently fails. Otherwise the browser keeps presenting an already-
    // spent value, and a second failed probe leaves it TWO generations behind
    // the session record, which identity's reuse check treats as a family
    // revoke - taking down every subsequent authenticated call with the
    // generic "Missing Authorization header" 401.
    if (rotatedToken) applySessionCookie(response, rotatedToken);
    return response;
}
