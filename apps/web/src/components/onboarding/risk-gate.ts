/**
 * Sign-up anti-bot gate policy.
 *
 * Extracted from the component on purpose. The policy - when the gate is shown,
 * what may be claimed, and what actually counts as "passed" - is the part that
 * regressed in pre-release audit finding 23, and it is pure logic with no reason
 * to be locked inside JSX where it cannot be asserted without a DOM.
 *
 * The rule this module exists to enforce: the client may never assert a
 * verification it has not obtained. A Turnstile token is not a verification -
 * the token is minted by Cloudflare in the browser and only becomes a verdict
 * when the server exchanges it at sign-up time. So the strongest claim the
 * client is ever entitled to make is "a token is ready to submit".
 */

/** How the sign-up gate should present itself. */
export type RiskGateMode =
    /** A provider is configured: show the managed challenge. */
    | "challenge"
    /**
     * No provider is configured. This is a deployment fault, and the gate is
     * closed rather than decorative - a control that looks like a gate but
     * passes everyone hides the fault from the user and the operator alike.
     */
    | "unavailable"
    /** No provider and no demo override: the gate does not apply at all. */
    | "hidden";

export interface RiskGateInput {
    /** The Turnstile site key, empty when unconfigured. */
    turnstileSiteKey: string;
    /**
     * Forces the gate visible in a demo build that has no provider. It changes
     * only whether the gate is shown - it never grants a pass, because a demo
     * flag must not become a way to bypass the real challenge.
     */
    demoCaptcha?: boolean;
}

export function resolveRiskGate({
    turnstileSiteKey,
    demoCaptcha = false,
}: RiskGateInput): RiskGateMode {
    if (turnstileSiteKey.trim() !== "") return "challenge";
    return demoCaptcha ? "unavailable" : "hidden";
}

/**
 * Whether the sign-up form may proceed.
 *
 * True only once a challenge token exists. In `unavailable` mode this is
 * always false - the point of the mode is that the form is genuinely closed,
 * so that a deployment fault is visible immediately instead of surfacing later
 * as an unexplained 4xx from the sign-up endpoint.
 */
export function canProceed(mode: RiskGateMode, token: string | null): boolean {
    if (mode === "unavailable") return false;
    if (mode === "hidden") return true;
    return Boolean(token);
}

/**
 * Whether the UI may render the word "Verified".
 *
 * Always false, and deliberately expressed as a function rather than simply
 * never writing the word. The original defect was a checkbox that set a
 * `verified` state from a stubbed response; the recovery path was "the client
 * cannot know". That is a property of the system, not an implementation detail
 * of one component, so it is expressed once here and asserted in tests. If a
 * future server-verified handshake makes this true, this function is the single
 * place that has to change - deliberately, and with its tests updated.
 */
export function mayClaimVerified(): false {
    return false;
}
