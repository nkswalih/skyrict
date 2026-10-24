/**
 * Hard Network Interceptor for Demo Mode.
 * Ensures zero traffic can reach /api/v1/* while inside the demo workspace.
 */

export function installDemoNetworkGuard(): void {
  if (typeof window === "undefined") return;

  const originalFetch = window.fetch;
  window.fetch = async function (input: RequestInfo | URL, init?: RequestInit) {
    const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;

    if (window.location.pathname.startsWith("/demo") && url.includes("/api/v1/")) {
      console.warn(`[Demo Interceptor] Blocked network call to: ${url}`);
      return new Response(
        JSON.stringify({
          error: "Demo Mode Active",
          detail: "All operations in demo mode are client-side only.",
        }),
        {
          status: 403,
          headers: { "Content-Type": "application/json" },
        }
      );
    }
    return originalFetch.apply(this, [input, init]);
  };
}