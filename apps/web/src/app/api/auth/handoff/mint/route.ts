import type { NextRequest } from "next/server";
import { NextResponse } from "next/server";

import { deriveApex } from "@/lib/auth/apex";

import {
    SESSION_COOKIE,
    applySessionCookie,
    assertSameOrigin,
    backendError,
    callBackend,
    hostSurface,
    resolveTenantSlug,
} from "@/lib/server/auth";

export const dynamic = "force-dynamic";

function workspaceUrl(request: NextRequest, slug: string): string {
    // Build the workspace origin from the client-facing Host header, not
    // request.nextUrl: nextUrl reports the server's own socket port (3100),
    // which the browser cannot reach through the CSP form-action allowlist.
    const host = request.headers.get("host") ?? "";
    const port = host.includes(":") ? host.slice(host.indexOf(":")) : "";
    const hostname = host.replace(/:\d+$/, "").toLowerCase();
    // The mint runs on the signin surface, so the {slug}.signin. label must be
    // stripped before deriving the apex: default.signin.localhost -> localhost.
    // Without this the handoff form would post back to the signin host, where
    // the redeem route rejects the surface with "Invalid request origin.".
    const apex = hostname.includes(".signin.")
        ? hostname.split(".signin.").pop() ?? ""
        : deriveApex(hostname);
    const tenant = slug || resolveTenantSlug(host) || "app";
    return `${request.nextUrl.protocol}//${tenant}.${apex}${port}`;
}

/**
 * Mint a single-use, tenant-bound handoff token (POST body only, never in the
 * URL). Only auth origins (signup/signin) may mint; the workspace host never
 * does. The refresh token rides inside the payload so the workspace origin can
 * establish its host-scoped session cookie on redemption.
 */
export async function POST(request: NextRequest) {
    const { surface, slug } = hostSurface(request.headers.get("host"));
    if (surface !== "signup" && surface !== "signin") {
        return NextResponse.json(
            { error: "Invalid request origin." },
            { status: 403 },
        );
    }
    if (!assertSameOrigin(request)) {
        return NextResponse.json(
            { error: "Invalid request origin." },
            { status: 403 },
        );
    }

    const refreshToken = request.cookies.get(SESSION_COOKIE)?.value;
    if (!refreshToken) {
        return NextResponse.json(
            { error: "Session expired." },
            { status: 401 },
        );
    }

    const body = (await request.json().catch(() => ({}))) as {
        redirect?: unknown;
    };
    const redirect =
        typeof body.redirect === "string" && body.redirect.startsWith("/")
            ? body.redirect
            : "/";

    // Rotate the refresh token before embedding it in the handoff payload. The
    // signin-origin cookie and the payload must never hold the same token: once
    // the workspace redemption refreshes with the payload token, the cookie's
    // copy becomes stale, and the next signin-origin refresh would be flagged as
    // reuse - revoking the whole token family, including the brand-new workspace
    // session. Rotating here consumes the cookie's copy and clears the cookie so
    // the payload token is the only live token, used exactly once at redemption.
    const rotated = await callBackend("/auth/refresh", {
        body: { refresh_token: refreshToken },
        tenantSlug: slug,
    });
    if (!rotated.ok || !rotated.data?.refresh_token) {
        const response = NextResponse.json(
            { error: "Session expired." },
            { status: 401 },
        );
        applySessionCookie(response, null);
        return response;
    }
    const handoffToken = String(rotated.data.refresh_token);

    const result = await callBackend("/handoffs", {
        body: {
            purpose: "session",
            payload: {
                refresh_token: handoffToken,
                tenant_slug: slug,
                redirect,
            },
        },
        tenantSlug: slug,
    });
    if (!result.ok) return backendError(result);

    const data = result.data;
    if (!data?.token) {
        return NextResponse.json(
            { error: "Could not mint handoff token." },
            { status: 502 },
        );
    }

    const response = NextResponse.json({
        token: String(data.token),
        workspaceUrl: workspaceUrl(request, slug),
        redirect,
    });
    applySessionCookie(response, null);
    return response;
}
