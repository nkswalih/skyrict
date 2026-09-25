/**
 * Server-only (Node runtime) origin helpers.
 *
 * The workspace and signin surfaces live on different subdomains, so server
 * components and BFF redirects must build absolute cross-origin URLs from the
 * incoming Host header. Do not import this module from middleware (edge).
 */

import { headers } from "next/headers";

import { baseParts, hostSurface, resolveTenantSlug } from "@/lib/server/auth";

interface OriginParts {
    proto: string;
    port: string;
    apex: string;
    host: string;
}

async function originParts(): Promise<OriginParts> {
    const h = await headers();
    const host = h.get("host") ?? "";
    const forwarded = h.get("x-forwarded-proto");
    const proto =
        forwarded?.split(",")[0]?.trim() ??
        (process.env.NODE_ENV === "production" ? "https" : "http");
    const { port, apex } = baseParts(host);
    return { proto, port, apex, host };
}

/** Absolute `{slug}.signin.{apex}/signin` URL for the current tenant. */
export async function signinUrl(error?: string): Promise<string> {
    const { proto, port, apex, host } = await originParts();
    const { surface, slug } = hostSurface(host);
    const tenant = slug || resolveTenantSlug(host) || "app";
    const base =
        surface === "signin"
            ? `${proto}://${host}/signin`
            : `${proto}://${tenant}.signin.${apex}${port}/signin`;
    return error ? `${base}?error=${encodeURIComponent(error)}` : base;
}

/** Absolute `{slug}.{apex}` origin for the current tenant. */
export async function workspaceUrl(): Promise<string> {
    const { proto, port, apex, host } = await originParts();
    const { surface, slug } = hostSurface(host);
    if (surface === "workspace") return `${proto}://${host}`;
    const tenant = slug || resolveTenantSlug(host) || "app";
    return `${proto}://${tenant}.${apex}${port}`;
}
