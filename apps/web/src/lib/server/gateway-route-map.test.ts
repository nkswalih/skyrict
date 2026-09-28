import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

/**
 * Drift guard for the gateway's route map.
 *
 * There are two implementations of "which backend serves /api/v1/<segment>":
 *
 *   1. the BFF, in src/app/api/v1/[...path]/route.ts, used for same-origin
 *      browser traffic;
 *   2. the nginx gateway, in infra/nginx/gateway.conf.template, used for the
 *      public api.skyrict.in origin.
 *
 * They must agree. Azure Container Apps ingress is host-based and cannot route
 * on path, so the nginx map is the only thing that can put all three services
 * behind one hostname - and it is a hand-maintained duplicate of a list that
 * already exists in TypeScript.
 *
 * The failure mode this guards is quiet. A segment added to the BFF but not to
 * nginx sends real traffic to identity, which answers a well-formed RFC 7807
 * 404. Nothing crashes, no probe fails, and the report reads like a client bug
 * in a feature that "does not work yet". This test is the only thing standing
 * between that edit and production.
 */

// This file lives at apps/web/src/lib/server/, so five levels up is the repo
// root - the BFF is under it and so is the nginx template.
const REPO_ROOT = fileURLToPath(new URL("../../../../../", import.meta.url));

const BFF_ROUTE = `${REPO_ROOT}apps/web/src/app/api/v1/[...path]/route.ts`;
const NGINX_TEMPLATE = `${REPO_ROOT}infra/nginx/gateway.conf.template`;

/**
 * Pull the core-segment list out of the BFF.
 *
 * The list is inline in a `.includes(` call rather than exported, so this parses
 * it. If the source shape ever changes, the extraction returns an empty list and
 * the assertions below fail loudly rather than comparing two empty lists and
 * reporting success - which is the failure mode a naive "both empty, therefore
 * equal" check would give.
 */
function bffCoreSegments(): string[] {
  const source = readFileSync(BFF_ROUTE, "utf8");
  // The list is inline and reads `const target = ["crm", ...].includes(segment)`
  // - the array precedes the call, not the other way round.
  const call = source.match(/\[\s*([^\]]*?)\s*\]\s*\.includes\(/);
  expect(call, "could not find the [...].includes(segment) core list in route.ts").not.toBeNull();

  const segments = [...(call?.[1] ?? "").matchAll(/"([^"]+)"/g)].map((m) => m[1]);
  expect(segments.length, "extracted zero segments from route.ts - has the shape changed?")
    .toBeGreaterThan(5);
  return segments;
}

/** Pull the segment -> backend keys out of the nginx target map. */
function nginxRouteMap(): { core: string[]; defaultTarget: string } {
  const template = readFileSync(NGINX_TEMPLATE, "utf8");
  const block = template.match(
    /map\s+\$skyrict_api_segment\s+\$skyrict_api_backend\s*\{([^}]*)\}/,
  );
  expect(block, "could not find the $skyrict_api_segment map in gateway.conf.template").not.toBeNull();

  const body = block?.[1] ?? "";
  const core: string[] = [];
  let defaultTarget = "";

  for (const raw of body.split("\n")) {
    const line = raw.trim();
    if (!line || line.startsWith("#")) continue;
    // A map entry is "<key> <value>;" - keys are bare words, values are URLs.
    const entry = line.match(/^(\S+)\s+(\S+);$/);
    if (!entry) continue;
    const [, key, value] = entry;
    if (key === "default") {
      defaultTarget = value;
    } else {
      core.push(key);
    }
  }

  expect(core.length, "extracted zero segment keys from the nginx map").toBeGreaterThan(5);
  expect(defaultTarget, "the nginx map has no default target").not.toBe("");
  return { core, defaultTarget };
}

describe("gateway route map", () => {
  const nginx = nginxRouteMap();
  const bff = bffCoreSegments();

  it("routes exactly the same segments to core as the BFF does", () => {
    // Compare as sets: nginx map order is a readability choice, the BFF array
    // order is arbitrary, and neither order is meaningful to a reader.
    const fromNginx = new Set(nginx.core);
    const fromBff = new Set(bff);

    const missingInNginx = bff.filter((s) => !fromNginx.has(s));
    const extraInNginx = nginx.core.filter((s) => !fromBff.has(s));

    expect(
      { missingInNginx, extraInNginx },
      "the nginx gateway and the BFF disagree about which segments are core's. "
        + "A segment present in only one of them is silently misrouted: core answers "
        + "a 404 for identity traffic, and identity answers a 404 for core traffic.",
    ).toEqual({ missingInNginx: [], extraInNginx: [] });
  });

  it("defaults unknown segments to identity, like the BFF ternary", () => {
    // route.ts:97-101 is `CORE.includes(segment) ? "core" : "identity"`, so
    // anything not in the core list must fall through to identity.
    expect(nginx.defaultTarget).toBe("__IDENTITY_BACKEND__");
  });

  it("sends every /download path to core regardless of segment", () => {
    // route.ts:69-70 special-cases /download before the segment lookup, because
    // those are byte streams out of the document/report store. The gateway
    // implements this by rewriting the SEGMENT to "documents" in
    // $skyrict_api_segment; if that override is dropped, downloads under
    // identity-owned segments silently start 404ing.
    const template = readFileSync(NGINX_TEMPLATE, "utf8");
    const segmentMap = template.match(/map\s+\$request_uri\s+\$skyrict_api_segment\s*\{([^}]*)\}/);
    expect(segmentMap, "could not find the $request_uri segment map").not.toBeNull();

    const downloadOverride = (segmentMap?.[1] ?? "").match(
      /"~[^"]*\/download[^"]*"\s+(\S+);/,
    );
    expect(
      downloadOverride?.[1],
      "the segment map has no /download override, so the gateway lost route.ts:69-70",
    ).toBe("documents");
  });

  it("forwards the path unchanged, including the /api/v1 prefix", () => {
    // The backends mount their routers at /api/v1 (identity serves
    // /api/v1/health, core serves /api/v1/crm/...). A `rewrite` that strips the
    // prefix in the gateway would 404 every real request while all the routing
    // assertions above still passed.
    const template = readFileSync(NGINX_TEMPLATE, "utf8");
    const apiLocation = template.match(/location \/api\/v1\/ \{([\s\S]*?)\n {8}\}/);
    expect(apiLocation, "could not find the location /api/v1/ block").not.toBeNull();

    const body = apiLocation?.[1] ?? "";
    expect(body).not.toMatch(/^\s*rewrite\b/m);
    expect(body).toMatch(/proxy_pass\s+\$skyrict_api_backend\$uri\$is_args\$args;/);
  });
});
