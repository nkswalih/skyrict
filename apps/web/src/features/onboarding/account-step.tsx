"use client";

import { useRef, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { zodResolver } from "@hookform/resolvers/zod";
import { Mail } from "lucide-react";

import { env } from "@/config/env";
import { RiskChallenge } from "@/components/onboarding/risk-challenge";
import { checkEmailAvailability, signupStart } from "@/lib/api/auth-api";
import { NETWORK_ERROR_MESSAGE } from "@/lib/api/error-messages";
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
  const {
    register,
    handleSubmit,
    setError,
    formState: { errors, isSubmitting },
  } = useForm<AccountValues>({
    resolver: zodResolver(accountSchema),
    defaultValues: { email: "" },
  });

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
      setSubmitError(NETWORK_ERROR_MESSAGE);
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
    router.push(`/signup/verify?${next.toString()}`);
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
        hideLabel
        id="email"
        type="email"
        autoComplete="email"
        placeholder="name@company.com"
        icon={Mail}
        error={errors.email?.message}
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

      <p className="pt-1 text-center text-[11px] leading-relaxed text-muted-foreground">
        By signing up, I agree to the Skyrict{" "}
        <Link
          href="/terms"
          className="underline underline-offset-4 hover:text-foreground"
        >
          Terms of Service
        </Link>{" "}
        and{" "}
        <Link
          href="/privacy"
          className="underline underline-offset-4 hover:text-foreground"
        >
          Privacy Policy
        </Link>
        .
      </p>

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
