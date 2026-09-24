/**
 * Host-based routing for the four subdomain surfaces.
 *
 * One Next app serves every surface; the Host header picks which one. The
 * middleware resolves the surface + tenant slug (mirroring the backend
 * TenantResolver), rejects unknown hosts, and rewrites public paths to their
 * internal routes:
 *
 *   marketing  web.localhost            `/`            → landing (signup-only)
 *   signup     signup.localhost         `/signup`      → `/signup`
 *   signin     {slug}.signin.localhost  `/signin`      → `/login`
 *   workspace  {slug}.localhost         `/`, `/agents` → `/dashboard/…`
 *
 * Public URLs never contain `/dashboard` or `signin`; the internal
 * `/dashboard/*` tree is the workspace app, served at the tenant root.
 */

import type { NextRequest } from "next/server";
import { NextResponse } from "next/server";

import {
    SESSION_COOKIE,
    hostSurface,
    signinOrigin,
    signupOrigin,
} from "@/lib/server/auth";

const AUTH_PATHS = [
    "/login",
    "/register",
    "/setup-mfa",
    "/signin",
    "/signup",
    "/invite",
    "/forgot-password",
    "/reset-password",
];

const LEGAL_PATHS = ["/terms", "/privacy"];

const INTERNAL_WORKSPACE_REWRITE_HEADER = "x-internal-workspace-rewrite";

function isLegalPath(pathname: string): boolean {
    return LEGAL_PATHS.includes(pathname);
}

function isAuthPath(pathname: string): boolean {
    return (
        AUTH_PATHS.includes(pathname) ||
        pathname.startsWith("/signup/") ||
        pathname.startsWith("/register/") ||
        pathname.startsWith("/mfa/")
    );
}

function notFound(): NextResponse {
    return NextResponse.rewrite(
        new URL("/_not-found", "http://internal.localhost"),
    );
}

export function middleware(request: NextRequest) {
    const host = request.headers.get("host") ?? "";
    const { surface, slug } = hostSurface(host);
    const { pathname } = request.nextUrl;

    const isApi = pathname.startsWith("/api");
    const isStatic =
        pathname.startsWith("/_next") || pathname === "/favicon.ico";

    if (isStatic) return NextResponse.next();

    if (surface === "unknown") {
        if (isApi)
            return NextResponse.json({ error: "Not found." }, { status: 404 });
        return notFound();
    }

    if (isApi) return NextResponse.next();

    switch (surface) {
        case "marketing": {
            // Signup-only marketing site: auth paths leave via the signup origin.
            if (isAuthPath(pathname) || pathname.startsWith("/dashboard")) {
                return NextResponse.redirect(
                    new URL(
                        signupOrigin(host, request.nextUrl.protocol),
                        request.url,
                    ),
                );
            }
            return NextResponse.next();
        }
        case "signup": {
            // Legacy /register URL: move callers to the /signup route so old
            // bookmarks and in-flight emails keep working.
            if (pathname === "/register" || pathname.startsWith("/register/")) {
                return NextResponse.redirect(
                    new URL(
                        pathname.replace(/^\/register/, "/signup"),
                        request.url,
                    ),
                    { status: 308 },
                );
            }
            if (isAuthPath(pathname) || isLegalPath(pathname)) {
                return NextResponse.next();
            }
            return NextResponse.redirect(new URL("/signup", request.url));
        }
        case "signin": {
            if (pathname === "/signin") {
                return NextResponse.rewrite(new URL("/login", request.url));
            }
            if (
                pathname === "/setup-mfa" ||
                pathname === "/mfa/verify" ||
                pathname === "/invite" ||
                isLegalPath(pathname)
            ) {
                return NextResponse.next();
            }
            return NextResponse.redirect(new URL("/signin", request.url));
        }
        case "workspace": {
            const isInternalWorkspaceRewrite =
                request.headers.get(INTERNAL_WORKSPACE_REWRITE_HEADER) === "1";

            if (isAuthPath(pathname)) {
                return NextResponse.redirect(
                    new URL(
                        signinOrigin(host, request.nextUrl.protocol, slug),
                        request.url,
                    ),
                );
            }

            // Every page on the workspace surface lives inside the authenticated
            // dashboard app, so a request without the session cookie has nothing
            // to render. Coarse presence check only - cookie validity is
            // enforced by the BFF on the next API call, and an invalid-but-
            // present cookie is handled by the client session restore. This
            // mirrors the former dashboard-layout check but keeps the whole
            // /dashboard tree statically prerenderable.
            if (!request.cookies.has(SESSION_COOKIE)) {
                return NextResponse.redirect(
                    new URL(
                        signinOrigin(
                            host,
                            request.nextUrl.protocol,
                            slug,
                            "Your session could not be established. Please sign in again.",
                        ),
                        request.url,
                    ),
                );
            }

            if (pathname === "/dashboard") {
                return NextResponse.redirect(
                    new URL(`/${request.nextUrl.search || ""}`, request.url),
                );
            }

            if (pathname === "/dashboard/invite") {
                // The workspace Invite page shares its name with the reserved auth
                // invite-accept route (/invite); keep it under /dashboard so the
                // normalize redirect below doesn't bounce it to the signin surface.
                return NextResponse.next();
            }

            if (
                pathname.startsWith("/dashboard/") &&
                !isInternalWorkspaceRewrite
            ) {
                return NextResponse.redirect(
                    new URL(
                        `${pathname.slice("/dashboard".length)}${request.nextUrl.search || ""}`,
                        request.url,
                    ),
                );
            }

            const internal =
                pathname === "/" ? "/dashboard" : `/dashboard${pathname}`;

            const headers = new Headers(request.headers);
            headers.set(INTERNAL_WORKSPACE_REWRITE_HEADER, "1");

            return NextResponse.rewrite(
                new URL(
                    `${internal}${request.nextUrl.search || ""}`,
                    request.url,
                ),
                {
                    request: {
                        headers,
                    },
                },
            );
        }
        default:
            return notFound();
    }
}

export const config = {
    // Skip Next-managed static assets and anything with a file extension.
    matcher: ["/((?!_next/static|_next/image|favicon.ico|.*\\..*).*)"],
};
