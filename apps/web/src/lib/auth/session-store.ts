/**
 * In-memory access-token store (browser only).
 *
 * The access token never touches localStorage/sessionStorage - it lives in a
 * module variable and is re-hydrated on page load via /api/auth/session.
 */

import { RESERVED_SLUGS } from "@/lib/auth/reserved-slugs";

let accessToken: string | null = null;

export function setAccessToken(token: string | null): void {
    accessToken = token;
}

export function getAccessToken(): string | null {
    return accessToken;
}

/** Tenant slug for API calls: derived from the host, else NEXT_PUBLIC_TENANT_SLUG. */
export function getTenantSlug(): string {
    if (typeof window !== "undefined") {
        const match =
            /^([a-z0-9-]+)\.(?:signin\.)?(?:localhost|skyrict\.in)$/.exec(
                window.location.hostname,
            );
        if (match && !RESERVED_SLUGS.has(match[1])) return match[1];
    }
    return process.env.NEXT_PUBLIC_TENANT_SLUG ?? "";
}
