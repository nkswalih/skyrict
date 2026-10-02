import type { NextRequest } from "next/server";
import { NextResponse } from "next/server";

import { assertSameOrigin, backendError, callBackend } from "@/lib/server/auth";

export const dynamic = "force-dynamic";

export async function POST(request: NextRequest) {
    if (!assertSameOrigin(request)) {
        return NextResponse.json(
            { error: "Invalid request origin." },
            { status: 403 },
        );
    }

    const body = (await request.json().catch(() => ({}))) as Record<
        string,
        unknown
    >;
    const email =
        typeof body.email === "string" ? body.email.trim().toLowerCase() : "";
    if (!email) {
        return NextResponse.json(
            { error: "Email is required." },
            { status: 400 },
        );
    }

    const result = await callBackend("/auth/signup/start", {
        body: {
            email,
            turnstile_token: body.turnstileToken ?? null,
        },
    });
    if (!result.ok) return backendError(result);

    // The proof the rest of the wizard spends in place of a second challenge.
    const data = result.data;
    return NextResponse.json({
        status: "ok",
        flowToken: data?.flow_token ?? data?.flowToken ?? null,
    });
}
