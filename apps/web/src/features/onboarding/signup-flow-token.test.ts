import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
    clearSignupFlow,
    loadSignupFlow,
    saveSignupFlow,
} from "./signup-flow-token";

const KEY = "skyrict.onboarding.signupFlow";

/**
 * Vitest runs in the node environment here and the project carries no DOM
 * dependency, so the storage API itself is the only thing stubbed. Everything
 * under test - the JSON shape, the address binding, the casing rule, the
 * behaviour on rubbish input - is the real code.
 */
function stubSessionStorage(): Map<string, string> {
    const entries = new Map<string, string>();
    vi.stubGlobal("sessionStorage", {
        getItem: (key: string) => entries.get(key) ?? null,
        setItem: (key: string, value: string) => {
            entries.set(key, value);
        },
        removeItem: (key: string) => {
            entries.delete(key);
        },
        clear: () => {
            entries.clear();
        },
    });
    return entries;
}

describe("signup flow proof storage", () => {
    let entries: Map<string, string>;

    beforeEach(() => {
        entries = stubSessionStorage();
    });

    afterEach(() => {
        vi.unstubAllGlobals();
    });

    it("hands the proof back for the address it was issued for", () => {
        saveSignupFlow("owner@neworg.com", "proof-1");

        expect(loadSignupFlow("owner@neworg.com")).toBe("proof-1");
    });

    it("matches the address the way the backend does", () => {
        saveSignupFlow("owner@neworg.com", "proof-1");

        expect(loadSignupFlow("Owner@NewOrg.com")).toBe("proof-1");
    });

    it("refuses a proof issued for a different address", () => {
        saveSignupFlow("owner@neworg.com", "proof-1");

        expect(loadSignupFlow("someone-else@elsewhere.com")).toBeNull();
    });

    it("returns null when nothing was stored", () => {
        expect(loadSignupFlow("owner@neworg.com")).toBeNull();
    });

    it("replaces an earlier proof rather than keeping both", () => {
        saveSignupFlow("owner@neworg.com", "proof-1");
        saveSignupFlow("owner@neworg.com", "proof-2");

        expect(loadSignupFlow("owner@neworg.com")).toBe("proof-2");
    });

    it("writes the proof to sessionStorage and nowhere else", () => {
        saveSignupFlow("owner@neworg.com", "proof-1");

        // The proof is what authorises sending mail to the address, so it stays
        // out of anything a Referer header or an access log would pick up.
        expect([...entries.keys()]).toEqual([KEY]);
    });

    it("forgets the proof once it is spent", () => {
        saveSignupFlow("owner@neworg.com", "proof-1");
        clearSignupFlow();

        expect(loadSignupFlow("owner@neworg.com")).toBeNull();
    });

    it("survives storage throwing", () => {
        vi.stubGlobal("sessionStorage", {
            getItem: () => {
                throw new Error("denied");
            },
            setItem: () => {
                throw new Error("denied");
            },
            removeItem: () => {
                throw new Error("denied");
            },
        });

        // Private browsing and blocked third-party storage both do this. The
        // wizard must degrade to "no proof", not to a crash on render.
        expect(() => saveSignupFlow("owner@neworg.com", "proof-1")).not.toThrow();
        expect(loadSignupFlow("owner@neworg.com")).toBeNull();
        expect(() => clearSignupFlow()).not.toThrow();
    });

    it.each([
        ["not json", "definitely not json"],
        ["a json scalar", "42"],
        ["null", "null"],
        ["an empty token", JSON.stringify({ email: "owner@neworg.com", flowToken: "" })],
        ["a missing token", JSON.stringify({ email: "owner@neworg.com" })],
        ["a non-string email", JSON.stringify({ email: 7, flowToken: "proof-1" })],
    ])("treats %s as no proof at all", (_label, stored) => {
        entries.set(KEY, stored);

        expect(loadSignupFlow("owner@neworg.com")).toBeNull();
    });
});
