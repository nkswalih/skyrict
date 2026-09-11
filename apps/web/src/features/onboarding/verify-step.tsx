"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ArrowLeft, LoaderCircle, ShieldCheck } from "lucide-react";

import { requestVerificationCode, verifyEmailCode } from "@/lib/api/auth-api";
import { AuthButton } from "@/lib/auth/AuthButton";
import { OtpInput } from "@/lib/auth/OtpInput";

const RESEND_SECONDS = 60;

function VerifyStep({ email }: { email: string }) {
  const router = useRouter();
  const [code, setCode] = useState("");
  const [verifying, setVerifying] = useState(false);
  const [error, setError] = useState<string>();
  const [resendIn, setResendIn] = useState(RESEND_SECONDS);
  const [resending, setResending] = useState(false);
  const [sendError, setSendError] = useState<string>();
  const verifyingRef = useRef(false);

  const sendCode = useCallback(async () => {
    setSendError(undefined);
    try {
      const result = await requestVerificationCode({ email });
      setResendIn(result.resendIn);
    } catch (err) {
      setSendError(
        err instanceof Error ? err.message : "Could not send the code. Try again.",
      );
    }
  }, [email]);

  useEffect(() => {
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
        const next = new URLSearchParams({
          email,
          vt: result.verificationToken,
        });
        router.push(`/register/security?${next.toString()}`);
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
            <LoaderCircle
              aria-hidden="true"
              className="size-3.5 animate-spin"
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
              disabled={resending}
              className="font-medium text-primary underline-offset-4 hover:underline disabled:cursor-not-allowed disabled:opacity-50"
            >
              {resending ? "Resending\n" : "Resend code"}
            </button>
          )}
        </p>
        <p className="text-muted-foreground">
          Wrong email?{" "}
          <Link
            href="/register"
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
          href="/register"
          className="underline-offset-4 hover:underline"
        >
          Back to account details
        </Link>
      </p>
    </div>
  );
}

export { VerifyStep };
