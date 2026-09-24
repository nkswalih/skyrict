import { describe, expect, it, vi } from "vitest";

const requestState = { host: "northwind.skyrict.in", proto: "https" };

vi.mock("next/headers", () => ({
    headers: async () =>
        new Headers({
            host: requestState.host,
            "x-forwarded-proto": requestState.proto,
        }),
}));

import { signinUrl, workspaceUrl } from "@/lib/server/urls";

function setOrigin(host: string, proto = "https"): void {
    requestState.host = host;
    requestState.proto = proto;
}

describe("signinUrl", () => {
    it("builds the tenant signin URL from a workspace host", async () => {
        setOrigin("northwind.skyrict.in");
        await expect(signinUrl()).resolves.toBe(
            "https://northwind.signin.skyrict.in/signin",
        );
    });

    it("appends the URL-encoded error query parameter", async () => {
        setOrigin("northwind.skyrict.in");
        await expect(signinUrl("Session failed")).resolves.toBe(
            "https://northwind.signin.skyrict.in/signin?error=Session%20failed",
        );
    });

    it("resolves the apex correctly from the bare apex host", async () => {
        setOrigin("skyrict.in");
        await expect(signinUrl()).resolves.toBe(
            "https://app.signin.skyrict.in/signin",
        );
    });

    it("reuses the incoming host on the signin surface", async () => {
        setOrigin("northwind.signin.skyrict.in");
        await expect(signinUrl()).resolves.toBe(
            "https://northwind.signin.skyrict.in/signin",
        );
    });
});

describe("workspaceUrl", () => {
    it("returns the workspace host unchanged", async () => {
        setOrigin("northwind.skyrict.in");
        await expect(workspaceUrl()).resolves.toBe(
            "https://northwind.skyrict.in",
        );
    });

    it("builds the workspace origin from the bare apex host", async () => {
        setOrigin("skyrict.in");
        await expect(workspaceUrl()).resolves.toBe("https://app.skyrict.in");
    });
});