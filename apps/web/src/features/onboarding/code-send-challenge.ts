/**
 * Token lifecycle for the inline Turnstile challenge on the verify step.
 *
 * Extracted from `verify-step.tsx` so these rules are testable without a DOM.
 *
 * The rule that matters is not obvious, and it was previously wrong in a way
 * that only shows up after the resend cooldown:
 *
 * 1. A Turnstile token is single-use. Cloudflare consumes it during
 *    verification whether or not the rest of the request then succeeds, so a
 *    token must never survive the send that spent it.
 * 2. Turnstile will not run a challenge inside a `display: none` container.
 *
 * Combine the two and you get a trap. If the widget container is hidden while a
 * token is held - which is what "collapse the widget once it has solved"
 * implies - then the reset that follows a send cannot produce a fresh token,
 * because it is running against a hidden widget. The component then keeps the
 * already-spent token, and the resend button replays it. Identity rejects it as
 * a duplicate, and the user is told to prove they are not a robot on a request
 * that had already been proven.
 *
 * The fix is to drop the token at the moment of the send, which both honours
 * rule 1 and re-shows the container, satisfying rule 2.
 */

/** The token a send consumed, and the cooldown it started, if it succeeded. */
export interface SendAttempt {
    /** The token spent by this attempt, or null when nothing was sent. */
    spent: string | null;
    /** Seconds until resend is offered; null when the attempt failed. */
    cooldownSeconds: number | null;
}

/**
 * A send may only start with a token actually in hand.
 *
 * A type predicate rather than a plain boolean so the caller gets the narrowed
 * type back and does not have to assert what this already established.
 */
export function canRequestCode(token: string | null): token is string {
    return token !== null && token !== "";
}

/**
 * The state to hold after a send attempt, successful or not.
 *
 * The token is dropped either way. Clearing it on failure matters as much as
 * on success: a failed request has usually still had its token consumed by
 * verification, so keeping it would guarantee the next attempt replays a dead
 * token.
 */
export function stateAfterSendAttempt(): { token: null } {
    return { token: null };
}

/**
 * Whether the widget container may be collapsed.
 *
 * Collapsed only while a live token is held. Because every send leaves the
 * token null, a container is never collapsed at the moment it needs to
 * re-arm - which is the entire point of the distinction.
 */
export function challengeContainerCollapsed(token: string | null): boolean {
    return canRequestCode(token);
}

/**
 * Whether the resend affordance is available.
 *
 * An expired cooldown is necessary but not sufficient. The button also needs an
 * unspent token, otherwise `sendCode` early-returns and the click is silently
 * swallowed - the user sees a button that does nothing.
 */
export function canResend(
    token: string | null,
    { resending, resendIn }: { resending: boolean; resendIn: number },
): boolean {
    return canRequestCode(token) && !resending && resendIn <= 0;
}
