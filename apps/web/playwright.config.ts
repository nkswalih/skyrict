/*
 * Playwright config for the multi-tenant E2E harness (SKY-103).
 *
 * The app serves four subdomain surfaces (see src/middleware.ts): marketing
 * (localhost), signup (signup.localhost), signin ({slug}.signin.localhost)
 * and workspace ({slug}.localhost). In CI all traffic reaches Next.js through
 * nginx on the E2E origin (E2E_BASE_URL, default http://default.localhost:3000;
 * nginx injects the tenant slug from the subdomain and proxies to the
 * `next start` server on :3100). Locally the dev server serves the same
 * surfaces directly.
 *
 * Projects:
 *   - setup: signs in as the seeded admin (through /signin on the signin
 *     surface), completes mandatory MFA enrollment, and saves the session to
 *     e2e/.auth/admin.json.
 *   - reports-smoke: runs the reporting suites already authenticated via the
 *     setup project's storage state, applied by each spec's own worker-scoped
 *     browser context fixture (the runner's default per-test context cannot
 *     be used; see the spec headers).
 *   - crm-finance (SKY-105): CRM deal pipeline + finance journeys. These
 *     specs sign in through the real signin surface via the `workspace`
 *     fixture (e2e/fixtures/auth.ts), which creates one worker-scoped
 *     browser context per worker and never reuses a shared storage-state
 *     snapshot, so the refresh-token rotation chain stays private to the
 *     worker.
 *
 * Workers and refresh-token rotation
 * ----------------------------------
 * The suite may run several workers (fullyParallel; CI defaults to 2).
 * Identity rotates the refresh token on every /api/auth/session hydration and
 * treats presenting an already-rotated token as token reuse, which revokes the
 * session family. Every worker therefore owns ONE worker-scoped browser
 * context (the `workspace` fixture in fixtures/auth.ts or the `tenant`
 * fixture in fixtures/tenants.ts) so its cookie jar advances a single rotation
 * chain (T0 -> T1 -> ...), exactly what identity expects. Never load the same
 * storage-state snapshot into two contexts.
 */

import { defineConfig } from "@playwright/test";

// Windows Node cannot resolve `*.localhost`; this makes BffApi's Node-side
// requests reach the E2E origin (served by nginx on 127.0.0.1) the same way
// CI and Chromium already do. No-op elsewhere.
// eslint-disable-next-line @typescript-eslint/no-require-imports
require("./e2e/localhost-dns.cjs");

const baseURL = process.env.E2E_BASE_URL ?? "http://default.localhost:3000";

/*
 * CI boots the whole stack (nginx + services via docker compose) and runs
 * `next start` itself, so Playwright must reuse that origin (E2E_SKIP_WEBSERVER=1).
 * Local runs reuse a running dev server when one is up, otherwise Playwright
 * boots `pnpm run dev` itself.
 */
const webServer =
    process.env.E2E_SKIP_WEBSERVER === "1"
        ? undefined
        : {
              command: "pnpm run dev",
              // Readiness probe must use `localhost`: the Node-side check cannot
              // resolve `*.localhost` (only Chromium can). Tests still navigate the
              // tenant surfaces via the URL builders under e2e/support/urls.ts.
              url: "http://localhost:3000/",
              reuseExistingServer: !process.env.CI,
              timeout: 120_000,
          };

export default defineConfig({
    testDir: "./e2e",
    // Worker-isolated sessions (see header) make parallel workers safe.
    fullyParallel: true,
    forbidOnly: Boolean(process.env.CI),
    retries: process.env.CI ? 2 : 0,
    workers: process.env.CI ? 2 : 1,
    timeout: 30_000,
    expect: { timeout: 8_000 },
    reporter: process.env.CI ? "html" : "list",
    use: {
        baseURL,
        trace: "on-first-retry",
        viewport: { width: 1280, height: 800 },
    },
    projects: [
        {
            name: "setup",
            testMatch: /auth\.setup\.ts/,
        },
        {
            name: "reports-smoke",
            testMatch: /(reports-workspace|dashboard-smoke)\.spec\.ts/,
            dependencies: ["setup"],
            // NOTE: no `use.storageState` here. The specs open a single
            // worker-scoped context per worker so the cookie jar can advance the
            // refresh-token rotation chain across their tests (see the headers).
        },
        {
            name: "crm-finance",
            testMatch: /(crm-pipeline|finance-journeys)\.spec\.ts/,
            dependencies: ["setup"],
            // NOTE: no `use.storageState` here either. The specs sign in through the
            // real signin surface using the `workspace` fixture, which creates a
            // fresh worker-scoped context - a brand-new token family that never
            // collides with another worker's rotation chain.
        },
        {
            name: "security",
            testMatch: /security\/.*\.spec\.ts/,
            dependencies: ["setup"],
            // Kills parallelism and retries on purpose: these specs run against a
            // tightened rate-limit stack (docker-compose.e2e.security.yml) where a
            // single replay would burn the exact budget they assert on. They run
            // in their own CI phase with --workers=1 --retries=0.
            fullyParallel: false,
            retries: 0,
            // NOTE: also excluded from the default `playwright test` run in CI -
            // the main phase passes explicit --project flags so the security suite
            // only ever runs on the tight stack.
        },
    ],
    ...(webServer ? { webServer } : {}),
});
