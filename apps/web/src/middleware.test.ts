/**
 * Routing contract tests for the host-based middleware.
 *
 * Covers the docs subdomain surface end to end: the docs.skyrict.in rewrite
 * onto the internal /docs tree (without exposing /docs in the browser URL),
 * the apex /docs redirect to the canonical docs hostname, the Vercel preview
 * fallback keeping /docs routes working, and the existing workspace/signin
 * surfaces staying untouched.
 */

import { NextRequest } from "next/server";
import { describe, expect, it } from "vitest";

import { middleware } from "@/middleware";

function nextRequest(
    url: string,
    init?: RequestInit,
): NextRequest {
    // The middleware resolves the surface from the Host header, which
    // `new Request()` does not derive from the URL, so forward it explicitly.
    const requestUrl = new URL(url);
    return new NextRequest(url, {
        ...init,
        headers: {
            host: requestUrl.host,
            ...((init?.headers as Record<string, string> | undefined) ?? {}),
        },
    } as ConstructorParameters<typeof NextRequest>[1]);
}

function redirectLocation(response: Response): string | null {
    return response.headers.get("location");
}

function rewriteTarget(response: Response): string | null {
    return response.headers.get("x-middleware-rewrite");
}

describe("docs surface (docs.skyrict.in)", () => {
    it("serves the internal /docs page at the docs root", () => {
        const response = middleware(nextRequest("https://docs.skyrict.in/"));

        expect(response.status).toBe(200);
        expect(rewriteTarget(response)).toMatch(/\/docs$/);
    });

    it.each([
        ["/getting-started", "/docs/getting-started"],
        [
            "/getting-started/create-account",
            "/docs/getting-started/create-account",
        ],
        ["/search", "/docs/search"],
    ])("rewrites %s to %s", (publicPath, internalPath) => {
        const response = middleware(
            nextRequest(`https://docs.skyrict.in${publicPath}`),
        );

        expect(rewriteTarget(response)).toContain(internalPath);
    });

    it("passes /docs-prefixed paths through unchanged (docs links + fallback)", () => {
        const response = middleware(
            nextRequest("https://docs.skyrict.in/docs/getting-started"),
        );

        expect(rewriteTarget(response)).toContain("/docs/getting-started");
    });

    it("keeps the query string on the rewrite", () => {
        const response = middleware(
            nextRequest("https://docs.skyrict.in/getting-started?tab=local"),
        );

        expect(rewriteTarget(response)).toContain(
            "/docs/getting-started?tab=local",
        );
    });

    it("never classifies docs.skyrict.in as a workspace (no /dashboard rewrite)", () => {
        const response = middleware(nextRequest("https://docs.skyrict.in/"));

        expect(rewriteTarget(response)).toContain("/docs");
        expect(rewriteTarget(response)).not.toContain("/dashboard");
    });

    it("leaves auth paths on the docs host redirecting to the signup origin", () => {
        const response = middleware(
            nextRequest("https://docs.skyrict.in/signup"),
        );

        expect(response.status).toBe(307);
        expect(redirectLocation(response)).toBe(
            "https://signup.skyrict.in/signup",
        );
    });

    it("serves the root-level OG image without remapping it under /docs", () => {
        const response = middleware(
            nextRequest("https://docs.skyrict.in/opengraph-image"),
        );

        expect(response.status).toBe(200);
        expect(rewriteTarget(response)).toBeNull();
    });

    it("serves the docs surface on the dev host (docs.localhost)", () => {
        const response = middleware(
            nextRequest("http://docs.localhost/getting-started"),
        );

        expect(rewriteTarget(response)).toContain("/docs/getting-started");
    });
});

describe("apex docs redirect (skyrict.in)", () => {
    it("redirects /docs to the canonical docs hostname", () => {
        const response = middleware(nextRequest("https://skyrict.in/docs"));

        expect(response.status).toBe(308);
        expect(redirectLocation(response)).toMatch(
            /^https:\/\/docs\.skyrict\.in\/?$/,
        );
    });

    it("redirects /docs/* preserving the path and query", () => {
        const response = middleware(
            nextRequest(
                "https://skyrict.in/docs/getting-started?tab=local",
            ),
        );

        expect(response.status).toBe(308);
        expect(redirectLocation(response)).toBe(
            "https://docs.skyrict.in/getting-started?tab=local",
        );
    });

    it("does not redirect on the Vercel deployment fallback (/docs root)", () => {
        const response = middleware(
            nextRequest("https://skyrict.vercel.app/docs"),
        );

        expect(response.status).toBe(200);
        expect(redirectLocation(response)).toBeNull();
        expect(rewriteTarget(response)).toBeNull();
    });

    it("keeps the Vercel fallback /docs/* routes working", () => {
        const response = middleware(
            nextRequest("https://skyrict.vercel.app/docs/getting-started"),
        );

        expect(response.status).toBe(200);
        expect(redirectLocation(response)).toBeNull();
        expect(rewriteTarget(response)).toBeNull();
    });

    it("does not redirect on the marketing web host", () => {
        const response = middleware(nextRequest("https://web.skyrict.in/docs"));

        expect(response.status).toBe(200);
        expect(redirectLocation(response)).toBeNull();
    });
});

describe("existing surfaces stay untouched", () => {
    it("keeps the tenant workspace surface (rewrite to /dashboard)", () => {
        const response = middleware(
            nextRequest("https://northwind.skyrict.in/", {
                headers: { cookie: "skyrict_session=abc" },
            }),
        );

        expect(rewriteTarget(response)).toContain("/dashboard");
    });

    it("keeps the tenant signin surface (rewrite to /login)", () => {
        const response = middleware(
            nextRequest("https://northwind.signin.skyrict.in/signin"),
        );

        expect(rewriteTarget(response)).toContain("/login");
    });

    it("still 404s unknown hosts", () => {
        const response = middleware(nextRequest("https://evil.example.com/"));

        expect(rewriteTarget(response)).toContain("/_not-found");
    });
});