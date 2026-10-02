/**
 * Carries the sign-up flow proof from step 1 to step 2.
 *
 * sessionStorage rather than the URL. The proof is what authorises sending mail
 * to the address, so it must not end up in browser history, a `Referer` header
 * or an access log. `wizard-session.ts` sets the precedent for keeping
 * pre-login wizard context on this side of the wire.
 *
 * Bound to the address it was issued for. A proof left behind by a different
 * email is refused here instead of being sent to the backend to be rejected
 * there, which is the difference between "start again" and a 422.
 */

interface StoredFlow {
    email: string;
    flowToken: string;
}

const KEY = "skyrict.onboarding.signupFlow";

export function saveSignupFlow(email: string, flowToken: string): void {
    try {
        const payload: StoredFlow = { email, flowToken };
        sessionStorage.setItem(KEY, JSON.stringify(payload));
    } catch {
        /* SSR or private-browsing - safe to ignore. */
    }
}

export function loadSignupFlow(email: string): string | null {
    try {
        const raw = sessionStorage.getItem(KEY);
        if (!raw) return null;
        const stored = JSON.parse(raw) as Partial<StoredFlow> | null;
        if (typeof stored?.flowToken !== "string" || stored.flowToken === "") {
            return null;
        }
        if (typeof stored.email !== "string") return null;
        return stored.email.toLowerCase() === email.toLowerCase()
            ? stored.flowToken
            : null;
    } catch {
        return null;
    }
}

export function clearSignupFlow(): void {
    try {
        sessionStorage.removeItem(KEY);
    } catch {
        /* noop */
    }
}
