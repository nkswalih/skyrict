import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
    clearSignupFlow,
    loadSignupFlow,
    saveSignupFlow,
} from "./signup-flow-token";

const KEY = (email: string) =>
    `skyrict.onboarding.signupFlow:${email.trim().toLowerCase()}`;

/**
 * Vitest runs in the node environment here and the project carries no DOM
 * dependency, so the storage API itself is the only thing stubbed. Everything
 * under test - the address binding, the key shape, the behaviour on an empty or
 * missing value - is the real code.
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

    it("ignores surrounding whitespace, which the account step trims anyway", () => {
        saveSignupFlow("owner@neworg.com", "proof-1");

        expect(loadSignupFlow("  owner@neworg.com  ")).toBe("proof-1");
    });

    it("refuses a proof issued for a different address", () => {
        saveSignupFlow("owner@neworg.com", "proof-1");

        expect(loadSignupFlow("someone-else@elsewhere.com")).toBeNull();
    });

    it("keeps two signups in two tabs apart", () => {
        // The backend binds a proof to one address, so a shared key would have
        // the second tab clobber the first and report a session that never
        // expired.
        saveSignupFlow("owner@neworg.com", "proof-1");
        saveSignupFlow("someone-else@elsewhere.com", "proof-2");

        expect(loadSignupFlow("owner@neworg.com")).toBe("proof-1");
        expect(loadSignupFlow("someone-else@elsewhere.com")).toBe("proof-2");
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
        expect([...entries.keys()]).toEqual([KEY("owner@neworg.com")]);
    });

    it("stores the proof as the bare token, not a serialised envelope", () => {
        // A JSON blob would put the address in the value as well as the key,
        // for no benefit now that the key is scoped to it.
        saveSignupFlow("owner@neworg.com", "proof-1");

        expect(entries.get(KEY("owner@neworg.com"))).toBe("proof-1");
    });

    it("forgets the proof once it is spent, and only that one", () => {
        saveSignupFlow("owner@neworg.com", "proof-1");
        saveSignupFlow("someone-else@elsewhere.com", "proof-2");

        clearSignupFlow("owner@neworg.com");

        expect(loadSignupFlow("owner@neworg.com")).toBeNull();
        expect(loadSignupFlow("someone-else@elsewhere.com")).toBe("proof-2");
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
        expect(() => clearSignupFlow("owner@neworg.com")).not.toThrow();
    });

    it.each([
        ["an empty string", ""],
        ["whitespace", "   "],
        ["whitespace around a real proof", "  proof-1  "],
    ])("normalises %s", (_label, stored) => {
        entries.set(KEY("owner@neworg.com"), stored);

        expect(loadSignupFlow("owner@neworg.com")).toBe(
            stored.includes("proof-1") ? "proof-1" : null,
        );
    });
});
