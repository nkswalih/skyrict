import type { NextRequest } from "next/server";
import { NextResponse } from "next/server";

import { resolveBffAuth } from "@/lib/server/bff-auth";
import {
    applySessionCookie,
    callBackendStream,
    resolveTenantSlug,
} from "@/lib/server/auth";

export const dynamic = "force-dynamic";

/**
 * BFF relay for AI document pack downloads (FIN-AI-004).
 *
 * This static route shadows the ``/api/v1/[...path]`` catch-all for the PDF
 * download: ``callBackend``'s JSON buffer would turn the PDF bytes into ``{}``
 * (the same corruption the reports CSV export route fixes), so the upstream
 * ``application/pdf`` body is passed to the browser as-is. Only the
 * download-relevant headers survive, mirroring the stream/attach relays.
 *
 * The access token comes from the shared ``resolveBffAuth``, so a cookie-only
 * caller authenticates here exactly as it does on every other BFF route. This
 * handler previously read only the Authorization header and forwarded
 * ``token: null``; see pre-release audit finding 26.
 */
export async function GET(
    request: NextRequest,
    { params }: { params: Promise<{ docId: string }> },
) {
    const { docId } = await params;
    const slug = resolveTenantSlug(request.headers.get("host"));
    const auth = await resolveBffAuth(request);
    if (!auth.ok) return auth.response;
    const { token, rotatedRefreshToken } = auth;

    const upstream = await callBackendStream(
        `/finance/ai/docs/${encodeURIComponent(docId)}/download`,
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
    const response = new NextResponse(upstream.body, {
        status: upstream.status,
        headers,
    });
    if (rotatedRefreshToken) applySessionCookie(response, rotatedRefreshToken);
    return response;
}
