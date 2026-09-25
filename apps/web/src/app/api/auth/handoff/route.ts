import type { NextRequest } from "next/server";
import { NextResponse } from "next/server";

import {
    applySessionCookie,
    baseParts,
    callBackend,
    hostSurface,
} from "@/lib/server/auth";

export const dynamic = "force-dynamic";

const ALLOWED_ORIGIN =
    /^https?:\/\/(?:signup\.|(?:[a-z0-9-]+)\.signin\.)(?:localhost|skyrict\.com)(?::\d+)?$/;

function allowedOrigin(origin: string | null): boolean {
    // `null` (the header value sent for opaque origins) and a missing header are
    // both fine for this route: the single-use token is the actual credential,
    // it is minted only on auth origins behind the same-origin CSRF gate, and the
    // SameSite=Lax session cookie is never relied on here.
    if (!origin || origin === "null") return true;
    return ALLOWED_ORIGIN.test(origin.toLowerCase());
}

function allowedRedirect(path: string): boolean {
    if (
        path.includes("//") ||
        path.includes("..") ||
        path.includes(":") ||
        path.includes("\\")
    ) {
        return false;
    }
    return path === "/" || /^\/[a-zA-Z0-9][a-zA-Z0-9/_-]*$/.test(path);
}

function applyCors(response: NextResponse, origin: string | null): void {
    if (!origin) return;
    response.headers.set("Access-Control-Allow-Origin", origin);
    response.headers.set("Vary", "Origin");
    response.headers.set("Access-Control-Allow-Methods", "POST, OPTIONS");
    response.headers.set("Access-Control-Allow-Headers", "Content-Type");
    // Required when the client fetches with `credentials: "include"`, otherwise
    // the browser CORS-check fails and the session cookie is never stored.
    response.headers.set("Access-Control-Allow-Credentials", "true");
}

/** Cross-origin preflight: the workspace origin accepts auth-origin POSTs. */
export async function OPTIONS(request: NextRequest) {
    const origin = request.headers.get("origin");
    if (!allowedOrigin(origin)) {
        return NextResponse.json(
            { error: "Invalid request origin." },
            { status: 403 },
        );
    }
    const response = new NextResponse(null, { status: 204 });
    applyCors(response, origin);
    return response;
}

/** Absolute `{slug}.signin.{apex}/signin?error=...` for this tenant. */
function signinUrl(request: NextRequest, slug: string, error?: string): string {
    const proto = request.nextUrl.protocol;
    const { port, apex } = baseParts(request.headers.get("host") ?? "");
    const base = `${proto}//${slug}.signin.${apex}${port}/signin`;
    return error ? `${base}?error=${encodeURIComponent(error)}` : base;
}

/**
 * Redeem a handoff token on the workspace origin. Invoked by a top-level form
 * POST from the signin page. The response is a 303 See Other to the workspace
 * root with the host-scoped session cookie attached: the browser follows with a
 * fresh GET (PRG), a first-party context in which the Set-Cookie is honored and
 * the dashboard renders. A 307 would replay the POST to the root and Chrome
 * does not apply the new cookie on that cross-site POST re-submission.
 * Consumes the single-use token, host-locks it to the Host tenant, and
 * exchanges the embedded refresh token for a fresh pair.
 */
export async function POST(request: NextRequest) {
    const { surface, slug } = hostSurface(request.headers.get("host"));
    if (surface !== "workspace" || !slug) {
        return NextResponse.json(
            { error: "Invalid request origin." },
            { status: 403 },
        );
    }

    if (!allowedOrigin(request.headers.get("origin"))) {
        return NextResponse.json(
            { error: "Invalid request origin." },
            { status: 403 },
        );
    }

    const form = await request.formData().catch(() => null);
    const token = form ? String(form.get("token") ?? "") : "";
    if (!token) {
        return NextResponse.redirect(
            signinUrl(request, slug, "Sign-in session expired. Try again."),
            303,
        );
    }

    const redeem = await callBackend("/handoffs/redeem", {
        body: { token, purpose: "session" },
        tenantSlug: slug,
    });
    if (!redeem.ok) {
        return NextResponse.redirect(
            signinUrl(request, slug, "Could not complete sign-in. Try again."),
            303,
        );
    }

    const payload = (redeem.data?.payload ?? {}) as Record<string, unknown>;
    if (payload.tenant_slug !== slug) {
        return NextResponse.redirect(
            signinUrl(request, slug, "Invalid request origin."),
            303,
        );
    }

    const refreshToken = payload.refresh_token;
    const redirect = payload.redirect;
    if (
        typeof refreshToken !== "string" ||
        typeof redirect !== "string" ||
        !allowedRedirect(redirect)
    ) {
        return NextResponse.redirect(
            signinUrl(request, slug, "Invalid sign-in handoff."),
            303,
        );
    }

    const refreshed = await callBackend("/auth/refresh", {
        body: { refresh_token: refreshToken },
        tenantSlug: slug,
    });
    if (!refreshed.ok) {
        return NextResponse.redirect(
            signinUrl(request, slug, "Could not complete sign-in. Try again."),
            303,
        );
    }

    const data = refreshed.data;
    if (!data?.access_token) {
        return NextResponse.redirect(
            signinUrl(request, slug, "Could not complete sign-in. Try again."),
            303,
        );
    }

    const workspace = `${request.nextUrl.protocol}//${request.headers.get("host")}`;
    const response = NextResponse.redirect(new URL(redirect, workspace), 303);
    if (data.refresh_token)
        applySessionCookie(response, String(data.refresh_token));
    return response;
}
