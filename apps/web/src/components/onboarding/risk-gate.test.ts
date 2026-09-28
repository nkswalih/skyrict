/**
 * Regression guard for pre-release audit finding 23.
 *
 * The defect was not that the captcha was bypassable - it was that the UI
 * asserted a verification that had never happened. A checkbox flipped itself
 * to "Verified" because a hardcoded stub returned `{ status: "ok" }` without a
 * network call, while identity fails closed on an unconfigured Turnstile
 * secret. The user was told they had passed a check, filled in the whole form,
 * and only then received an opaque 4xx.
 *
 * The contract under test is about *claims*, not about controls being disabled.
 * A test that only asserted "the button is disabled" would have passed against
 * the broken code, which is the trap this file exists to close.
 */
import { describe, expect, it } from "vitest";

import {
    canProceed,
    mayClaimVerified,
    resolveRiskGate,
} from "@/components/onboarding/risk-gate";

describe("resolveRiskGate", () => {
    it("shows the managed challenge when a provider is configured", () => {
        expect(
            resolveRiskGate({ turnstileSiteKey: "1x00000000000000000000AA" }),
        ).toBe("challenge");
    });

    it("refuses to render a gate it cannot enforce when a demo asks for one", () => {
        // The regression. `?demoCaptcha=1` with no configured provider used to
        // render a checkbox that certified itself. The demo flag asks for the
        // gate to be visible; it must never manufacture a pass, so the honest
        // answer is a closed gate rather than a decorative one.
        expect(
            resolveRiskGate({ turnstileSiteKey: "", demoCaptcha: true }),
        ).toBe("unavailable");
    });

    it("hides the gate when no provider is set and no demo asks for one", () => {
        // A deliberate third state, not an oversight. apps/web/.env.example
        // ships the site key empty, so this is the default for a fresh
        // checkout, and account-step.tsx does not consult the captcha in this
        // state - it requires env.turnstileSiteKey before blocking a submit.
        //
        // Called out explicitly because the tempting "fix" is to fold this into
        // "unavailable" and close sign-up wherever the provider is missing.
        // That is a product decision disguised as a bug fix.
        expect(resolveRiskGate({ turnstileSiteKey: "" })).toBe("hidden");
        expect(
            resolveRiskGate({ turnstileSiteKey: "", demoCaptcha: false }),
        ).toBe("hidden");
    });

    it("treats a blank key as absent in every combination", () => {
        // A present-but-whitespace key is the exact shape of a mis-set
        // environment variable. It must behave identically to "" rather than
        // rendering a challenge widget that can never succeed.
        expect(resolveRiskGate({ turnstileSiteKey: "   " })).toBe("hidden");
        expect(
            resolveRiskGate({ turnstileSiteKey: "   ", demoCaptcha: true }),
        ).toBe("unavailable");
    });
});

describe("canProceed", () => {
    it("requires a token before the challenge passes", () => {
        expect(canProceed("challenge", null)).toBe(false);
        expect(canProceed("challenge", "")).toBe(false);
        expect(canProceed("challenge", "token-abc")).toBe(true);
    });

    it("never lets the form proceed while the gate is closed as unavailable", () => {
        // Even a token - stale, replayed, or from a demo flag - must not open a
        // closed gate.
        expect(canProceed("unavailable", null)).toBe(false);
        expect(canProceed("unavailable", "token-abc")).toBe(false);
    });

    it("does not obstruct sign-up when the gate does not apply", () => {
        expect(canProceed("hidden", null)).toBe(true);
    });
});

describe("mayClaimVerified", () => {
    it("is unconditionally false", () => {
        // Not a snapshot of current behaviour - a standing assertion that the
        // client is incapable of verifying anything. The server is the only
        // party that can make that claim, and it makes it at sign-up time. If a
        // future server-verified handshake makes this true, this function is the
        // single place that has to change, deliberately, with its tests updated.
        expect(mayClaimVerified()).toBe(false);
    });
});
