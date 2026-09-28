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
 * BFF relay for conversation attachment blobs (SKY-60 attachment durability).
 *
 * The frontend fetches the blob via `apiFetchRaw` and previews it through an
 * object URL, exactly like document detail previews. This route shadows the
 * `/api/v1/[...path]` catch-all so the binary body passes through untouched
 * instead of being round-tripped as JSON.
 *
 * The access token comes from the shared `resolveBffAuth`. This handler used to
 * read only the Authorization header and forward `token: null` when it was
 * absent, so a cookie-only caller got a relayed 401; the documented contract is
 * that the httpOnly session cookie authenticates every same-origin BFF route.
 * See pre-release audit finding 26.
 */
export async function GET(
    request: NextRequest,
    {
        params,
    }: { params: Promise<{ id: string; attachmentId: string }> },
) {
    if (!assertSameOrigin(request)) {
        return NextResponse.json(
            { error: "Invalid request origin." },
            { status: 403 },
        );
    }

    const { id, attachmentId } = await params;
    const slug = resolveTenantSlug(request.headers.get("host"));
    const auth = await resolveBffAuth(request);
    if (!auth.ok) return auth.response;
    const { token, rotatedRefreshToken } = auth;

    const upstream = await callBackendStream(
        `/ai/agents/conversations/${encodeURIComponent(id)}/attachments/${encodeURIComponent(attachmentId)}`,
        { method: "GET", tenantSlug: slug, token, target: "core" },
    );

    if (!upstream || !upstream.body) {
        return NextResponse.json(
            { detail: "Core service is unavailable. Please try again." },
            { status: 502 },
        );
    }

    const headers = new Headers();
    for (const name of ["Content-Type", "Content-Disposition"]) {
        const value = upstream.headers.get(name);
        if (value) headers.set(name, value);
    }
    if (!headers.has("Content-Type")) {
        headers.set("Content-Type", "application/octet-stream");
    }
    const response = new NextResponse(upstream.body, {
        status: upstream.status,
        headers,
    });
    if (rotatedRefreshToken) applySessionCookie(response, rotatedRefreshToken);
    return response;
}
