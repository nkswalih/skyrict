import { afterEach, describe, expect, it, vi } from "vitest";

import {
    deriveApex,
    hostSurface,
    resolveTenantSlug,
    signinOrigin,
    signupOrigin,
} from "@/lib/server/auth";

afterEach(() => {
    vi.unstubAllEnvs();
});

describe("hostSurface", () => {
    it("maps apex production and dev hosts to marketing", () => {
        expect(hostSurface("skyrict.in")).toEqual({
            surface: "marketing",
            slug: "",
        });
        expect(hostSurface("localhost")).toEqual({
            surface: "marketing",
            slug: "",
        });
        expect(hostSurface("127.0.0.1")).toEqual({
            surface: "marketing",
            slug: "",
        });
    });

    it("maps web.* apex hosts to marketing", () => {
        expect(hostSurface("web.skyrict.in")).toEqual({
            surface: "marketing",
            slug: "",
        });
    });

    it("maps signup.skyrict.in to the signup surface", () => {
        expect(hostSurface("signup.skyrict.in")).toEqual({
            surface: "signup",
            slug: "",
        });
    });

    it("maps {tenant}.skyrict.in to the workspace surface with its slug", () => {
        expect(hostSurface("northwind.skyrict.in")).toEqual({
            surface: "workspace",
            slug: "northwind",
        });
    });

    it("maps {tenant}.signin.skyrict.in to the signin surface", () => {
        expect(hostSurface("northwind.signin.skyrict.in")).toEqual({
            surface: "signin",
            slug: "northwind",
        });
    });

    it("rejects reserved platform slugs on the production apex", () => {
        expect(hostSurface("app.skyrict.in")).toEqual({
            surface: "unknown",
            slug: "",
        });
        expect(hostSurface("www.skyrict.in")).toEqual({
            surface: "unknown",
            slug: "",
        });
    });

    it("maps Vercel preview hosts to the marketing surface", () => {
        expect(
            hostSurface(
                "skyrict-web-git-fix-vercel-routing-1a2b3c4d.vercel.app",
            ),
        ).toEqual({ surface: "marketing", slug: "" });
        expect(hostSurface("skyrict-web-1a2b3c4d.vercel.app")).toEqual({
            surface: "marketing",
            slug: "",
        });
    });

    it("rejects obsolete skyrict.com hosts", () => {
        expect(hostSurface("skyrict.com")).toEqual({
            surface: "unknown",
            slug: "",
        });
        expect(hostSurface("northwind.skyrict.com")).toEqual({
            surface: "unknown",
            slug: "",
        });
        expect(hostSurface("northwind.signin.skyrict.com")).toEqual({
            surface: "unknown",
            slug: "",
        });
    });

    it("rejects hosts outside the allowlisted origins", () => {
        expect(hostSurface("evil.example.com")).toEqual({
            surface: "unknown",
            slug: "",
        });
        expect(hostSurface("northwind.vercel.app.evil.example")).toEqual({
            surface: "unknown",
            slug: "",
        });
        expect(hostSurface(null)).toEqual({ surface: "unknown", slug: "" });
    });
});

describe("resolveTenantSlug", () => {
    it("returns the slug for workspace and signin hosts", () => {
        expect(resolveTenantSlug("northwind.skyrict.in")).toBe("northwind");
        expect(resolveTenantSlug("northwind.signin.skyrict.in")).toBe(
            "northwind",
        );
    });

    it("returns empty for marketing and preview hosts (no dev TENANT_SLUG)", () => {
        vi.stubEnv("TENANT_SLUG", "");
        expect(resolveTenantSlug("skyrict.in")).toBe("");
        expect(resolveTenantSlug("web.skyrict.in")).toBe("");
        expect(
            resolveTenantSlug("skyrict-web-git-fix-1a2b3c4d.vercel.app"),
        ).toBe("");
    });

    it("falls back to the dev-only TENANT_SLUG for unknown hosts outside production", () => {
        vi.stubEnv("TENANT_SLUG", "tenant-fallback");
        expect(resolveTenantSlug("unknown.invalid")).toBe("tenant-fallback");
    });
});

describe("deriveApex", () => {
    it("keeps the bare apex and dev hosts intact", () => {
        expect(deriveApex("skyrict.in")).toBe("skyrict.in");
        expect(deriveApex("localhost")).toBe("localhost");
        expect(deriveApex("127.0.0.1")).toBe("127.0.0.1");
    });

    it("strips exactly the leading label from tenant/role hosts", () => {
        expect(deriveApex("signup.skyrict.in")).toBe("skyrict.in");
        expect(deriveApex("web.skyrict.in")).toBe("skyrict.in");
        expect(deriveApex("www.skyrict.in")).toBe("skyrict.in");
        expect(deriveApex("acme.skyrict.in")).toBe("skyrict.in");
        expect(deriveApex("northwind.skyrict.in")).toBe("skyrict.in");
        expect(deriveApex("acme.localhost")).toBe("localhost");
    });

    it("keeps the .signin. suffix when derived from a signin host", () => {
        expect(deriveApex("acme.signin.skyrict.in")).toBe(
            "signin.skyrict.in",
        );
        expect(deriveApex("northwind.signin.skyrict.in")).toBe(
            "signin.skyrict.in",
        );
    });

    it("keeps Vercel preview hostnames resolvable", () => {
        expect(
            deriveApex("skyrict-web-git-fix-vercel-routing-1a2b3c4d.vercel.app"),
        ).toBe("vercel.app");
    });
});

describe("signupOrigin", () => {
    it("redirects the apex host to the signup subdomain", () => {
        expect(signupOrigin("skyrict.in", "https:")).toBe(
            "https://signup.skyrict.in/signup",
        );
    });

    it("redirects other marketing hosts to the signup origin", () => {
        expect(signupOrigin("web.skyrict.in", "https:")).toBe(
            "https://signup.skyrict.in/signup",
        );
    });

    it("keeps the dev host and port", () => {
        expect(signupOrigin("localhost:3000", "http:")).toBe(
            "http://signup.localhost:3000/signup",
        );
    });
});

describe("signinOrigin", () => {
    it("redirects a workspace host to its tenant signin host", () => {
        expect(signinOrigin("acme.skyrict.in", "https:", "acme")).toBe(
            "https://acme.signin.skyrict.in/signin",
        );
        expect(signinOrigin("northwind.skyrict.in", "https:", "northwind")).toBe(
            "https://northwind.signin.skyrict.in/signin",
        );
    });

    it("keeps the dev host/port and forwards the error message", () => {
        expect(signinOrigin("acme.localhost:3000", "http:", "acme")).toBe(
            "http://acme.signin.localhost:3000/signin",
        );
        expect(
            signinOrigin("acme.skyrict.in", "https:", "acme", "Session failed"),
        ).toBe("https://acme.signin.skyrict.in/signin?error=Session%20failed");
    });
});

describe("cross-surface classification (hostSurface unchanged)", () => {
    it("keeps signup.skyrict.in on the signup surface", () => {
        expect(hostSurface("signup.skyrict.in")).toEqual({
            surface: "signup",
            slug: "",
        });
    });

    it("keeps northwind.skyrict.in on the workspace surface", () => {
        expect(hostSurface("northwind.skyrict.in")).toEqual({
            surface: "workspace",
            slug: "northwind",
        });
    });

    it("keeps northwind.signin.skyrict.in on the signin surface", () => {
        expect(hostSurface("northwind.signin.skyrict.in")).toEqual({
            surface: "signin",
            slug: "northwind",
        });
    });
});
