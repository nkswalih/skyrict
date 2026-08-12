/**
 * Auth API seam.
 *
 * Every call goes through the same-origin BFF route handlers (/api/auth/*),
 * which enforce the Origin/Referer CSRF gate, resolve the tenant slug from
 * the Host header, and proxy to the identity service — the browser never
 * talks to the identity service directly. Login/MFA set the httpOnly
 * refresh-token cookie and return the access token in the body; the browser
 * keeps it in memory only.
 */

import { ApiError } from "@/lib/api/http";
import { getAccessToken, setAccessToken } from "@/lib/auth/session-store";

export { ApiError };

export interface AuthUser {
  id: string;
  email: string;
  fullName: string;
  isActive: boolean;
  isVerified: boolean;
  mfaEnabled: boolean;
  createdAt: string;
}

export type LoginResult =
  | { status: "authenticated"; accessToken: string; expiresIn: number; user: AuthUser }
  | { status: "mfa_setup"; accessToken: string; expiresIn: number; user: AuthUser }
  | { status: "mfa_challenge"; mfaToken: string; user: AuthUser };

export type VerifyMfaResult =
  | { status: "ok"; accessToken: string; expiresIn: number; user: AuthUser }
  | { status: "invalid" };

/** POST to a same-origin BFF route; the JSON body is the response payload. */
async function bffPost<T>(path: string, body: unknown): Promise<T> {
  let res: Response;
  try {
    res = await fetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      cache: "no-store",
    });
  } catch {
    throw new ApiError(0, "Network error — check your connection and try again.");
  }

  const payload = (await res.json().catch(() => ({}))) as T & { error?: string };
  if (!res.ok) {
    throw new ApiError(
      res.status,
      payload.error ?? "Request failed. Please try again.",
    );
  }
  return payload as T;
}

// ---------------------------------------------------------------------------
// Sign in
// ---------------------------------------------------------------------------

interface BffLoginResponse {
  status: "authenticated" | "mfa_setup" | "mfa_challenge";
  accessToken?: string | null;
  expiresIn?: number;
  mfaToken?: string | null;
  user?: AuthUser | null;
  error?: string;
}

export async function loginEmailPassword(input: {
  email: string;
  password: string;
}): Promise<LoginResult> {
  let response: Response;
  try {
    response = await fetch("/api/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(input),
    });
  } catch {
    throw new ApiError(0, "Network error — check your connection and try again.");
  }

  const payload = (await response.json().catch(() => ({}))) as BffLoginResponse;
  if (!response.ok) {
    throw new ApiError(
      response.status,
      payload.error ?? "Unable to sign in. Check your credentials and try again.",
    );
  }

  if (payload.status === "mfa_challenge") {
    setAccessToken(null);
    if (!payload.mfaToken || !payload.user) {
      throw new ApiError(502, "Unexpected login response.");
    }
    return {
      status: "mfa_challenge",
      mfaToken: payload.mfaToken,
      user: payload.user,
    };
  }

  if (!payload.accessToken || !payload.user) {
    throw new ApiError(502, "Unexpected login response.");
  }
  setAccessToken(payload.accessToken);
  return {
    status: payload.status === "mfa_setup" ? "mfa_setup" : "authenticated",
    accessToken: payload.accessToken,
    expiresIn: payload.expiresIn ?? 0,
    user: payload.user,
  };
}

interface BffMfaVerifyResponse {
  status: "authenticated";
  accessToken?: string | null;
  expiresIn?: number;
  user?: AuthUser | null;
  error?: string;
}

export async function verifyMfa(input: {
  code: string;
  mfaToken: string;
}): Promise<VerifyMfaResult> {
  let response: Response;
  try {
    response = await fetch("/api/auth/mfa/verify", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ mfa_token: input.mfaToken, code: input.code }),
    });
  } catch {
    throw new ApiError(0, "Network error — check your connection and try again.");
  }

  const payload = (await response.json().catch(() => ({}))) as BffMfaVerifyResponse;
  if (response.status === 401 || response.status === 403) {
    return { status: "invalid" };
  }
  if (!response.ok) {
    throw new ApiError(
      response.status,
      payload.error ?? "Unable to verify the code.",
    );
  }
  if (!payload.accessToken || !payload.user) {
    throw new ApiError(502, "Unexpected verification response.");
  }
  setAccessToken(payload.accessToken);
  return {
    status: "ok",
    accessToken: payload.accessToken,
    expiresIn: payload.expiresIn ?? 0,
    user: payload.user,
  };
}

// ---------------------------------------------------------------------------
// Onboarding wizard (through the BFF)
// ---------------------------------------------------------------------------

export interface RiskAssessment {
  requiresCaptcha: boolean;
  requiresChallenge: boolean;
  signals: string[];
}

export async function assessRisk(): Promise<RiskAssessment> {
  return {
    requiresCaptcha: true,
    requiresChallenge: false,
    signals: [],
  };
}

export async function solveCaptcha(): Promise<{ status: "ok" }> {
  return { status: "ok" };
}

export async function signupStart(input: {
  email: string;
  turnstileToken?: string;
}): Promise<{ status: "ok" }> {
  return bffPost<{ status: "ok" }>("/api/auth/start", {
    email: input.email,
    turnstileToken: input.turnstileToken,
  });
}

export async function checkEmailAvailability(input: {
  email: string;
}): Promise<{ available: boolean }> {
  return bffPost<{ available: boolean }>("/api/auth/check/email", {
    email: input.email,
  });
}

export async function requestVerificationCode(input: {
  email: string;
}): Promise<{
  status: "ok";
  resendIn: number;
  code?: string | null;
}> {
  return bffPost<{ status: "ok"; resendIn: number; code?: string | null }>(
    "/api/auth/code/send",
    { email: input.email },
  );
}

export type VerifyEmailCodeResult =
  | { status: "ok"; verificationToken: string }
  | { status: "invalid" }
  | { status: "expired" };

export async function verifyEmailCode(input: {
  email: string;
  code: string;
}): Promise<VerifyEmailCodeResult> {
  const data = await bffPost<{
    status: "ok" | "invalid" | "expired";
    verificationToken?: string | null;
  }>("/api/auth/code/verify", { email: input.email, code: input.code });
  if (data.status === "ok" && data.verificationToken) {
    return { status: "ok", verificationToken: data.verificationToken };
  }
  if (data.status === "expired") {
    return { status: "expired" };
  }
  return { status: "invalid" };
}

export async function getCaptcha(): Promise<{ captchaId: string; image: string }> {
  let res: Response;
  try {
    res = await fetch("/api/auth/captcha", { cache: "no-store" });
  } catch {
    throw new ApiError(0, "Network error — check your connection and try again.");
  }

  const payload = (await res.json().catch(() => ({}))) as {
    captchaId?: string;
    image?: string;
    error?: string;
  };
  if (!res.ok) {
    throw new ApiError(res.status, payload.error ?? "Could not load the security code.");
  }
  if (!payload.captchaId || !payload.image) {
    throw new ApiError(502, "Unexpected captcha response.");
  }
  return { captchaId: payload.captchaId, image: payload.image };
}

export async function completeSecurityStep(input: {
  email: string;
  verificationToken: string;
  password: string;
  captchaId: string;
  captchaAnswer: string;
}): Promise<{ status: "ok" }> {
  return bffPost<{ status: "ok" }>("/api/auth/password", {
    email: input.email,
    verificationToken: input.verificationToken,
    password: input.password,
    captchaId: input.captchaId,
    captchaAnswer: input.captchaAnswer,
  });
}

export async function checkWorkspaceSlug(input: {
  slug: string;
}): Promise<{ available: boolean }> {
  return bffPost<{ available: boolean }>("/api/auth/check/slug", {
    slug: input.slug,
  });
}

export interface CreateOrganizationInput {
  email: string;
  verificationToken: string;
  planId: string;
  companyName: string;
  industry: string;
  workspaceSlug: string;
  ownerFullName: string;
  phoneCountry: string;
  phoneNumber: string;
  address: {
    country: string;
    addressLine1: string;
    addressLine2?: string;
    city: string;
    state: string;
    postalCode: string;
  };
}

export interface CreateOrganizationResult {
  status: "ok";
  mfaRequired: boolean;
  tenantId: string;
  tenantSlug: string;
}

export async function createOrganization(
  input: CreateOrganizationInput,
): Promise<CreateOrganizationResult> {
  return bffPost<CreateOrganizationResult>("/api/auth/org", {
    email: input.email,
    verificationToken: input.verificationToken,
    planId: input.planId,
    companyName: input.companyName,
    industry: input.industry,
    workspaceSlug: input.workspaceSlug,
    ownerFullName: input.ownerFullName,
    phoneCountry: input.phoneCountry,
    phoneNumber: input.phoneNumber,
    address: input.address,
  });
}

// ---------------------------------------------------------------------------
// Mandatory MFA enrollment (authenticated, through the BFF)
// ---------------------------------------------------------------------------

export interface MfaSetup {
  secret: string;
  otpauthUri: string;
  backupCodes: string[];
}

function authHeaders(): Headers {
  const headers = new Headers({ "Content-Type": "application/json" });
  const token = getAccessToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  return headers;
}

export async function setupMfa(): Promise<MfaSetup> {
  let res: Response;
  try {
    res = await fetch("/api/auth/mfa/setup", {
      method: "POST",
      headers: authHeaders(),
      cache: "no-store",
    });
  } catch {
    throw new ApiError(0, "Network error — check your connection and try again.");
  }

  const payload = (await res.json().catch(() => ({}))) as {
    secret?: string;
    provisioning_uri?: string;
    backup_codes?: string[];
    error?: string;
  };
  if (!res.ok) {
    throw new ApiError(res.status, payload.error ?? "Could not start MFA setup.");
  }

  return {
    secret: payload.secret ?? "",
    otpauthUri: payload.provisioning_uri ?? "",
    backupCodes: Array.isArray(payload.backup_codes) ? payload.backup_codes : [],
  };
}

export async function regenerateBackupCodes(): Promise<{ backupCodes: string[] }> {
  let res: Response;
  try {
    res = await fetch("/api/auth/mfa/backup-codes", {
      method: "POST",
      headers: authHeaders(),
      cache: "no-store",
    });
  } catch {
    throw new ApiError(0, "Network error — check your connection and try again.");
  }

  const payload = (await res.json().catch(() => ({}))) as {
    backup_codes?: string[];
    error?: string;
  };
  if (!res.ok) {
    throw new ApiError(
      res.status,
      payload.error ?? "Could not regenerate recovery codes.",
    );
  }

  return {
    backupCodes: Array.isArray(payload.backup_codes) ? payload.backup_codes : [],
  };
}

// ---------------------------------------------------------------------------
// Handoff (auth origin → workspace origin)
// ---------------------------------------------------------------------------

/**
 * Complete a finished auth flow: mint a single-use handoff token on the auth
 * origin, POST it (body only) to the workspace origin's /api/auth/handoff to
 * establish the host-scoped session cookie, then navigate to the workspace
 * root. The URL bar ends on {slug}.localhost — never signin.
 */
export async function completeHandoff(redirect = "/"): Promise<void> {
  const mint = await bffPost<{
    token: string;
    workspaceUrl: string;
    redirect: string;
  }>("/api/auth/handoff/mint", { redirect });

  // Redeem via a top-level form POST navigation, not fetch. The workspace
  // origin sets the host-scoped session cookie during a first-party navigation
  // and 302s to the redirect target — no CORS, no third-party-cookie blocking.
  // (A cross-site fetch would drop the Set-Cookie under Chrome's third-party
  // cookie blocking, bouncing the user straight back to signin.)
  const form = document.createElement("form");
  form.method = "POST";
  form.action = new URL("/api/auth/handoff", mint.workspaceUrl).toString();
  form.style.display = "none";
  const tokenInput = document.createElement("input");
  tokenInput.type = "hidden";
  tokenInput.name = "token";
  tokenInput.value = mint.token;
  form.appendChild(tokenInput);
  document.body.appendChild(form);
  form.submit();
}

export async function confirmMfaSetup(input: {
  code: string;
}): Promise<{ status: "ok" } | { status: "invalid" }> {
  let res: Response;
  try {
    res = await fetch("/api/auth/mfa/confirm", {
      method: "POST",
      headers: authHeaders(),
      body: JSON.stringify({ code: input.code }),
      cache: "no-store",
    });
  } catch {
    throw new ApiError(0, "Network error — check your connection and try again.");
  }

  const payload = (await res.json().catch(() => ({}))) as {
    ok?: boolean;
    error?: string;
  };
 if (res.status === 400 || res.status === 403) {
    return { status: "invalid" };
  }
  if (!res.ok) {
    throw new ApiError(res.status, payload.error ?? "Could not verify the code.");
  }
  return payload.ok ? { status: "ok" } : { status: "invalid" };
}
