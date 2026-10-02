"use client";

import { Spinner } from "@/components/ui/spinner";
import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ArrowLeft, ShieldCheck } from "lucide-react";

import { requestVerificationCode, verifyEmailCode } from "@/lib/api/auth-api";
import { TurnstileWidget } from "@/components/onboarding/turnstile-widget";
import {
    canRequestCode,
    canResend,
    challengeContainerCollapsed,
    stateAfterSendAttempt,
} from "@/features/onboarding/code-send-challenge";
import { AuthButton } from "@/lib/auth/AuthButton";
import { OtpInput } from "@/lib/auth/OtpInput";
import { env } from "@/config/env";

const RESEND_SECONDS = 60;

function VerifyStep({ email }: { email: string }) {
  const router = useRouter();
  const [code, setCode] = useState("");
  const [verifying, setVerifying] = useState(false);
  const [error, setError] = useState<string>();
  const [resendIn, setResendIn] = useState(RESEND_SECONDS);
  const [resending, setResending] = useState(false);
  const [sendError, setSendError] = useState<string>();
  const [turnstileToken, setTurnstileToken] = useState<string | null>(null);
  const [resetSignal, setResetSignal] = useState(0);
  const verifyingRef = useRef(false);

  const sendCode = useCallback(async () => {
    setSendError(undefined);
    // No challenge solved yet: nothing to send. The effect below re-runs this
    // callback as soon as the token arrives, so the first code goes out on its
    // own exactly as it did before the gate existed.
    if (!canRequestCode(turnstileToken)) return;

    // Spend the token now, before awaiting, and do it whether or not the send
    // works. Cloudflare consumes it during verification either way.
    //
    // Clearing it here is also what makes the re-arm below possible: the widget
    // container collapses whenever a token is held, and Turnstile will not run
    // a challenge inside a collapsed container. A widget hidden behind the
    // token it just spent can only ever reset to nothing, which left resend
    // replaying a token identity had already consumed. See
    // code-send-challenge.ts.
    // Read the post-send state from the same function the tests pin, rather
    // than hard-coding null here. A test that re-implemented the rule would
    // pass while the component drifted, which is the only thing a test of this
    // kind is for.
    const { token: noTokenHeld } = stateAfterSendAttempt();
    setTurnstileToken(noTokenHeld);
    setResetSignal((n) => n + 1);

    const spent = turnstileToken;
    try {
      const result = await requestVerificationCode({
        email,
        turnstileToken: spent,
      });
      setResendIn(result.resendIn);
    } catch (err) {
      setSendError(
        err instanceof Error ? err.message : "Could not send the code. Try again.",
      );
    }
  }, [email, turnstileToken]);

  // Auto-send the first code, once, as soon as a challenge has been solved.
  //
  // The ref is what stops this becoming a loop: re-arming after a send clears
  // the token and a new one arrives, and without the ref every arrival would
  // trigger another send.
  const autoSentRef = useRef(false);
  useEffect(() => {
    if (autoSentRef.current || !turnstileToken) return;
    autoSentRef.current = true;
    sendCode().catch(() => {});
  }, [turnstileToken, sendCode]);

  useEffect(() => {
    if (resendIn <= 0) return;
    const timer = setInterval(() => {
      setResendIn((seconds) => Math.max(0, seconds - 1));
    }, 1000);
    return () => clearInterval(timer);
  }, [resendIn]);

  const submitCode = useCallback(
    async (value: string) => {
      if (value.length !== 6 || verifyingRef.current) return;
      verifyingRef.current = true;
      setVerifying(true);
      setError(undefined);
      let result: Awaited<ReturnType<typeof verifyEmailCode>>;
      try {
        result = await verifyEmailCode({ email, code: value });
      } catch (err) {
        verifyingRef.current = false;
        setVerifying(false);
        setError(
          err instanceof Error
            ? err.message
            : "Could not verify the code. Try again.",
        );
        return;
      }
      verifyingRef.current = false;
      setVerifying(false);
      if (result.status === "ok") {
        const next = new URLSearchParams({
          email,
          vt: result.verificationToken,
        });
        router.push(`/signup/security?${next.toString()}`);
      } else {
        setCode("");
        setError(
          result.status === "expired"
            ? "This code expired. Request a new one."
            : "That code isn't right. Check it and try again.",
        );
      }
    },
    [email, router],
  );

  useEffect(() => {
    if (code.length === 6) {
      void submitCode(code);
    }
  }, [code, submitCode]);

  async function handleResend() {
    setResending(true);
    setCode("");
    setError(undefined);
    await sendCode();
    setResending(false);
  }

  async function handleVerify() {
    if (code.length < 6) {
      setError("Enter the full 6-digit code.");
      return;
    }
    void submitCode(code);
  }

  return (
    <div className="space-y-6">
      <div className="flex items-start gap-3 rounded-lg border border-border bg-muted/40 p-4">
        <ShieldCheck
          aria-hidden="true"
          className="mt-0.5 size-5 shrink-0 text-primary"
        />
        <div className="space-y-1 text-sm">
          <p className="font-medium text-foreground">Code sent to {email}</p>
          <p className="text-xs text-muted-foreground">
            Enter the 6-digit code below.
          </p>
        </div>
      </div>

      {sendError ? (
        <div className="rounded-lg border border-destructive/40 bg-destructive/5 p-3 text-sm text-destructive">
          {sendError}
        </div>
      ) : null}

      {/* Second challenge for the code request itself.

          Sign-up start and code send are both Turnstile-gated server-side, and
          they need separate tokens because a Turnstile token is single-use.
          This one is inline rather than the full-screen RiskChallenge overlay:
          the user has already passed that gate one step earlier, and taking the
          viewport over again to re-send a code would be a worse experience than
          the protection is worth.

          It collapses only while a live token is held. That is deliberate and
          load-bearing rather than cosmetic - Turnstile cannot solve inside a
          `display: none` container, so a container collapsed behind the token
          it just spent would never re-arm. See code-send-challenge.ts. */}
      {!env.turnstileSiteKey ? (
        <div className="rounded-lg border border-destructive/40 bg-destructive/5 p-3 text-sm text-destructive">
          Sign-up is unavailable: no CAPTCHA provider is configured, so the
          verification code cannot be requested. An administrator needs to set
          the Turnstile site key.
        </div>
      ) : (
        <div
          aria-hidden={challengeContainerCollapsed(turnstileToken)}
          inert={challengeContainerCollapsed(turnstileToken)}
          className={
            challengeContainerCollapsed(turnstileToken)
              ? "hidden"
              : "flex justify-center py-1"
          }
        >
          <TurnstileWidget
            siteKey={env.turnstileSiteKey}
            onTokenChange={setTurnstileToken}
            resetSignal={resetSignal}
          />
        </div>
      )}

      <div className="space-y-3">
        <OtpInput
          length={6}
          value={code}
          onChange={setCode}
          disabled={verifying || resending}
          error={Boolean(error)}
          ariaLabel="Verification code"
        />
        {verifying ? (
          <p className="flex items-center justify-center gap-1.5 text-xs text-muted-foreground">
            <Spinner
              aria-hidden="true"
              className="size-3.5"
            />
            {"Verifying code\n"}
          </p>
        ) : error ? (
          <p className="text-center text-xs font-medium text-destructive">
            {error}
          </p>
        ) : null}
      </div>

      <div className="space-y-2 text-center text-sm">
        <p className="text-muted-foreground">
          {resendIn > 0 ? (
            <>
              Resend code in{" "}
              <span className="font-mono tabular-nums text-foreground">
                {"0:"}
                {String(resendIn).padStart(2, "0")}
              </span>
            </>
          ) : (
            <button
              type="button"
              onClick={handleResend}
              // An expired cooldown is not enough. Without an unspent token the
              // click would reach sendCode's guard and vanish, so the button
              // stays disabled until the re-armed challenge produces one.
              disabled={
                !canResend(turnstileToken, { resending, resendIn })
              }
              className="font-medium text-primary underline-offset-4 hover:underline disabled:cursor-not-allowed disabled:opacity-50"
            >
              {resending ? "Resending\n" : "Resend code"}
            </button>
          )}
        </p>
        <p className="text-muted-foreground">
          Wrong email?{" "}
          <Link
            href="/signup"
            className="font-medium text-primary underline-offset-4 hover:underline"
          >
            Change it
          </Link>
        </p>
      </div>

      <AuthButton
        type="button"
        className="w-full"
        loading={verifying}
        onClick={handleVerify}
      >
        Verify email
      </AuthButton>

      <p className="flex items-center justify-center gap-1 text-xs text-muted-foreground">
        <ArrowLeft aria-hidden="true" className="size-3" />
        <Link
          href="/signup"
          className="underline-offset-4 hover:underline"
        >
          Back to account details
        </Link>
      </p>
    </div>
  );
}

export { VerifyStep };
