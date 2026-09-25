/**
 * Client-side URL helpers mirroring the middleware's cross-surface routing.
 * Kept free of React so any browser module (session provider, API client) can
 * compute the tenant signin origin without a circular import.
 */

/**
 * Absolute `{slug}.signin.{apex}:{port}/signin` URL for the current origin,
 * mirroring the middleware's cross-surface routing. Falls back to the current
 * origin's `/signin` when there is no tenant label (dev without a subdomain).
 */

import { deriveApex } from "@/lib/auth/apex";

export function browserSigninUrl(): string {
    const { protocol, hostname, port } = window.location;
    const host = hostname.toLowerCase();
    const portSuffix = port ? `:${port}` : "";
    if (host.includes(".signin."))
        return `${protocol}//${host}${portSuffix}/signin`;
    const labels = host.split(".");
    // No tenant label (bare dev host): fall back to the same-origin /signin.
    if (labels.length <= 1) return `${protocol}//${host}${portSuffix}/signin`;
    const apex = deriveApex(host);
    const slug = labels[0];
    return `${protocol}//${slug}.signin.${apex}${portSuffix}/signin`;
}
