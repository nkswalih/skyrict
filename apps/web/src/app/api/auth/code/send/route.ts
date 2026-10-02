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

    // Forwarded verbatim. The backend verifies it; the BFF deliberately does
    // not inspect or substitute a token, because a token minted here would
    // prove the BFF solved a challenge rather than the user.
    const turnstileToken =
        typeof body.turnstileToken === "string" && body.turnstileToken.trim()
            ? body.turnstileToken
            : null;

    const result = await callBackend("/auth/signup/send-code", {
        body: { email, turnstile_token: turnstileToken },
    });
    if (!result.ok) return backendError(result);

    const data = result.data;
    return NextResponse.json({
        status: "ok",
        resendIn: Number(data?.resend_in ?? data?.resendIn ?? 60),
        code: data?.code ?? null,
    });
}
