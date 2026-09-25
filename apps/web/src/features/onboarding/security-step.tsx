"use client";

import { useCallback, useState } from "react";
import { useRouter } from "next/navigation";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { zodResolver } from "@hookform/resolvers/zod";
import { KeyRound } from "lucide-react";

import {
    CaptchaChallenge,
    type CaptchaValue,
} from "@/components/onboarding/captcha-challenge";
import { ApiError, completeSecurityStep } from "@/lib/api/auth-api";
import { setWizardCredentials } from "@/lib/auth/wizard-session";
import { AuthInput } from "@/lib/auth/AuthInput";
import { AuthButton } from "@/lib/auth/AuthButton";
import { PasswordField } from "@/lib/auth/PasswordField";
import { PasswordRequirements } from "@/lib/auth/PasswordRequirements";
import { PasswordStrength } from "@/lib/auth/PasswordStrength";
import { allRequirementsMet } from "@/lib/auth/password";

const securitySchema = z
    .object({
        password: z
            .string()
            .min(12, "Use at least 12 characters")
            .refine(
                (value) => allRequirementsMet(value),
                "Meet every requirement to continue.",
            ),
        confirmPassword: z.string(),
    })
    .refine((data) => data.password === data.confirmPassword, {
        message: "Passwords don't match",
        path: ["confirmPassword"],
    });

type SecurityValues = z.infer<typeof securitySchema>;

function SecurityStep({ email, vt }: { email: string; vt: string }) {
    const router = useRouter();

    const [captcha, setCaptcha] = useState<CaptchaValue | null>(null);
    const [captchaError, setCaptchaError] = useState(false);
    const [captchaRevision, setCaptchaRevision] = useState(0);
    const [submitError, setSubmitError] = useState("");

    const {
        register,
        handleSubmit,
        watch,
        formState: { errors, isSubmitting },
    } = useForm<SecurityValues>({
        resolver: zodResolver(securitySchema),
        defaultValues: { password: "", confirmPassword: "" },
    });

    const password = watch("password");

    const handleCaptchaChange = useCallback((value: CaptchaValue | null) => {
        setCaptcha(value);
        if (value) setCaptchaError(false);
    }, []);

    const handleCaptchaError = useCallback((failed: boolean) => {
        setCaptchaError(failed);
    }, []);

    function onSubmit(values: SecurityValues) {
        if (!captcha) {
            setCaptchaError(true);
            return;
        }
        setSubmitError("");
        completeSecurityStep({
            email,
            verificationToken: vt,
            password: values.password,
            captchaId: captcha.captchaId,
            captchaAnswer: captcha.answer,
        })
            .then(() => {
                setWizardCredentials({ email, password: values.password });
                const next = new URLSearchParams({ email, vt });
                router.push(`/signup/plan?${next.toString()}`);
            })
            .catch((error: unknown) => {
                if (
                    error instanceof ApiError &&
                    (error.status === 422 || error.status === 401)
                ) {
                    setCaptchaError(true);
                    setCaptchaRevision((revision) => revision + 1);
                }
                setSubmitError(
                    error instanceof ApiError
                        ? error.message
                        : "We couldn't complete this step. Please try again.",
                );
            });
    }

    return (
        <form
            onSubmit={handleSubmit(onSubmit)}
            className="space-y-4"
            noValidate
        >
            <div className="space-y-1.5">
                <PasswordField
                    label="Password"
                    id="password"
                    autoComplete="new-password"
                    placeholder="Password"
                    icon={KeyRound}
                    error={errors.password?.message}
                    {...register("password")}
                />
                <PasswordStrength password={password} />
                <PasswordRequirements password={password} />
            </div>

            <AuthInput
                label="Confirm password"
                id="confirmPassword"
                type="password"
                autoComplete="new-password"
                placeholder="Repeat your password"
                error={errors.confirmPassword?.message}
                {...register("confirmPassword")}
            />

            <div className="space-y-1.5 pt-1">
                <CaptchaChallenge
                    revision={captchaRevision}
                    onCaptchaChange={handleCaptchaChange}
                    onError={handleCaptchaError}
                />
                {captchaError ? (
                    <p className="text-xs font-medium text-destructive">
                        Enter the code shown above to continue.
                    </p>
                ) : null}
            </div>

            {submitError ? (
                <p className="text-xs font-medium text-destructive">
                    {submitError}
                </p>
            ) : null}

            <AuthButton type="submit" className="w-full" loading={isSubmitting}>
                Continue
            </AuthButton>
        </form>
    );
}

export { SecurityStep };
