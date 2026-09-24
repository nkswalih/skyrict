import { describe, expect, it } from "vitest";

import { docsActiveHref, surfacePathFor } from "@/content/docs";

describe("surfacePathFor", () => {
    it("returns the docs-surface route without the /docs prefix", () => {
        expect(
            surfacePathFor("getting-started", "create-account"),
        ).toBe("/getting-started/create-account");
    });
});

describe("docsActiveHref", () => {
    it("keeps /docs-prefixed paths (apex + Vercel fallback) unchanged", () => {
        expect(docsActiveHref("/docs")).toBe("/docs");
        expect(docsActiveHref("/docs/getting-started")).toBe(
            "/docs/getting-started",
        );
    });

    it("maps the docs surface root to the /docs route", () => {
        expect(docsActiveHref("/")).toBe("/docs");
    });

    it("maps docs-surface paths (no /docs prefix) to the /docs route", () => {
        expect(docsActiveHref("/getting-started")).toBe(
            "/docs/getting-started",
        );
    });
});