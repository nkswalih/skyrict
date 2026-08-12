import type { APIRequestContext } from "@playwright/test";

import { api, bff, ApiError } from "./network";
import { signupHost } from "./env";
import { totp } from "./crypto";

export const E2E_PASSWORD = "E2ePass1234!x";

let seq = 0;
function nextSeq(): number {
  seq += 1;
  return seq;
}

const RUN_ID = Date.now().toString(36).toLowerCase();

export function uniqueEmail(prefix: string): string {
  return `e2e.${prefix}.${RUN_ID}.${nextSeq()}@skyrict-e2e.com`;
}

export function uniqueSlug(prefix: string): string {
  return `${prefix}-${RUN_ID}-${nextSeq()}`.toLowerCase();
}

export interface Account {
  email: string;
  password: string;
  fullName: string;
  companyName: string;
  slug: string;
  tenantId: string | null;
}

export interface AuthResponse {
  access_token: string | null;
  refresh_token: string | null;
  token_type: string;
  expires_in: number;
  mfa_required: boolean;
  mfa_token: string | null;
  next_step: string | null;
  user: Record<string, unknown> | null;
}

export interface SessionRecord {
  id: string;
  user_id: string;
  tenant_id: string;
  ip_address: string | null;
  user_agent: string | null;
  status: string;
  is_trusted: boolean;
  created_at: string;
  last_active_at: string;
  expires_at: string | null;
}

export interface Invitation {
  id: string;
  token: string;
  email: string;
  role_name: string;
  expires_at: string;
  used_at: string | null;
  created_at: string;
}

/**
 * Create a workspace owner exactly as the browser does — through the web BFF
 * routes — so fixtures exercise the real middleware, CSRF gate, and backend
 * wizard endpoints without spending browser time.
 */
export async function signupAccountViaBff(
  request: APIRequestContext,
  prefix: string,
): Promise<Account> {
  const email = uniqueEmail(prefix);
  const password = E2E_PASSWORD;
  const fullName = `E2E ${prefix.replace(/[-_]/g, " ")} Owner`;
  const companyName = `${prefix} ${nextSeq()} Inc`;
  const slug = uniqueSlug(prefix);

  const captcha = await bff<{ captchaId: string; answer: string | null }>(
    request,
    "/api/auth/captcha",
    { method: "GET", host: signupHost },
  );
  if (!captcha.captchaId) {
    throw new Error("No CAPTCHA challenge issued by the backend.");
  }
  if (!captcha.answer) {
    throw new Error(
      "CAPTCHA answer is null — the identity service must run with IDENTITY_ENVIRONMENT=test.",
    );
  }

  await bff(request, "/api/auth/start", {
    host: signupHost,
    body: { email },
  });

  const sent = await bff<{ status: string; resendIn: number; code: string | null }>(
    request,
    "/api/auth/code/send",
    { host: signupHost, body: { email } },
  );
  if (!sent.code) {
    throw new Error(
      "Plaintext OTP missing — the identity service must run with IDENTITY_ENVIRONMENT=test.",
    );
  }

  const verified = await bff<{ status: string; verificationToken: string | null }>(
    request,
    "/api/auth/code/verify",
    { host: signupHost, body: { email, code: sent.code } },
  );
  if (verified.status !== "ok" || !verified.verificationToken) {
    throw new Error(`Email verification failed with status "${verified.status}".`);
  }

  await bff(request, "/api/auth/password", {
    host: signupHost,
    body: {
      email,
      verificationToken: verified.verificationToken,
      password,
      captchaId: captcha.captchaId,
      captchaAnswer: captcha.answer,
    },
  });

  const org = await bff<{
    status: string;
    mfaRequired: boolean;
    tenantId: string | null;
    tenantSlug: string;
  }>(request, "/api/auth/org", {
    host: signupHost,
    body: {
      email,
      verificationToken: verified.verificationToken,
      planId: "professional",
      companyName,
      industry: "Technology",
      workspaceSlug: slug,
      ownerFullName: fullName,
      phoneCountry: "US",
      phoneNumber: "555-0100",
      address: {
        country: "US",
        addressLine1: "100 Market Street",
        city: "San Francisco",
        state: "CA",
        postalCode: "94103",
      },
    },
  });

  return {
    email,
    password,
    fullName,
    companyName,
    slug: org.tenantSlug || slug,
    tenantId: org.tenantId,
  };
}

export async function login(
  request: APIRequestContext,
  account: Pick<Account, "email" | "password"> & { slug?: string },
): Promise<AuthResponse> {
  return api<AuthResponse>(request, "/auth/login", {
    body: { email: account.email, password: account.password, tenant_slug: account.slug ?? null },
    slug: account.slug,
  });
}

export async function verifyMfaChallenge(
  request: APIRequestContext,
  input: { mfaToken: string; code: string; slug: string },
): Promise<AuthResponse> {
  return api<AuthResponse>(request, "/auth/mfa/verify", {
    body: { mfa_token: input.mfaToken, code: input.code },
    slug: input.slug,
  });
}

export async function refresh(
  request: APIRequestContext,
  input: { refreshToken: string; slug: string },
): Promise<AuthResponse> {
  return api<AuthResponse>(request, "/auth/refresh", {
    body: { refresh_token: input.refreshToken },
    slug: input.slug,
  });
}

export async function logout(
  request: APIRequestContext,
  input: { refreshToken?: string; accessToken: string; slug: string },
): Promise<void> {
  await api(request, "/auth/logout", {
    body: { refresh_token: input.refreshToken ?? null },
    token: input.accessToken,
    slug: input.slug,
  });
}

export async function listSessions(
  request: APIRequestContext,
  input: { accessToken: string; slug: string },
): Promise<{ sessions: SessionRecord[]; total: number }> {
  return api(request, "/sessions", { method: "GET", token: input.accessToken, slug: input.slug });
}

export async function revokeSession(
  request: APIRequestContext,
  input: { accessToken: string; slug: string; sessionId: string },
): Promise<void> {
  await api(request, `/sessions/${input.sessionId}`, {
    method: "DELETE",
    token: input.accessToken,
    slug: input.slug,
  });
}

export async function trustSession(
  request: APIRequestContext,
  input: { accessToken: string; slug: string; sessionId: string },
): Promise<void> {
  await api(request, `/sessions/${input.sessionId}/trusted`, {
    method: "PATCH",
    body: { is_trusted: true },
    token: input.accessToken,
    slug: input.slug,
  });
}

export async function mfaSetupApi(
  request: APIRequestContext,
  input: { accessToken: string; slug: string },
): Promise<{ secret: string; provisioning_uri: string; backup_codes: string[] }> {
  return api(request, "/mfa/setup", { token: input.accessToken, slug: input.slug });
}

export async function mfaVerifyApi(
  request: APIRequestContext,
  input: { accessToken: string; slug: string; code: string },
): Promise<{ verified: boolean }> {
  return api(request, "/mfa/verify", {
    body: { code: input.code },
    token: input.accessToken,
    slug: input.slug,
  });
}

export async function createInvitation(
  request: APIRequestContext,
  input: { accessToken: string; slug: string; email: string; roleName: string },
): Promise<Invitation> {
  return api<Invitation>(request, "/invitations", {
    body: { email: input.email, role_name: input.roleName },
    token: input.accessToken,
    slug: input.slug,
  });
}

export async function acceptInvitation(
  request: APIRequestContext,
  input: {
    token: string;
    email: string;
    password: string;
    fullName: string;
    slug: string;
  },
): Promise<void> {
  await api(request, "/invitations/accept", {
    body: {
      token: input.token,
      email: input.email,
      password: input.password,
      full_name: input.fullName,
    },
    slug: input.slug,
  });
}

export async function getMyRoles(
  request: APIRequestContext,
  input: { accessToken: string; slug: string },
): Promise<{ roles: string[]; permissions: string[] }> {
  return api(request, "/roles/me", { method: "GET", token: input.accessToken, slug: input.slug });
}

/**
 * Enroll MFA for a freshly-created account (login is next_step=mfa.setup).
 * Returns the TOTP secret, the issued access token, and the backup codes.
 */
export async function enrollMfaViaApi(
  request: APIRequestContext,
  account: Account,
): Promise<{ secret: string; accessToken: string; backupCodes: string[] }> {
  const pending = await login(request, account);
  if (pending.next_step !== "mfa.setup" || !pending.access_token) {
    throw new Error("Expected next_step=mfa.setup from a fresh account login.");
  }
  const setup = await mfaSetupApi(request, {
    accessToken: pending.access_token,
    slug: account.slug,
  });
  await mfaVerifyApi(request, {
    accessToken: pending.access_token,
    slug: account.slug,
    code: totp(setup.secret),
  });
  return {
    secret: setup.secret,
    accessToken: pending.access_token,
    backupCodes: setup.backup_codes,
  };
}

/** Full login for a user that already has MFA enabled: challenge + TOTP verify. */
export async function loginVerified(
  request: APIRequestContext,
  account: Account,
  secret: string,
): Promise<AuthResponse> {
  const challenge = await login(request, account);
  if (challenge.next_step !== "mfa.verify" || !challenge.mfa_token) {
    throw new Error("Expected next_step=mfa.verify for a user with MFA enabled.");
  }
  return verifyMfaChallenge(request, {
    mfaToken: challenge.mfa_token,
    code: totp(secret),
    slug: account.slug,
  });
}

export { ApiError };
