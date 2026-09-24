/**
 * Platform-owned workspace slugs that can never be tenant subdomains.
 *
 * Mirrors identity.core.constants.RESERVED_SLUGS so the BFF and the browser
 * reject platform hosts (web.skyrict.in, app.skyrict.in, ...) the same way
 * the identity service does.
 */
export const RESERVED_SLUGS = new Set([
    "admin",
    "api",
    "app",
    "blog",
    "docs",
    "dev",
    "help",
    "mail",
    "signin",
    "signup",
    "staging",
    "status",
    "support",
    "test",
    "web",
    "www",
    "acme",
    "skyrict",
]);
