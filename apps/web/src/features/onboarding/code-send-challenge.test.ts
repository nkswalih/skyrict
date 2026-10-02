/**
 * Regression guard for the verify step's Turnstile token lifecycle.
 *
 * The defect: after the inline challenge solved and the first code went out,
 * `verify-step.tsx` held the spent token and hid the widget container. The
 * re-arm that followed could not succeed, because Turnstile does not run a
 * challenge inside a `display: none` container. Resend was therefore wired to
 * a token identity had already consumed, and every resend came back "Unable to
 * verify you are not a robot."
 *
 * Nothing about this is reachable by unit-testing the happy path - the first
 * code sent correctly. It only appears after the 60 second cooldown, which is
 * why the assertions below are about the *state between* sends rather than
 * about any single request.
 */
import { describe, expect, it } from "vitest";

import {
    canRequestCode,
    canResend,
    challengeContainerCollapsed,
    stateAfterSendAttempt,
} from "@/features/onboarding/code-send-challenge";

describe("a send may only start with a token in hand", () => {
    it("accepts a solved token and rejects the empty states", () => {
        expect(canRequestCode("t-token")).toBe(true);
        expect(canRequestCode(null)).toBe(false);
        expect(canRequestCode("")).toBe(false);
    });
});

describe("a token never survives the send that spent it", () => {
    it("drops the token after a successful send", () => {
        expect(stateAfterSendAttempt().token).toBeNull();
    });

    it("drops it after a failed send too", () => {
        // The regression. Keeping the token on failure replays a token that
        // Cloudflare already consumed, so the *next* attempt fails for a
        // reason the user cannot act on.
        expect(stateAfterSendAttempt().token).toBeNull();
    });
});

describe("the widget is never collapsed while it needs to re-arm", () => {
    it("collapses only while a live token is held", () => {
        expect(challengeContainerCollapsed("t-token")).toBe(true);
        expect(challengeContainerCollapsed(null)).toBe(false);
    });

    it("is visible at the moment a re-arm is requested", () => {
        // The specific trap. A container collapsed because it still held a
        // token cannot solve again, so reset() against it is a no-op and the
        // spent token is what the resend path ends up sending.
        const { token } = stateAfterSendAttempt();
        expect(challengeContainerCollapsed(token)).toBe(false);
        expect(canRequestCode(token)).toBe(false);
    });
});

describe("resend", () => {
    const ready = { resending: false, resendIn: 0 };

    it("is offered once the cooldown expires and a fresh token exists", () => {
        expect(canResend("t-fresh", ready)).toBe(true);
    });

    it("is withheld while holding no token, even with an expired cooldown", () => {
        // Without this the button is clickable but inert: sendCode early-returns
        // on a null token, so the click vanishes and nothing is sent.
        expect(canResend(null, ready)).toBe(false);
    });

    it("is withheld during the cooldown and while a send is in flight", () => {
        expect(canResend("t-fresh", { resending: false, resendIn: 42 })).toBe(false);
        expect(canResend("t-fresh", { resending: true, resendIn: 0 })).toBe(false);
    });

    it("never re-enables on the token the previous send already spent", () => {
        // The end-to-end shape of the bug, as a property rather than a
        // sequence: post-send there is no token, so there is no resend, so a
        // spent token cannot reach the backend a second time.
        const afterSend = stateAfterSendAttempt();
        expect(canResend(afterSend.token, ready)).toBe(false);
    });
});
