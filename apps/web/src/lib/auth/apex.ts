/**
 * Shared apex derivation for the app's hostname structure.
 *
 * Valid hosts are the bare apex (`skyrict.in`, dev `localhost`), the
 * `{label}.{apex}` forms (`web.skyrict.in`, `signup.skyrict.in`,
 * `{tenant}.skyrict.in`, dev `{tenant}.localhost`), `{label}.signin.{apex}`,
 * and Vercel preview names. The apex handed to URL builders is "everything
 * after the first label" — e.g. `signup.skyrict.in` -> `skyrict.in`,
 * `acme.signin.skyrict.in` -> `signin.skyrict.in`.
 *
 * A bare apex has NO label to strip. Applying `split(".").slice(1)` to
 * `skyrict.in` yields just the TLD (`in`), which corrupted cross-surface
 * handoffs from the apex host (`https://skyrict.in/signup` redirected to
 * `signup.in` instead of `signup.skyrict.in`). The apex-name set (mirroring
 * the allowlist regexes in lib/server/auth.ts) is the generic guard: hosts
 * that ARE the apex keep themselves; everything else strips exactly one
 * leading label. This also preserves dev workspace hosts (`acme.localhost` ->
 * `localhost`), which a plain "2 labels -> whole host" rule would break.
 *
 * Pure string function: safe in edge middleware, route handlers, and client
 * components alike. Callers strip any port and lowercase before calling.
 */

const APEX_NAMES = new Set(["localhost", "skyrict.in"]);

export function deriveApex(hostname: string): string {
    if (APEX_NAMES.has(hostname)) return hostname;
    const labels = hostname.split(".");
    if (labels.length <= 1 || /^\d+\.\d+\.\d+\.\d+$/.test(hostname)) {
        return hostname;
    }
    return labels.slice(1).join(".");
}