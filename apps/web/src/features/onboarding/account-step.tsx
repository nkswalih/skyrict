"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { zodResolver } from "@hookform/resolvers/zod";
import { CheckCircle2, LoaderCircle, Mail } from "lucide-react";

import { env } from "@/config/env";
import { RiskChallenge } from "@/components/onboarding/risk-challenge";
import { checkEmailAvailability, signupStart } from "@/lib/api/auth-api";
import { AuthButton } from "@/lib/auth/AuthButton";
import { AuthInput } from "@/lib/auth/AuthInput";

const emailSchema = z.string().trim().email("Enter a valid email address");

const accountSchema = z.object({
  email: emailSchema,
});

type AccountValues = z.infer<typeof accountSchema>;

function AccountStep({ demoCaptcha = false }: { demoCaptcha?: boolean }) {
  const router = useRouter();
  const formRef = useRef<HTMLFormElement>(null);
  const [captchaVisible, setCaptchaVisible] = useState(true);
  const [captchaValid, setCaptchaValid] = useState(false);
  const [captchaToken, setCaptchaToken] = useState<string | null>(null);
  const [captchaError, setCaptchaError] = useState(false);
  const [submitError, setSubmitError] = useState<string>();
  const [availability, setAvailability] = useState<
    "idle" | "checking" | "available" | "taken"
  >("idle");
  const {
    register,
    handleSubmit,
    watch,
    setError,
    formState: { errors, isSubmitting },
  } = useForm<AccountValues>({
    resolver: zodResolver(accountSchema),
    defaultValues: { email: "" },
  });

  const email = watch("email");

  useEffect(() => {
    let cancelled = false;
    const parsed = emailSchema.safeParse(email);
    if (!parsed.success) {
      setAvailability("idle");
      return;
    }
    setAvailability("checking");
    const timer = setTimeout(async () => {
      try {
        const result = await checkEmailAvailability({ email: parsed.data });
        if (!cancelled) {
          setAvailability(result.available ? "available" : "taken");
        }
      } catch {
        // Backend unreachable / transient failure - never crash the wizard.
        // Fall back to a neutral state so the user can still continue.
        if (!cancelled) {
          setAvailability("idle");
        }
      }
    }, 500);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [email]);

  async function onSubmit(values: AccountValues) {
    const honeypot = new FormData(formRef.current ?? undefined).get("website");
    if (typeof honeypot === "string" && honeypot.length > 0) {
      return;
    }
    let available: boolean;
    let availabilityFailed = false;
    try {
      available = (await checkEmailAvailability({ email: values.email })).available;
    } catch {
      available = false;
      availabilityFailed = true;
    }
    if (availabilityFailed) {
      setSubmitError("Could not reach the signup service. Is the backend running? Try again.");
      return;
    }
    if (!available) {
      setError("email", {
        type: "manual",
        message: "This email is unavailable.",
      });
      return;
    }
    if (captchaVisible && !captchaValid) {
      setCaptchaError(true);
      return;
    }
    if (captchaVisible && env.turnstileSiteKey && !captchaToken) {
      setCaptchaError(true);
      return;
    }
    setSubmitError(undefined);
    try {
      await signupStart({
        email: values.email.trim(),
        turnstileToken: captchaToken ?? undefined,
      });
    } catch (err) {
      setSubmitError(
        err instanceof Error ? err.message : "Could not start signup. Try again.",
      );
      return;
    }
    const next = new URLSearchParams({ email: values.email.trim() });
    router.push(`/register/verify?${next.toString()}`);
  }

  return (
    <form
      ref={formRef}
      onSubmit={handleSubmit(onSubmit)}
      className="space-y-4"
      noValidate
    >
      <AuthInput
        label="Work email"
        id="email"
        type="email"
        autoComplete="email"
        placeholder="you@company.com"
        icon={Mail}
        hint={
          availability === "checking"
            ? "Checking availability\n"
            : availability === "available"
              ? "This email is available."
              : undefined
        }
        error={
          errors.email?.message ??
          (availability === "taken"
            ? "This email is unavailable."
            : undefined)
        }
        trailing={
          availability === "checking" ? (
            <LoaderCircle
              aria-hidden="true"
              className="mr-1 size-4 animate-spin text-muted-foreground"
            />
          ) : availability === "available" ? (
            <CheckCircle2 aria-hidden="true" className="mr-1 size-4 text-primary" />
          ) : null
        }
        {...register("email")}
      />

      <div className="pt-1">
        <RiskChallenge
          demoCaptcha={demoCaptcha}
          onShowChange={setCaptchaVisible}
          onTokenChange={setCaptchaToken}
          onValidChange={(valid) => {
            setCaptchaValid(valid);
            if (valid) setCaptchaError(false);
          }}
        />
        {captchaVisible && !captchaValid ? (
          <p className="mt-1.5 text-xs font-medium text-muted-foreground">
            Complete the security check to continue.
          </p>
        ) : captchaError ? (
          <p className="mt-1.5 text-xs font-medium text-destructive">
            Confirm you&apos;re not a robot to continue.
          </p>
        ) : null}
        {submitError ? (
          <p className="mt-1.5 text-xs font-medium text-destructive">
            {submitError}
          </p>
        ) : null}
      </div>

      <AuthButton
        type="submit"
        className="w-full"
        loading={isSubmitting}
        disabled={captchaVisible && !captchaValid}
      >
        Continue with email
      </AuthButton>
    </form>
  );
}

export { AccountStep };
