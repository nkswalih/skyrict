import type { NextRequest } from "next/server";
import { NextResponse } from "next/server";

import { SERVICE_UNAVAILABLE_MESSAGE } from "@/lib/api/error-messages";
import {
    apiBase,
    assertSameOrigin,
    backendError,
    callBackend,
    mapUser,
    resolveTenantSlug,
} from "@/lib/server/auth";
import { captureBffException } from "@/lib/server/sentry";

export const dynamic = "force-dynamic";

/**
 * Upload or remove the signed-in user's avatar.
 *
 * The browser sends multipart/form-data (or a bare DELETE) to this same-origin
 * handler; the tenant slug is resolved server-side from the Host header and the
 * Bearer access token is forwarded, exactly like the other /api/auth/* routes.
 * The response carries the refreshed user so the client can update its session
 * in place.
 */
export async function PUT(request: NextRequest) {
    if (!assertSameOrigin(request)) {
        return NextResponse.json(
            { error: "Invalid request origin." },
            { status: 403 },
        );
    }

    const slug = resolveTenantSlug(request.headers.get("host"));
    const authorization = request.headers.get("authorization");
    const token = authorization?.toLowerCase().startsWith("bearer ")
        ? authorization.slice("Bearer ".length)
        : null;

    const form = await request.formData().catch(() => null);
    if (!form) {
        return NextResponse.json(
            { error: "Could not read the upload." },
            { status: 400 },
        );
    }

    let response: Response;
    try {
        response = await fetch(`${apiBase()}/api/v1/avatars/me`, {
            method: "PUT",
            headers: {
                "X-Tenant-Slug": slug,
                ...(token ? { Authorization: `Bearer ${token}` } : {}),
            },
            body: form,
            cache: "no-store",
        });
    } catch (error) {
        captureBffException(error, "/avatars/me", "identity");
        return NextResponse.json(
            { error: SERVICE_UNAVAILABLE_MESSAGE },
            { status: 502 },
        );
    }

    const payload = (await response.json().catch(() => ({}))) as {
        data?: Record<string, unknown> | null;
        detail?: string;
    };
    if (!response.ok) {
        const detail =
            typeof payload.detail === "string" ? payload.detail : null;
        return NextResponse.json(
            { error: detail ?? "Could not update your avatar." },
            { status: response.status },
        );
    }
    return NextResponse.json(
        { user: mapUser(payload.data) },
        { status: response.status },
    );
}

export async function DELETE(request: NextRequest) {
    if (!assertSameOrigin(request)) {
        return NextResponse.json(
            { error: "Invalid request origin." },
            { status: 403 },
        );
    }

    const slug = resolveTenantSlug(request.headers.get("host"));
    const authorization = request.headers.get("authorization");
    const token = authorization?.toLowerCase().startsWith("bearer ")
        ? authorization.slice("Bearer ".length)
        : null;

    const result = await callBackend("/avatars/me", {
        method: "DELETE",
        tenantSlug: slug,
        token,
    });

    if (!result.ok || !result.data) {
        return backendError(result);
    }
    return NextResponse.json({ user: mapUser(result.data) });
}
