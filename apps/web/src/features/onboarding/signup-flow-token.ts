/**
 * Carries the sign-up flow proof from step 1 to step 2.
 *
 * sessionStorage rather than the URL. The proof is what authorises sending mail
 * to the address, so it must not end up in browser history, a `Referer` header
 * or an access log. `wizard-session.ts` sets the precedent for keeping
 * pre-login wizard context on this side of the wire.
 *
 * Keyed by the address the proof was issued for. The backend binds it that way,
 * so two tabs signing up different people no longer overwrite each other and
 * report a session that was never lost. The address is already in the URL of
 * both steps, so the key adds no exposure.
 */

const KEY_PREFIX = "skyrict.onboarding.signupFlow:";

function key(email: string): string {
    return `${KEY_PREFIX}${email.trim().toLowerCase()}`;
}

export function saveSignupFlow(email: string, flowToken: string): void {
    try {
        sessionStorage.setItem(key(email), flowToken);
    } catch {
        /* SSR or private-browsing - safe to ignore. */
    }
}

export function loadSignupFlow(email: string): string | null {
    try {
        // The backend cannot issue a blank proof, so neither is one worth
        // carrying. Without this a whitespace value would be sent on and come
        // back as a 422 the user cannot act on.
        const stored = sessionStorage.getItem(key(email))?.trim();
        return stored ? stored : null;
    } catch {
        return null;
    }
}

export function clearSignupFlow(email: string): void {
    try {
        sessionStorage.removeItem(key(email));
    } catch {
        /* noop */
    }
}
