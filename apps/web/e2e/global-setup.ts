import dns from "node:dns";

import { API_BASE, marketingUrl } from "./helpers/env";

const HEALTH = `${API_BASE}/api/v1/health`;
const READY = `${API_BASE}/api/v1/ready`;

/**
 * Browsers resolve any `*.localhost` hostname to loopback natively, but Node's
 * DNS (used by the Playwright `request` fixture for `bff()` calls) does not on
 * every OS. Shimming `dns.lookup` keeps the API layer deterministic on CI.
 */
function shimLocalhostDns(): void {
  const originalLookup = dns.lookup.bind(dns);
  dns.lookup = ((hostname: string, ...rest: unknown[]) => {
    if (typeof hostname === "string" && hostname.endsWith(".localhost")) {
      const cb = rest.find(
        (
          arg,
        ): arg is (err: NodeJS.ErrnoException | null, address: string, family: number) => void =>
          typeof arg === "function",
      );
      if (cb) {
        cb(null, "127.0.0.1", 4);
        return;
      }
    }
    (originalLookup as unknown as (...args: unknown[]) => void)(hostname, ...rest);
  }) as typeof dns.lookup;
}

async function waitFor(
  url: string,
  label: string,
  timeoutMs: number,
): Promise<void> {
  const deadline = Date.now() + timeoutMs;
  let lastError = "";
  while (Date.now() < deadline) {
    try {
      const res = await fetch(url, { cache: "no-store" });
      if (res.ok) return;
      lastError = `${res.status}`;
    } catch (err) {
      lastError = err instanceof Error ? err.message : String(err);
    }
    await new Promise((resolve) => setTimeout(resolve, 1500));
  }
  throw new Error(
    `${label} did not become healthy in ${timeoutMs}ms (last: ${lastError}). ` +
      `Is the identity service running at ${API_BASE}? ` +
      `Run \`make test-e2e\` or start services manually before the suite.`,
  );
}

export default async function globalSetup(): Promise<void> {
  shimLocalhostDns();

  await waitFor(HEALTH, "identity health", 90_000);
  await waitFor(READY, "identity readiness (DB + Redis)", 90_000);

  // The web server only needs to accept connections; any HTTP status proves it
  // is up. The marketing host on localhost must be reachable for the browser.
  const deadline = Date.now() + 60_000;
  while (Date.now() < deadline) {
    try {
      await fetch(marketingUrl("/"), { cache: "no-store" });
      return;
    } catch {
      await new Promise((resolve) => setTimeout(resolve, 1500));
    }
  }
  throw new Error(
    `Web app did not respond at ${marketingUrl("/")} in 60s. ` +
      "Start it with `make dev-web` or a production build before the suite.",
  );
}
