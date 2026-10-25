/**
 * Demo network guard.
 *
 * The demo is a client-only walkthrough: every read and write comes from the
 * seeded `localStorage` snapshot. As defence-in-depth (and to make accidental
 * regressions loud) this module blocks same-origin `/api/*` traffic while the
 * visitor is inside `/demo`, covering `fetch`, `XMLHttpRequest` and
 * `navigator.sendBeacon`. It installs once and is intentionally silent — the
 * old version logged a console warning for every blocked call, which showed up
 * as noise in the browser console.
 */

const GUARD_FLAG = "__skyrictDemoNetworkGuard";
const BLOCKED_BODY = JSON.stringify({
  error: "Demo mode active",
  detail: "All operations in the demo are client-side only.",
});

function isDemoContext(): boolean {
  return (
    typeof window !== "undefined" &&
    window.location.pathname.startsWith("/demo")
  );
}

function requestUrl(input: string | URL | Request): string {
  if (typeof input === "string") return input;
  if (input instanceof URL) return input.href;
  return input.url;
}

/** True only for same-origin `/api/*` calls while the demo is active. */
function shouldBlock(input: string | URL | Request): boolean {
  if (!isDemoContext()) return false;
  try {
    const url = new URL(requestUrl(input), window.location.href);
    return (
      url.origin === window.location.origin &&
      (url.pathname === "/api" || url.pathname.startsWith("/api/"))
    );
  } catch {
    return false;
  }
}

function blockedResponse(): Response {
  return new Response(BLOCKED_BODY, {
    status: 403,
    headers: { "Content-Type": "application/json" },
  });
}

export function installDemoNetworkGuard(): void {
  if (typeof window === "undefined") return;
  const flaggedWindow = window as Window & { [GUARD_FLAG]?: boolean };
  if (flaggedWindow[GUARD_FLAG]) return;
  flaggedWindow[GUARD_FLAG] = true;

  const originalFetch = window.fetch.bind(window);
  window.fetch = async function demoFetch(
    input: RequestInfo | URL,
    init?: RequestInit,
  ): Promise<Response> {
    if (shouldBlock(input as string | URL | Request)) return blockedResponse();
    return originalFetch(input, init);
  };

  const OriginalXHR = window.XMLHttpRequest;
  class DemoGuardedXHR extends OriginalXHR {
    private demoBlocked = false;

    open(
      method: string,
      url: string | URL,
      async: boolean = true,
      username?: string | null,
      password?: string | null,
    ): void {
      this.demoBlocked = shouldBlock(url);
      if (this.demoBlocked) {
        // Keep the instance in a valid state without touching the network.
        super.open("GET", "about:blank", async);
        return;
      }
      super.open(method, url, async, username ?? undefined, password ?? undefined);
    }

    send(body?: Document | XMLHttpRequestBodyInit | null): void {
      if (!this.demoBlocked) {
        super.send(body);
        return;
      }
      for (const [key, value] of [
        ["readyState", 4],
        ["status", 403],
        ["statusText", "Forbidden"],
        ["responseText", BLOCKED_BODY],
        ["response", BLOCKED_BODY],
      ] as const) {
        try {
          Object.defineProperty(this, key, {
            configurable: true,
            value,
          });
        } catch {
          // Read-only in some engines; the load events below still settle it.
        }
      }
      this.dispatchEvent(new Event("readystatechange"));
      this.dispatchEvent(new Event("load"));
      this.dispatchEvent(new Event("loadend"));
    }
  }
  window.XMLHttpRequest = DemoGuardedXHR;

  if (typeof navigator.sendBeacon === "function") {
    const originalSendBeacon = navigator.sendBeacon.bind(navigator);
    navigator.sendBeacon = ((url: string | URL, data?: BodyInit | null) => {
      if (shouldBlock(url)) return false;
      return originalSendBeacon(url, data);
    }) as typeof navigator.sendBeacon;
  }
}
