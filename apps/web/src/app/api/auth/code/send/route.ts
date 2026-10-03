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

    // Forwarded verbatim. The backend checks the proof against the address it
    // was issued for; the BFF deliberately does not inspect or substitute one,
    // because a proof minted here would prove the BFF cleared the challenge
    // rather than the user.
    const flowToken =
        typeof body.flowToken === "string" && body.flowToken.trim()
            ? body.flowToken
            : null;

    const result = await callBackend("/auth/signup/send-code", {
        body: { email, flow_token: flowToken },
    });
    if (!result.ok) return backendError(result);

    const data = result.data;
    return NextResponse.json({
        status: "ok",
        resendIn: Number(data?.resend_in ?? data?.resendIn ?? 60),
        code: data?.code ?? null,
    });
}
