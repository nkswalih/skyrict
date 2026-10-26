"use client";

import { Spinner } from "@/components/ui/spinner";
import { useCallback, useEffect, useRef, useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { zodResolver } from "@hookform/resolvers/zod";
import { Lock, Mail, ShieldCheck } from "lucide-react";
import { useRouter } from "next/navigation";

import {
    completeHandoff,
    loginEmailPassword,
    verifyMfa,
} from "@/lib/api/auth-api";
import { resolveHandoffDestination } from "@/lib/auth/handoff";
import { AuthButton } from "@/lib/auth/AuthButton";
import { AuthInput } from "@/lib/auth/AuthInput";
import { OtpInput } from "@/lib/auth/OtpInput";

const credentialsSchema = z.object({
    email: z.string().email("Enter a valid email address"),
    password: z.string().min(1, "Enter your password"),
});

type CredentialsValues = z.infer<typeof credentialsSchema>;

function LoginForm({
    initialEmail = "",
    initialError = "",
    accepted = false,
}: {
    initialEmail?: string;
    initialError?: string;
    accepted?: boolean;
}) {
    const router = useRouter();
    const [step, setStep] = useState<"credentials" | "mfa">("credentials");
    const [genericError, setGenericError] = useState<string | undefined>(
        initialError,
    );
    const [mfaToken, setMfaToken] = useState<string>();
    const [mfaCode, setMfaCode] = useState("");
    const [useBackup, setUseBackup] = useState(false);
    const [backupCode, setBackupCode] = useState("");
    const [mfaError, setMfaError] = useState(false);
    const [verifyingMfa, setVerifyingMfa] = useState(false);
    const [handingOff, setHandingOff] = useState(false);
    const verifyingMfaRef = useRef(false);

    const {
        register,
        handleSubmit,
        formState: { errors, isSubmitting },
    } = useForm<CredentialsValues>({
        resolver: zodResolver(credentialsSchema),
        defaultValues: { email: initialEmail, password: "" },
    });

    async function finish() {
        setHandingOff(true);
        await completeHandoff(await resolveHandoffDestination());
    }

    async function onSubmitCredentials(values: CredentialsValues) {
        setGenericError(undefined);
        try {
            const result = await loginEmailPassword(values);
            if (result.status === "mfa_challenge") {
                setMfaToken(result.mfaToken);
                setMfaCode("");
                setBackupCode("");
                setUseBackup(false);
                setMfaError(false);
                setStep("mfa");
                return;
            }
            if (result.status === "mfa_setup") {
                router.push("/setup-mfa");
                return;
            }
            await finish();
        } catch (err) {
            setGenericError(
                err instanceof Error
                    ? err.message
                    : "Unable to sign in. Check your credentials and try again.",
            );
        }
    }

    const submitMfa = useCallback(
        async (code: string) => {
            if (!mfaToken) {
                setMfaError(true);
                return;
            }
            if (verifyingMfaRef.current) return;
            verifyingMfaRef.current = true;
            setVerifyingMfa(true);
            setMfaError(false);
            const result = await verifyMfa({ code, mfaToken });
            verifyingMfaRef.current = false;
            setVerifyingMfa(false);
            if (result.status === "ok") {
                setHandingOff(true);
                await completeHandoff(await resolveHandoffDestination());
            } else {
                setMfaError(true);
                setMfaCode("");
                setBackupCode("");
            }
        },
        [mfaToken],
    );

    useEffect(() => {
        if (!useBackup && mfaCode.length === 6) {
            void submitMfa(mfaCode);
        }
    }, [mfaCode, useBackup, submitMfa]);

    function onSubmitMfa() {
        const code = useBackup ? backupCode : mfaCode;
        const ready = useBackup
            ? /^[a-f0-9]{16}$/.test(code)
            : code.length === 6;
        if (!ready) {
            setMfaError(true);
            return;
        }
        void submitMfa(code);
    }

    if (step === "mfa") {
        return (
            <div className="space-y-6">
                <div className="flex items-start gap-3">
                    <div className="flex size-10 shrink-0 items-center justify-center rounded-lg bg-primary/15">
                        <ShieldCheck
                            aria-hidden="true"
                            className="size-5 text-primary"
                        />
                    </div>
                    <div className="space-y-1">
                        <h2 className="font-display text-lg font-semibold text-foreground">
                            Two-factor check
                        </h2>
                        <p className="text-sm text-muted-foreground">
                            {useBackup
                                ? "Enter one of your backup codes. Each code works once."
                                : "Enter the 6-digit code from your authenticator app."}
                        </p>
                    </div>
                </div>
                <form
                    onSubmit={(event) => {
                        event.preventDefault();
                        onSubmitMfa();
                    }}
                    className="space-y-6"
                >
                    {useBackup ? (
                        <input
                            value={backupCode}
                            onChange={(event) =>
                                setBackupCode(
                                    event.target.value
                                        .replace(/[^a-f0-9]/gi, "")
                                        .toLowerCase(),
                                )
                            }
                            placeholder="abcdef0123456789"
                            aria-label="Backup code"
                            aria-invalid={mfaError}
                            autoComplete="off"
                            disabled={verifyingMfa}
                            className="h-14 w-full rounded-lg border border-border bg-card px-4 text-center font-mono text-lg lowercase tracking-widest tabular-nums outline-none transition-colors focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/30"
                        />
                    ) : (
                        <OtpInput
                            value={mfaCode}
                            onChange={setMfaCode}
                            disabled={verifyingMfa}
                            error={mfaError}
                            ariaLabel="Two-factor code"
                        />
                    )}
                    {mfaError ? (
                        <p className="text-sm font-medium text-destructive">
                            That code didn&apos;t match. Try again.
                        </p>
                    ) : null}
                    <AuthButton
                        type="submit"
                        className="size-10 justify-self-end w-full"
                        variant="brand"
                        size="icon-lg"
                        loading={verifyingMfa || handingOff}
                        disabled={
                            useBackup
                                ? backupCode.length !== 16
                                : mfaCode.length !== 6
                        }
                    >
                        Verify code
                    </AuthButton>
                    <div className="space-y-3">
                        <button
                            type="button"
                            onClick={() => {
                                setUseBackup((value) => !value);
                                setMfaCode("");
                                setBackupCode("");
                                setMfaError(false);
                            }}
                            disabled={verifyingMfa}
                            className="w-full text-center text-sm text-muted-foreground underline-offset-4 hover:underline disabled:cursor-not-allowed disabled:opacity-50"
                        >
                            {useBackup
                                ? "Use authenticator code"
                                : "Use a backup code"}
                        </button>
                        <button
                            type="button"
                            onClick={() => {
                                setStep("credentials");
                                setMfaCode("");
                                setBackupCode("");
                                setUseBackup(false);
                                setMfaError(false);
                            }}
                            disabled={verifyingMfa}
                            className="w-full text-center text-sm text-muted-foreground underline-offset-4 hover:underline disabled:cursor-not-allowed disabled:opacity-50"
                        >
                            Back to sign in
                        </button>
                    </div>
                </form>
            </div>
        );
    }

    if (handingOff) {
        return (
            <div className="flex items-center justify-center gap-2 py-16 text-sm text-muted-foreground">
                <Spinner
                    aria-hidden="true"
                    className="size-4"
                />
                {"Opening your workspace\n"}
            </div>
        );
    }

    return (
        <form
            onSubmit={handleSubmit(onSubmitCredentials)}
            className="space-y-5"
            noValidate
        >
            {accepted ? (
                <div
                    role="status"
                    className="rounded-lg border border-emerald-500/30 bg-emerald-500/10 px-3 py-2 text-sm text-emerald-700 dark:text-emerald-400"
                >
                    Account created - sign in to continue.
                </div>
            ) : null}
            <AuthInput
                label="Email"
                id="email"
                type="email"
                autoComplete="email"
                placeholder="Email"
                icon={Mail}
                error={errors.email?.message}
                {...register("email")}
            />
            <AuthInput
                label="Password"
                id="password"
                type="password"
                autoComplete="current-password"
                placeholder="Password"
                icon={Lock}
                error={errors.password?.message}
                {...register("password")}
            />
            {genericError ? (
                <div
                    role="alert"
                    className="rounded-lg border border-destructive/30 bg-destructive/5 px-3 py-2 text-sm text-destructive"
                >
                    {genericError}
                </div>
            ) : null}
            <AuthButton type="submit" className="size-10 justify-self-end w-full" variant="brand" size="icon-lg" loading={isSubmitting}>
                Sign in
            </AuthButton>
        </form>
    );
}

export { LoginForm };
