import type { NextRequest } from "next/server";
import { NextResponse } from "next/server";

import { resolveBffAuth } from "@/lib/server/bff-auth";
import {
    applySessionCookie,
    assertSameOrigin,
    callBackendStream,
    resolveTenantSlug,
} from "@/lib/server/auth";

export const dynamic = "force-dynamic";

/**
 * BFF relay for the supervisor SSE chat stream (SKY-60).
 *
 * This static route shadows the ``/api/v1/[...path]`` catch-all for the
 * streaming endpoint: instead of buffering the JSON body it relays the core
 * monolith's ``text/event-stream`` response chunk-by-chunk, so the Agents
 * shell renders tokens live.
 *
 * The same BFF guardrails apply as the catch-all: the tenant slug is derived
 * server-side from the Host header, the POST must pass the Origin/Referer CSRF
 * gate, and the access token is resolved by the shared ``resolveBffAuth`` -
 * a client-supplied Bearer token when present, otherwise one minted from the
 * httpOnly session cookie. That last part is the fix for pre-release audit
 * finding 26: this handler used to read the Authorization header and nothing
 * else, so a cookie-only caller was forwarded with no token and got a relayed
 * 401 even though the BFF's documented contract is that the cookie bridge
 * authenticates every same-origin route.
 */
export async function POST(request: NextRequest) {
    if (!assertSameOrigin(request)) {
        return NextResponse.json(
            { error: "Invalid request origin." },
            { status: 403 },
        );
    }

    const slug = resolveTenantSlug(request.headers.get("host"));
    const auth = await resolveBffAuth(request);
    if (!auth.ok) return auth.response;
    const { token, rotatedRefreshToken } = auth;
    const body = await request.json().catch(() => undefined);

    const upstream = await callBackendStream("/ai/agents/chat/stream", {
        method: "POST",
        body,
        tenantSlug: slug,
        token,
        target: "core",
    });

    if (!upstream || !upstream.body) {
        return NextResponse.json(
            { detail: "Core service is unavailable. Please try again." },
            { status: 502 },
        );
    }

    // Only the SSE content type and the no-buffering hints survive; the
    // upstream body is handed to the browser as a live stream.
    //
    // NextResponse rather than a bare Response so the rotated refresh cookie
    // can be attached below without a cast - it is a Response subclass, and
    // this is the same shape the reports CSV-export relay already returns.
    const response = new NextResponse(upstream.body, {
        status: upstream.status,
        headers: {
            "Content-Type":
                upstream.headers.get("content-type") ?? "text/event-stream",
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    });
    // Minting the token from the cookie rotated the refresh value identity
    // holds, so write the new one back or the next cookie-only call re-presents
    // a value identity is about to reject.
    if (rotatedRefreshToken) applySessionCookie(response, rotatedRefreshToken);
    return response;
}
