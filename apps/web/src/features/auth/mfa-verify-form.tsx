"use client";

import { Spinner } from "@/components/ui/spinner";
import { useCallback, useEffect, useRef, useState } from "react";
import { ShieldCheck } from "lucide-react";

import { completeHandoff, verifyMfa } from "@/lib/api/auth-api";
import { resolveHandoffDestination } from "@/lib/auth/handoff";
import { AuthButton } from "@/lib/auth/AuthButton";
import { OtpInput } from "@/lib/auth/OtpInput";

function MfaVerifyForm({ mfaToken }: { mfaToken?: string }) {
    const [useBackup, setUseBackup] = useState(false);
    const [code, setCode] = useState("");
    const [backupCode, setBackupCode] = useState("");
    const [error, setError] = useState(false);
    const [verifying, setVerifying] = useState(false);
    const [handingOff, setHandingOff] = useState(false);
    const verifyingRef = useRef(false);

    const codeReady = useBackup ? backupCode.length === 16 : code.length === 6;

    const submitCode = useCallback(
        async (value: string) => {
            if (!mfaToken) {
                setError(true);
                return;
            }
            if (verifyingRef.current) return;
            verifyingRef.current = true;
            setVerifying(true);
            setError(false);
            const result = await verifyMfa({ code: value, mfaToken });
            verifyingRef.current = false;
            setVerifying(false);
            if (result.status === "ok") {
                setHandingOff(true);
                const dest = await resolveHandoffDestination();
                await completeHandoff(dest);
            } else {
                setError(true);
                setCode("");
                setBackupCode("");
            }
        },
        [mfaToken],
    );

    useEffect(() => {
        if (!useBackup && code.length === 6) {
            void submitCode(code);
        }
    }, [code, useBackup, submitCode]);

    function handleVerify() {
        void submitCode(useBackup ? backupCode : code);
    }

    function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
        event.preventDefault();
        if (!codeReady) return;
        handleVerify();
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
        <form onSubmit={handleSubmit} className="space-y-6">
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
                    aria-invalid={error}
                    autoComplete="off"
                    disabled={verifying}
                    className="h-14 w-full rounded-lg border border-border bg-card px-4 text-center font-mono text-lg lowercase tracking-widest tabular-nums outline-none transition-colors focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/30"
                />
            ) : (
                <OtpInput
                    value={code}
                    onChange={setCode}
                    disabled={verifying}
                    error={error}
                />
            )}
            {error ? (
                <p className="text-sm font-medium text-destructive">
                    That code didn&apos;t match. Try again.
                </p>
            ) : null}
            <AuthButton
                type="submit"
                className="size-10 justify-self-end w-full"
                variant="brand"
                size="icon-lg"
                loading={verifying}
                disabled={!codeReady}
            >
                Verify
            </AuthButton>
            <button
                type="button"
                onClick={() => {
                    setUseBackup((value) => !value);
                    setError(false);
                }}
                disabled={verifying}
                className="w-full text-center text-sm text-muted-foreground underline-offset-4 hover:underline disabled:cursor-not-allowed disabled:opacity-50"
            >
                {useBackup ? "Use authenticator code" : "Use a backup code"}
            </button>
        </form>
    );
}

export { MfaVerifyForm };
