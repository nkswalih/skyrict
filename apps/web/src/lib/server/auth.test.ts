import { afterEach, describe, expect, it, vi } from "vitest";

import { hostSurface, resolveTenantSlug } from "@/lib/server/auth";

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
