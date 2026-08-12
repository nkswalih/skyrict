/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  transpilePackages: ["@skyrict/api-client", "@skyrict/auth", "@skyrict/ui"],
  // Allow tenant subdomains (acme.localhost:PORT, tester.signin.localhost:PORT)
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
              // workspace origins. The workspace port matches the dev server's
              // own port (3000 by default, auto-incremented when taken), so the
              // local wildcard is port-agnostic (dev: *.localhost, prod:
              // *.skyrict.com).
              "form-action 'self' http://*.localhost:* https://*.skyrict.com; " +
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

module.exports = nextConfig;
