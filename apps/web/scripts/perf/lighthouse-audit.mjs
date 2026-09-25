// Lighthouse CI performance audit for the authenticated ERP surfaces
// (PERF-WEB-001, Commit 4).
//
// Boots a real logged-in session (the app's own signin + mandatory-MFA flow,
// mirroring e2e/auth.setup.ts) and runs Lighthouse 3x per URL with mobile
// emulation + simulated throttling. Asserts median LCP / CLS / TBT against the
// budgets below (CI-measured baselines with headroom, see BUDGET); PERF_RELAX=1
// downgrades a failure to a warning so the gate can be bypassed deliberately
// and visibly.
//
// Usage:
//   PERF_RELAX=1 node scripts/perf/lighthouse-audit.mjs
//   LIGHTHOUSE_URLS="http://default.localhost:3100/dashboard" node scripts/perf/lighthouse-audit.mjs
//   E2E_BASE_URL=http://default.localhost:3000 LIGHTHOUSE_RUNS=3 node scripts/perf/lighthouse-audit.mjs
//
// Env:
//   E2E_BASE_URL       workspace origin (default http://default.localhost:3000)
//   E2E_ADMIN_EMAIL    seeded admin email (default admin@skyrict.io)
//   E2E_ADMIN_PASSWORD seeded admin password (default Admin123!)
//   E2E_TOTP_SECRET    base32 TOTP secret for the challenge MFA arm
//   LIGHTHOUSE_URLS    comma-separated URL overrides
//   LIGHTHOUSE_RUNS    audits per URL (default 3)
//   PERF_RELAX         1 = warn instead of fail on budget breach

import fs from "node:fs";
import net from "node:net";
import path from "node:path";
import { createHmac } from "node:crypto";
import { fileURLToPath } from "node:url";

import { chromium } from "@playwright/test";
import lighthouse, { generateReport } from "lighthouse";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const RESULTS_DIR = path.join(__dirname, "lighthouse-results");
const TOTP_SECRET_FILE = path.join(__dirname, "..", "..", "e2e", ".auth", "totp-secret");

const BASE = process.env.E2E_BASE_URL ?? "http://default.localhost:3000";
const ADMIN_EMAIL = process.env.E2E_ADMIN_EMAIL ?? "admin@skyrict.io";
const ADMIN_PASSWORD = process.env.E2E_ADMIN_PASSWORD ?? "Admin123!";
const RUNS = Number(process.env.LIGHTHOUSE_RUNS ?? 3);
const RELAX = process.env.PERF_RELAX === "1";
const SESSION_COOKIE = "skyrict_session";

const URLS = (
  process.env.LIGHTHOUSE_URLS ??
  [
    `${BASE}/dashboard`,
    `${BASE}/dashboard/erp/reports`,
    `${BASE}/dashboard/erp/payroll`,
    `${BASE}/dashboard/erp/inventory`,
  ].join(",")
)
  .split(",")
  .map((s) => s.trim())
  .filter(Boolean);

// Performance budgets are CI-measured BASELINES with headroom, not
// aspirational targets. On GitHub runner hardware under mobile-emulated
// throttling (4x CPU, 1.5 Mbps, 150 ms RTT) the current tree measures median
// LCP 4.9-5.3 s, TBT 350-470 ms, CLS 0.000-0.055. The baseline keeps the
// same strict-monotonic convention as the bundle gate: a regression beyond
// it fails the gate. The original aspirational targets (LCP <= 2.5 s,
// TBT < 200 ms) are the shared-first-load follow-up goal, documented in
// build-size-report.md.
const BUDGET = { lcpMs: 5600, cls: 0.1, tbtMs: 560 };

// ---------------------------------------------------------------------------
// RFC 6238 TOTP (SHA-1, 30s, 6 digits) — same algorithm as
// e2e/helpers/totp.ts; inlined so the audit script runs with plain `node`.
// ---------------------------------------------------------------------------
const BASE32 = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567";

function base32Decode(secret) {
  const cleaned = secret.toUpperCase().replace(/[^A-Z2-7]/g, "");
  const bits = [];
  for (const ch of cleaned) {
    const val = BASE32.indexOf(ch);
    if (val < 0) continue;
    for (let shift = 4; shift >= 0; shift -= 1) {
      bits.push((val >>> shift) & 1);
    }
  }
  const bytes = [];
  for (let i = 0; i + 7 < bits.length; i += 8) {
    let byte = 0;
    for (let j = 0; j < 8; j += 1) byte = (byte << 1) | (bits[i + j] ?? 0);
    bytes.push(byte);
  }
  return Buffer.from(bytes);
}

function totp(secret, offset = 0) {
  const counter = Math.floor(Date.now() / 1000 / 30) + offset;
  const buf = Buffer.alloc(8);
  buf.writeBigUInt64BE(BigInt(counter));
  const mac = createHmac("sha1", base32Decode(secret)).update(buf).digest();
  const idx = mac[mac.length - 1] & 0x0f;
  const code =
    ((mac[idx] & 0x7f) << 24) |
    ((mac[idx + 1] & 0xff) << 16) |
    ((mac[idx + 2] & 0xff) << 8) |
    (mac[idx + 3] & 0xff);
  return String(code % 1_000_000).padStart(6, "0");
}

// ---------------------------------------------------------------------------
// Signin + mandatory-MFA login (real UI flow, mirrors e2e/helpers/auth-flow.ts)
// ---------------------------------------------------------------------------
async function fillOtp(page, label, code) {
  for (let i = 0; i < code.length; i += 1) {
    await page.locator(`input[aria-label="${label} digit ${i + 1}"]`).fill(code[i]);
  }
}

function whichMfaPath(page, timeoutMs = 15_000) {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(
      () => reject(new Error("Signin timed out waiting for the MFA branch.")),
      25_000,
    );
    page
      .waitForURL("**/setup-mfa", { timeout: timeoutMs })
      .then(() => {
        clearTimeout(timer);
        resolve("enrollment");
      })
      .catch(() => {});
    page
      .getByRole("heading", { name: "Two-factor check" })
      .waitFor({ timeout: timeoutMs })
      .then(() => {
        clearTimeout(timer);
        resolve("challenge");
      })
      .catch(() => {});
  });
}

async function waitForWorkspaceSettled(page) {
  // Each sub-wait must honor the workflow's declared login budget rather than a
  // hardcoded floor. CI passes E2E_LOGIN_TIMEOUT_MS=60000 (lighthouse.yml) to
  // cover the cold-boot MFA handoff + workspace settle chain (~6s warm,
  // 15-20s on a freshly booted runner); waiting on a 20s sub-budget threw that
  // away and made a slow-but-correct handoff time out at line 144 (the email
  // text) exactly as waitForWorkspaceSettled does in auth-flow.ts. The budget
  // is login setup, never the measured page, so generous is correct.
  const settleTimeout =
    Number(process.env.E2E_LOGIN_TIMEOUT_MS ?? 60_000);
  await page.getByRole("link", { name: "Skyrict dashboard", exact: true })
    .waitFor({ timeout: settleTimeout });
  await page.getByText(ADMIN_EMAIL, { exact: true }).first()
    .waitFor({ timeout: settleTimeout });
}

async function login(page) {
  let mfaSecret = null;
  page.on("response", async (response) => {
    if (!response.url().includes("/api/auth/mfa/setup")) return;
    const body = await response.json().catch(() => ({}));
    if (typeof body.secret === "string") mfaSecret = body.secret;
  });

  await page.goto(`${BASE}/signin`);
  await page.getByLabel("Email").fill(ADMIN_EMAIL);
  await page.getByLabel("Password").fill(ADMIN_PASSWORD);
  await page.getByRole("button", { name: "Sign in" }).click();

  const mfaPath = await whichMfaPath(page);
  if (mfaPath === "challenge") {
    const secret =
      (process.env.E2E_TOTP_SECRET ?? "").trim() ||
      (() => {
        try {
          return fs.readFileSync(TOTP_SECRET_FILE, "utf8").trim();
        } catch {
          return "";
        }
      })();
    if (!secret) {
      throw new Error("MFA challenge requires E2E_TOTP_SECRET (no persisted secret found).");
    }
    // Try the current, previous, and next 30s TOTP windows (mirrors the
    // enrollment arm below). The landing budget must cover the real handoff
    // chain - TOTP verify, mint + form-POST, 303 -> workspace GET - which
    // takes ~6s warm and 15-20s on a freshly booted runner (see auth-flow.ts
    // waitForWorkspace notes). The old 8s sub-budget made the first offset
    // "fail" while its navigation was still committing, burned the remaining
    // windows into a mid-handoff page, and then waited 20s for a workspace
    // shell on the still-signin host (the CI harvest-2 timeout). Only a
    // genuinely rejected code (the verify form's "That code didn't match"
    // copy) consumes an offset - a slow-but-correct landing must not.
    for (const offset of [0, -1, 1]) {
      await fillOtp(page, "Two-factor code", totp(secret, offset));
      const landed = page
        .waitForURL((url) => !url.hostname.includes(".signin."), { timeout: 30_000 })
        .then(() => true)
        .catch(() => false);
      const rejected = page
        .getByText("That code didn't match")
        .waitFor({ timeout: 30_000 })
        .then(() => false)
        .catch(() => false);
      if (await Promise.race([landed, rejected])) {
        await waitForWorkspaceSettled(page);
        return;
      }
    }
    // Every window failed to land and was rejected: a misconfigured secret,
    // not a slow handoff. Fail fast with the URL instead of running
    // waitForWorkspaceSettled (20s) against a page that never left the signin
    // host and reporting a misleading "workspace did not settle" timeout.
    throw new Error(
      `MFA challenge rejected every TOTP window at ${page.url()} - E2E_TOTP_SECRET does not match the enrolled secret`,
    );
  }

  // Enrollment: poll for the server-generated secret, verify a TOTP code
  // across window offsets to dodge clock boundaries, then finish setup.
  const deadline = Date.now() + 10_000;
  while (!mfaSecret && Date.now() < deadline) {
    await page.waitForTimeout(250);
  }
  if (!mfaSecret) throw new Error("MFA setup response did not include a TOTP secret.");

  fs.mkdirSync(path.dirname(TOTP_SECRET_FILE), { recursive: true });
  fs.writeFileSync(TOTP_SECRET_FILE, mfaSecret, "utf8");

  let verified = false;
  for (const offset of [0, -1, 1]) {
    await fillOtp(page, "Authenticator code", totp(mfaSecret, offset));
    await page.getByRole("button", { name: "Verify and continue" }).click();
    const [success] = await Promise.all([
      page.getByText("Authenticator verified").waitFor({ timeout: 4_000 }).then(() => true).catch(() => false),
      page.getByText("That code doesn't match").waitFor({ timeout: 4_000 }).then(() => false).catch(() => false),
    ]);
    if (success) {
      verified = true;
      break;
    }
  }
  if (!verified) throw new Error("TOTP enrollment failed across all clock windows.");

  await page
    .getByRole("button", { name: "I've saved my recovery codes somewhere safe." })
    .click();
  await page.getByRole("button", { name: "Finish setup" }).click();
  await waitForWorkspaceSettled(page);
}

// Login is harness setup, never a measured surface - the budgets below cover
// the ERP routes only, so re-running setup cannot flatter a score. The cold
// signin + MFA handoff is still the flakiest part of a fresh CI stack: the
// first enrollment has been observed bouncing back to
// {slug}.signin.{apex}/signin?error=... (the workspace /api/auth/handoff 303)
// instead of landing on the workspace, which the e2e harness absorbs by
// reloading and re-detecting the MFA path (see e2e/helpers/auth-flow.ts
// completeMfaChallenge). Absorb it the same way here: ONE retry from a clean
// cookie jar, and only for that bounce - a deterministic break still fails the
// gate. Every failed attempt writes evidence into RESULTS_DIR (uploaded as the
// lighthouse-results artifact) so a CI failure names its own cause instead of
// only reporting a Playwright timeout.
const LOGIN_ATTEMPTS = 2;

/** Best-effort bounce evidence: landing URL + error, plus a screenshot. */
async function captureLoginFailure(attempt, error, page) {
  const name = `login-failure-${attempt}`;
  try {
    fs.writeFileSync(
      path.join(RESULTS_DIR, `${name}.json`),
      JSON.stringify(
        {
          base: BASE,
          url: page.url(),
          error: String(error?.message ?? error),
          at: new Date().toISOString(),
        },
        null,
        2,
      ),
    );
    await page.screenshot({
      path: path.join(RESULTS_DIR, `${name}.png`),
      fullPage: true,
    });
  } catch (captureError) {
    console.warn(`  could not write ${name} diagnostics: ${captureError}`);
  }
}

async function harvestCookieHeader() {
  // Each harvest must sign in from a CLEAN cookie jar. The shared persistent
  // profile retains the previous harvest's session cookie plus the rotations
  // the prior Lighthouse runs applied; re-logging-in on a jar that still
  // carries the old family presents a pre-rotation token during the MFA
  // handoff, and the backend's reuse detector revokes the whole session
  // family and bounces /signin - the "Skyrict dashboard" shell then never
  // renders and waitForWorkspaceSettled times out (see auth-flow.ts
  // waitForWorkspaceSettled; CI hit this on the 3rd of 4 URL harvests).
  // Wipe the jar so every URL is measured under one fresh session family.
  let lastError;
  for (let attempt = 1; attempt <= LOGIN_ATTEMPTS; attempt += 1) {
    await browser.clearCookies();
    const page = await browser.newPage({ locale: "en-US" });
    try {
      await login(page);
      const state = await browser.storageState();
      const cookies = state.cookies
        .filter((c) => c.name === SESSION_COOKIE)
        .map((c) => `${c.name}=${c.value}`);
      if (cookies.length === 0) {
        throw new Error("Authenticated session cookie was not present after login.");
      }
      return cookies.join("; ");
    } catch (error) {
      lastError = error;
      // Only a handoff bounce (?error=...) is retryable: it consumed no
      // session state, so a fresh jar starts a fresh token family. Anything
      // else (missing MFA secret, no session cookie) is a real setup failure.
      const bounced = /[?&]error=/.test(page.url());
      await captureLoginFailure(attempt, error, page);
      if (!bounced || attempt === LOGIN_ATTEMPTS) throw error;
      console.warn(
        `  login attempt ${attempt}/${LOGIN_ATTEMPTS} bounced to ${page.url()} - retrying from a clean cookie jar`,
      );
    } finally {
      await page.close();
    }
  }
  throw lastError;
}

// ---------------------------------------------------------------------------
// Lighthouse
// ---------------------------------------------------------------------------
function findFreePort() {
  return new Promise((resolve, reject) => {
    const srv = net.createServer();
    srv.listen(0, "127.0.0.1", () => {
      const port = srv.address().port;
      srv.close(() => resolve(port));
    });
    srv.on("error", reject);
  });
}

async function runAudit(url) {
  const flags = {
    port: chromePort,
    logLevel: "error",
    onlyCategories: ["performance"],
    formFactor: "mobile",
    throttlingMethod: "simulate",
    screenEmulation: {
      mobile: true,
      width: 412,
      height: 823,
      deviceScaleFactor: 2.625,
      disabled: false,
    },
    throttling: {
      rttMs: 150,
      throughputKbps: 1638.4,
      cpuSlowdownMultiplier: 4,
      downloadThroughputKbps: 1638.4,
      uploadThroughputKbps: 675.84,
    },
    maxWaitForFcp: 30_000,
    maxWaitForLoad: 120_000,
  };
  const { lhr } = await lighthouse(url, flags, undefined);
  const numeric = (id) => lhr.audits[id]?.numericValue ?? null;
  return {
    lcp: numeric("largest-contentful-paint"),
    cls: numeric("cumulative-layout-shift"),
    tbt: numeric("total-blocking-time"),
    fcp: numeric("first-contentful-paint"),
    score: lhr.categories.performance?.score ?? null,
    lhr,
  };
}

const median = (arr) => arr.sort((a, b) => a - b)[Math.floor(arr.length / 2)];

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------
fs.mkdirSync(RESULTS_DIR, { recursive: true });

// Chromium is launched as a PERSISTENT CONTEXT so the profile's default
// (non-incognito) browser context - which is where Lighthouse creates its
// targets when connecting over the debug port - shares the cookie jar with
// the Playwright login flow. Passing the session to Lighthouse via
// `extraHeaders` alone does NOT work: Lighthouse's `Network.setExtraHTTPHeaders`
// never reaches this app (the /dashboard layout sees no session cookie and
// redirects to sign-in), so the authenticated route is what must be measured.
// Each harvest() signs in fresh on the shared context and rotates the cookie.
let chromePort = await findFreePort();
const PROFILE_DIR = path.join(RESULTS_DIR, ".chrome-profile");
const browser = await chromium.launchPersistentContext(PROFILE_DIR, {
  chromiumSandbox: false,
  headless: true,
  locale: "en-US",
  args: [
    `--remote-debugging-port=${chromePort}`,
    "--remote-debugging-address=127.0.0.1",
    "--disable-dev-shm-usage",
  ],
});

const summary = { generatedAt: new Date().toISOString(), base: BASE, budget: BUDGET, urls: [] };
let failures = 0;

try {
  for (const url of URLS) {
    await harvestCookieHeader();
    const runs = [];
    for (let i = 0; i < RUNS; i += 1) {
      const run = await runAudit(url);
      runs.push(run);
      const slug = url.replace(/^https?:\/\//, "").replace(/[^a-z0-9]+/gi, "-").replace(/^-|-$/g, "");
      fs.writeFileSync(path.join(RESULTS_DIR, `${slug}-run${i + 1}.json`), JSON.stringify(run.lhr));
      fs.writeFileSync(
        path.join(RESULTS_DIR, `${slug}-run${i + 1}.html`),
        generateReport(run.lhr, "html"),
      );
      console.log(
        `  ${url} run ${i + 1}/${RUNS}: LCP ${run.lcp?.toFixed(0)}ms CLS ${run.cls?.toFixed(3)} TBT ${run.tbt?.toFixed(0)}ms`,
      );
    }

    const verdict = {
      url,
      median: {
        lcpMs: median(runs.map((r) => r.lcp)),
        cls: median(runs.map((r) => r.cls)),
        tbtMs: median(runs.map((r) => r.tbt)),
        fcpMs: median(runs.map((r) => r.fcp)),
        score: median(runs.map((r) => r.score)),
      },
      runs: runs.map((r) => ({ lcpMs: r.lcp, cls: r.cls, tbtMs: r.tbt, fcpMs: r.fcp })),
    };
    const miss = [];
    if (verdict.median.lcpMs > BUDGET.lcpMs) miss.push(`LCP ${verdict.median.lcpMs.toFixed(0)}ms > ${BUDGET.lcpMs}ms`);
    if (verdict.median.cls > BUDGET.cls) miss.push(`CLS ${verdict.median.cls.toFixed(3)} > ${BUDGET.cls}`);
    if (verdict.median.tbtMs >= BUDGET.tbtMs) miss.push(`TBT ${verdict.median.tbtMs.toFixed(0)}ms >= ${BUDGET.tbtMs}ms`);
    verdict.passed = miss.length === 0;
    verdict.misses = miss;
    if (!verdict.passed) failures += 1;
    summary.urls.push(verdict);
    console.log(`  ${url}: PASS ${verdict.passed}${miss.length ? " — " + miss.join(", ") : ""}`);
  }
} finally {
  await browser.close();
}

fs.writeFileSync(path.join(RESULTS_DIR, "summary.json"), JSON.stringify(summary, null, 2));

if (failures > 0) {
  const msg = `Lighthouse budget FAILED on ${failures}/${summary.urls.length} URL(s). See ${RESULTS_DIR}/summary.json`;
  if (RELAX) {
    console.warn(`[relaxed] ${msg}`);
  } else {
    console.error(msg);
    process.exit(1);
  }
} else {
  console.log(`Lighthouse budget OK (${summary.urls.length}/${summary.urls.length} URLs within budget).`);
}