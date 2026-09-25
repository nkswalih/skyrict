import type { NextRequest } from "next/server";
import { NextResponse } from "next/server";

import { SERVICE_UNAVAILABLE_MESSAGE } from "@/lib/api/error-messages";
import { apiBase, assertSameOrigin, mapUser } from "@/lib/server/auth";
import { captureBffException } from "@/lib/server/sentry";

export const dynamic = "force-dynamic";

/**
 * Accept an invitation (self-service, no tenant resolution).
 *
 * The browser sends multipart/form-data with the invite token, email, password,
 * full name, and an optional avatar file; the handler forwards the same parts
 * to the identity service's /invitations/accept endpoint. On success the
 * client redirects to signin - the accept response carries no tokens.
 */
export async function POST(request: NextRequest) {
    if (!assertSameOrigin(request)) {
        return NextResponse.json(
            { error: "Invalid request origin." },
            { status: 403 },
        );
    }

    const form = await request.formData().catch(() => null);
    if (!form) {
        return NextResponse.json(
            { error: "Could not read the invitation details." },
            { status: 400 },
        );
    }

    let response: Response;
    try {
        response = await fetch(`${apiBase()}/api/v1/invitations/accept`, {
            method: "POST",
            body: form,
            cache: "no-store",
        });
    } catch (error) {
        captureBffException(error, "/invitations/accept", "identity");
        return NextResponse.json(
            { error: SERVICE_UNAVAILABLE_MESSAGE },
            { status: 502 },
        );
    }

    const payload = (await response.json().catch(() => ({}))) as {
        data?: Record<string, unknown> | null;
        detail?: string;
        type?: string;
    };
    if (!response.ok) {
        const detail =
            typeof payload.detail === "string"
                ? payload.detail
                : "Could not accept the invitation. Please try again.";
        return NextResponse.json(
            { error: detail, type: payload.type ?? null },
            { status: response.status },
        );
    }
    return NextResponse.json(
        { user: mapUser(payload.data) },
        { status: response.status },
    );
}
