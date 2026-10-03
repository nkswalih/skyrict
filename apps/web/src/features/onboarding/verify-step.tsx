"use client";

import { Spinner } from "@/components/ui/spinner";
import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ArrowLeft, ShieldCheck } from "lucide-react";

import { requestVerificationCode, verifyEmailCode } from "@/lib/api/auth-api";
import {
    clearSignupFlow,
    loadSignupFlow,
} from "@/features/onboarding/signup-flow-token";
import { AuthButton } from "@/lib/auth/AuthButton";
import { OtpInput } from "@/lib/auth/OtpInput";

const RESEND_SECONDS = 60;

const SESSION_EXPIRED =
    "This sign-up session has expired. Go back to step 1 and start again.";

function VerifyStep({ email }: { email: string }) {
  const router = useRouter();
  const [code, setCode] = useState("");
  const [verifying, setVerifying] = useState(false);
  const [error, setError] = useState<string>();
  const [resendIn, setResendIn] = useState(RESEND_SECONDS);
  const [resending, setResending] = useState(false);
  const [sendError, setSendError] = useState<string>();
  const verifyingRef = useRef(false);

  // Step 1 clears the one CAPTCHA the wizard asks for and hands the proof
  // back. Snapshot whether it arrived rather than reading it during render: the
  // token is spent the moment the code is verified, and a re-render after that
  // must not decide this step has nothing to show.
  const [proofMissing] = useState(() => loadSignupFlow(email) === null);

  const sendCode = useCallback(async () => {
    setSendError(undefined);
    const flowToken = loadSignupFlow(email);
    // Nothing to spend. A request without the proof would be refused anyway, so
    // say so instead of firing a doomed call.
    if (!flowToken) {
      setSendError(SESSION_EXPIRED);
      return;
    }
    try {
      const result = await requestVerificationCode({ email, flowToken });
      setResendIn(result.resendIn);
    } catch (err) {
      setSendError(
        err instanceof Error ? err.message : "Could not send the code. Try again.",
      );
    }
  }, [email]);

  // The first code goes out on its own as soon as this step opens. There is no
  // second challenge here: the user already cleared the wizard's one challenge
  // on step 1, and the proof that came back is what the backend spends.
  //
  // The ref is what stops this becoming a loop - it fires once per mount.
  const autoSentRef = useRef(false);
  useEffect(() => {
    if (autoSentRef.current) return;
    autoSentRef.current = true;
    sendCode().catch(() => {});
  }, [sendCode]);

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
        // Spent. Nothing after this step sends mail, so the proof has no
        // further use in this tab.
        clearSignupFlow(email);
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

  // No proof means no code is coming. Show the way out instead of an OTP box
  // that can never be filled in.
  if (proofMissing) {
    return (
      <div className="space-y-4">
        <div className="rounded-lg border border-destructive/40 bg-destructive/5 p-3 text-sm text-destructive">
          {SESSION_EXPIRED}
        </div>
        <Link href="/signup" className="block">
          <AuthButton className="w-full">
            Back to account details
          </AuthButton>
        </Link>
      </div>
    );
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
              disabled={resending || resendIn > 0}
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
