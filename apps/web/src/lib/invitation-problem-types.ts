/**
 * How the web app reads identity's RFC 7807 problem types for a bad invite.
 *
 * The full `type` URI is `https://api.skyrict.in/problems/<slug>`, and this
 * used to be spelled out in full in the invite page. That made the web app a
 * second, separately-maintained copy of a backend contract, in a different
 * language: the moment either side moved domain, an expired invitation would
 * have been reported to the user as "invalid", with no error on either side to
 * explain why. The public domain has in fact moved three times.
 *
 * Matching on the trailing slug instead makes this independent of which host
 * publishes the contract, and is how the rest of the repo already asserts on
 * problem types (see
 * `services/core/tests/integration/api/test_concurrency_atomicity.py`, which
 * asserts `type.endsWith("/duplicate-record")`).
 *
 * It is a separate module from the page so it can be unit-tested: vitest runs
 * on `src` test files in a node environment, so a `.tsx` React page cannot be
 * imported by a test at all. Same reason as `risk-gate.ts`.
 */

/** Problem-type slugs identity returns when an invite token is no longer usable. */
const INVITATION_PROBLEM_SLUGS = {
    expired: "/invitation-expired",
    alreadyUsed: "/invitation-already-used",
} as const;

/** The invite failure a problem `type` identifies, if it is one of ours. */
export type InviteProblem = keyof typeof INVITATION_PROBLEM_SLUGS;

/**
 * Identify an invite failure from an RFC 7807 `type`.
 *
 * Returns null for anything else, including a missing or non-string `type`:
 * an unrecognised problem is not evidence of any particular invite failure, and
 * the caller must fall back to its own "invalid" outcome rather than guess.
 *
 * The `endsWith` comparison is exact on the slug boundary. A suffix test alone
 * would also match a hypothetical `.../invitation-expired-v2`, but the slug is
 * the full path segment, so a longer name is a different problem and is left
 * unmatched.
 */
export function classifyInviteProblem(type: unknown): InviteProblem | null {
    if (typeof type !== "string") return null;
    for (const [problem, slug] of Object.entries(INVITATION_PROBLEM_SLUGS)) {
        if (type.endsWith(slug)) return problem as InviteProblem;
    }
    return null;
}
