/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Keep recently-visited dynamic pages (the HR / Payroll / Reports
  // searchParams pages that cannot be statically prerendered) in the client
  // router cache so back/forward and tab-switch navigation reuse the cached
  // payload instead of re-rendering from the server and re-flashing loading.
  // `experimental` is the schema key in Next 15.5 (read by the server as
  // `nextConfig.experimental.staleTimes`); the top-level form is unrecognized.
  experimental: {
    staleTimes: { dynamic: 60, static: 300 },
  },
  transpilePackages: ["@skyrict/api-client", "@skyrict/auth", "@skyrict/ui"],
  // Allow tenant subdomains (acme.localhost:3000, tester.signin.localhost:3000)
  // to reach the dev server. `**` covers multi-label subdomains that the single
  // `*.localhost` wildcard misses (e.g. {slug}.signin.localhost).
  allowedDevOrigins: ["*.localhost", "**.localhost", "localhost", "127.0.0.1"],
  async headers() {
    return [
      {
        source: "/(.*)",
        headers: [
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "X-Frame-Options", value: "DENY" },
          { key: "Referrer-Policy", value: "no-referrer" },
          { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" },
          { key: "X-DNS-Prefetch-Control", value: "on" },
          {
            key: "Content-Security-Policy",
            value:
              "frame-ancestors 'none'; base-uri 'self'; " +
              // The workspace handoff is submitted via a top-level form POST
              // from the auth subdomains, so form-action must include the
              // workspace origins (dev: *.localhost:3000, prod: *.skyrict.in).
              "form-action 'self' http://*.localhost:3000 https://*.skyrict.in; " +
              "object-src 'none'",
          },
          ...(process.env.NODE_ENV === "production"
            ? [
                {
                  key: "Strict-Transport-Security",
                  value: "max-age=63072000; includeSubDomains; preload",
                },
              ]
            : []),
        ],
      },
    ];
  },
};

// Sentry wraps Next's config so the SDK can register route handlers and source
// maps. The auth token/org/project are only needed for source-map upload at
// deploy time and may be absent locally - the runtime DSN guard in
// sentry.client.config.ts / sentry.server.config.ts is what decides whether
// the SDK actually captures anything. `silent` keeps build logs quiet when
// the upload credentials are not configured.
const { withSentryConfig } = require("@sentry/nextjs/config"); // eslint-disable-line @typescript-eslint/no-require-imports -- CommonJS config file per Next.js convention

// Bundle analyzer runs only when ANALYZE=true (size baseline + CI budget gate).
// It sits OUTSIDE Sentry and chains the inner webpack hook, so an analyzer
// build still gets Sentry's instrumentation config; a regular build (ANALYZE
// unset) is byte-for-byte the same config as before this wrapper.
const withBundleAnalyzer = require("@next/bundle-analyzer")({ // eslint-disable-line @typescript-eslint/no-require-imports -- CommonJS config file per Next.js convention
  enabled: process.env.ANALYZE === "true",
  defaultSizes: "gzip",
  generateStatsFile: true,
});

module.exports = withBundleAnalyzer(
  withSentryConfig(nextConfig, {
    org: process.env.SENTRY_ORG ?? "",
    project: process.env.SENTRY_PROJECT ?? "",
    authToken: process.env.SENTRY_AUTH_TOKEN ?? "",
    silent: true,
  }),
);
