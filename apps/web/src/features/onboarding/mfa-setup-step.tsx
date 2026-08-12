"use client";

import { useEffect, useRef, useState } from "react";
import {
  Check,
  Copy,
  Download,
  KeyRound,
  LoaderCircle,
  QrCode,
  RefreshCw,
  ShieldAlert,
  ShieldCheck,
} from "lucide-react";
import { QRCodeSVG } from "qrcode.react";

import {
  completeHandoff,
  confirmMfaSetup,
  regenerateBackupCodes,
  setupMfa,
  type MfaSetup,
} from "@/lib/api/auth-api";
import { AuthButton } from "@/lib/auth/AuthButton";
import { OtpInput } from "@/lib/auth/OtpInput";
import { cn } from "@/lib/utils";

function MfaSetupStep() {
  const setupRef = useRef<{ started: boolean; mounted: boolean } | null>(null);
  const [setup, setSetup] = useState<MfaSetup>();
  const [code, setCode] = useState("");
  const [confirming, setConfirming] = useState(false);
  const [confirmed, setConfirmed] = useState(false);
  const [handingOff, setHandingOff] = useState(false);
  const [error, setError] = useState<string>();
  const [copied, setCopied] = useState(false);
  const [codesCopied, setCodesCopied] = useState(false);
  const [acknowledged, setAcknowledged] = useState(false);
  const [confirmingRegenerate, setConfirmingRegenerate] = useState(false);
  const [regenerating, setRegenerating] = useState(false);
  const [regenerateError, setRegenerateError] = useState<string>();
  const [regenerated, setRegenerated] = useState(false);

  useEffect(() => {
    const state = (setupRef.current ??= { started: false, mounted: true });
    state.mounted = true;
    if (state.started) return;
    state.started = true;
    setupMfa()
      .then((result) => {
        if (state.mounted) setSetup(result);
      })
      .catch((err: unknown) => {
        if (state.mounted) {
          setError(
            err instanceof Error
              ? err.message
              : "Could not start MFA setup. Try again.",
          );
        }
      });
    return () => {
      state.mounted = false;
    };
  }, []);

  async function copySecret() {
    if (!setup) return;
    await navigator.clipboard.writeText(setup.secret);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  }

  async function copyCodes() {
    if (!setup || setup.backupCodes.length === 0) return;
    await navigator.clipboard.writeText(setup.backupCodes.join("\n"));
    setCodesCopied(true);
    setTimeout(() => setCodesCopied(false), 1500);
  }

  function downloadCodes() {
    if (!setup || setup.backupCodes.length === 0) return;
    const body = [
      "Skyrict recovery codes",
      "Workspace owner sign-in backup.",
      "Store this file in a safe place. Each code works exactly once.",
      "Do not share these codes. Anyone with a code can sign in as you.",
      "",
      ...setup.backupCodes,
      "",
      "If you use a code, remember to download the updated list later.",
    ].join("\n");
    const url = URL.createObjectURL(
      new Blob([body], { type: "text/plain;charset=utf-8" }),
    );
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = "skyrict-recovery-codes.txt";
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    URL.revokeObjectURL(url);
  }

  async function confirm() {
    if (!setup) return;
    if (code.length !== 6) {
      setError("Enter the 6-digit code from your authenticator app.");
      return;
    }
    setConfirming(true);
    setError(undefined);
    try {
      const result = await confirmMfaSetup({ code });
      if (result.status === "ok") {
        setConfirmed(true);
      } else {
        setCode("");
        setError("That code doesn't match. Try again.");
      }
    } catch (err: unknown) {
      setError(
        err instanceof Error
          ? err.message
          : "Could not verify the code. Try again.",
      );
    } finally {
      setConfirming(false);
    }
  }

  async function regenerate() {
    if (!setup) return;
    setRegenerating(true);
    setRegenerateError(undefined);
    try {
      const result = await regenerateBackupCodes();
      setSetup({ ...setup, backupCodes: result.backupCodes });
      setAcknowledged(false);
      setCodesCopied(false);
      setRegenerated(true);
    } catch (err: unknown) {
      setRegenerateError(
        err instanceof Error ? err.message : "Could not regenerate codes. Try again.",
      );
    } finally {
      setRegenerating(false);
    }
  }

  function finish() {
    setHandingOff(true);
    void completeHandoff("/").catch((err: unknown) => {
      setHandingOff(false);
      setError(
        err instanceof Error ? err.message : "Could not open your workspace.",
      );
    });
  }

  if (!setup) {
    if (error) {
      return (
        <div className="space-y-4 py-8 text-center">
          <p className="text-sm font-medium text-destructive">{error}</p>
          <AuthButton
            type="button"
            className="w-full"
            onClick={() => window.location.reload()}
          >
            Try again
          </AuthButton>
        </div>
      );
    }
    return (
      <div className="flex items-center justify-center gap-2 py-16 text-sm text-muted-foreground">
        <LoaderCircle aria-hidden="true" className="size-4 animate-spin" />
        {"Preparing your authenticator enrollment\n"}
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-start gap-3 rounded-lg border border-primary/40 bg-primary/10 p-4">
        <ShieldCheck
          aria-hidden="true"
          className="mt-0.5 size-5 shrink-0 text-primary"
        />
        <div className="space-y-1 text-sm">
          <p className="font-medium text-foreground">Mandatory for your security</p>
          <p className="text-xs text-muted-foreground">
            Two-factor authentication is required for every Skyrict workspace.
            You&apos;ll need it the next time you sign in.
          </p>
        </div>
      </div>

      {!confirmed ? (
        <div className="space-y-5">
          <div className="rounded-xl border border-border bg-muted/40 p-4">
            <p className="flex items-center gap-1.5 text-sm font-medium text-foreground">
              <QrCode aria-hidden="true" className="size-4 text-primary" />
              Step 1 · Scan with your authenticator app
            </p>
            <div className="mx-auto mt-4 flex size-40 items-center justify-center rounded-xl border border-border bg-white p-2">
              <QRCodeSVG
                value={setup.otpauthUri}
                size={144}
                level="M"
                marginSize={0}
                aria-label="QR code to scan with your authenticator app"
              />
            </div>
            <p className="mt-3 text-center text-xs text-muted-foreground">
              Or add this key manually:
            </p>
            <div className="mt-2 flex items-center justify-between gap-2 rounded-lg border border-border bg-card p-2.5">
              <code className="truncate font-mono text-xs text-foreground">
                {setup.secret}
              </code>
              <button
                type="button"
                onClick={copySecret}
                aria-label="Copy secret key"
                className="flex size-8 shrink-0 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
              >
                {copied ? (
                  <Check aria-hidden="true" className="size-4 text-primary" />
                ) : (
                  <Copy aria-hidden="true" className="size-4" />
                )}
              </button>
            </div>
          </div>

          <div className="space-y-3">
            <p className="flex items-center gap-1.5 text-sm font-medium text-foreground">
              <KeyRound aria-hidden="true" className="size-4 text-primary" />
              Step 2 · Enter the 6-digit code
            </p>
            <OtpInput
              length={6}
              value={code}
              onChange={setCode}
              disabled={confirming}
              error={Boolean(error)}
              ariaLabel="Authenticator code"
            />
            {error ? (
              <p className="text-center text-xs font-medium text-destructive">
                {error}
              </p>
            ) : (
              <p className="text-center text-xs text-muted-foreground">
                Open your authenticator app and scan the code to generate a
                6-digit code.
              </p>
            )}
            <AuthButton
              type="button"
              className="w-full"
              loading={confirming}
              onClick={confirm}
            >
              Verify and continue
            </AuthButton>
          </div>
        </div>
      ) : (
        <div className="space-y-5">
          <div className="flex items-center gap-2 rounded-lg border border-primary/40 bg-primary/10 p-3">
            <Check aria-hidden="true" className="size-4 text-primary" />
            <p className="text-sm font-medium text-foreground">
              Authenticator verified. Back up your recovery codes.
            </p>
          </div>

          <div className="rounded-xl border border-border bg-muted/40 p-4">
            <p className="flex items-center gap-1.5 text-sm font-medium text-foreground">
              <ShieldAlert aria-hidden="true" className="size-4 text-primary" />
              Recovery codes
            </p>
            <p className="mt-1 text-xs text-muted-foreground">
              Store these in a safe place. Each works once to sign in if you
              lose your authenticator app.
            </p>
            <div className="mt-3 flex flex-wrap gap-2">
              <button
                type="button"
                onClick={copyCodes}
                aria-label="Copy recovery codes"
                className="inline-flex items-center gap-1.5 rounded-lg border border-border bg-card px-3 py-1.5 text-xs font-medium text-foreground transition-colors hover:border-primary/40 hover:bg-muted"
              >
                {codesCopied ? (
                  <Check aria-hidden="true" className="size-3.5 text-primary" />
                ) : (
                  <Copy aria-hidden="true" className="size-3.5" />
                )}
                {codesCopied ? "Copied" : "Copy all"}
              </button>
              <button
                type="button"
                onClick={downloadCodes}
                aria-label="Download recovery codes"
                className="inline-flex items-center gap-1.5 rounded-lg border border-border bg-card px-3 py-1.5 text-xs font-medium text-foreground transition-colors hover:border-primary/40 hover:bg-muted"
              >
                <Download aria-hidden="true" className="size-3.5" />
                Download
              </button>
            </div>
            <div className="mt-3 grid grid-cols-2 gap-1.5">
              {setup.backupCodes.map((backupCode) => (
                <code
                  key={backupCode}
                  className="rounded-md border border-border bg-card px-2 py-1.5 text-center font-mono text-xs text-foreground"
                >
                  {backupCode}
                </code>
              ))}
            </div>
            {regenerated ? (
              <p className="mt-3 text-center text-xs font-medium text-primary">
                New codes generated. Save them and delete the old list.
              </p>
            ) : null}
            {regenerateError ? (
              <p className="mt-3 text-center text-xs font-medium text-destructive">
                {regenerateError}
              </p>
            ) : null}
            <div className="mt-3 flex justify-end">
              <button
                type="button"
                onClick={() => {
                  if (confirmingRegenerate) {
                    setConfirmingRegenerate(false);
                    void regenerate();
                  } else {
                    setConfirmingRegenerate(true);
                  }
                }}
                disabled={regenerating}
                aria-label="Regenerate recovery codes"
                className={cn(
                  "inline-flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-xs font-medium transition-colors",
                  confirmingRegenerate
                    ? "border-destructive/60 bg-destructive/10 text-destructive hover:bg-destructive/15"
                    : "border-border bg-card text-foreground hover:border-primary/40 hover:bg-muted",
                )}
              >
                {regenerating ? (
                  <LoaderCircle aria-hidden="true" className="size-3.5 animate-spin" />
                ) : (
                  <RefreshCw aria-hidden="true" className="size-3.5" />
                )}
                {regenerating
                  ? "Regenerating…"
                  : confirmingRegenerate
                    ? "Regenerate anyway?"
                    : "Regenerate"}
              </button>
            </div>
          </div>

          <button
            type="button"
            onClick={() => setAcknowledged((value) => !value)}
            className={cn(
              "flex w-full items-center gap-2 rounded-lg border px-3 py-2.5 text-left text-sm transition-colors",
              acknowledged
                ? "border-primary/50 bg-primary/10"
                : "border-border hover:border-primary/40",
            )}
            aria-pressed={acknowledged}
          >
            <span
              className={cn(
                "flex size-4 shrink-0 items-center justify-center rounded-[4px] border transition-colors",
                acknowledged
                  ? "border-primary bg-primary text-primary-foreground"
                  : "border-input bg-card",
              )}
            >
              {acknowledged ? (
                <Check aria-hidden="true" className="size-3" />
              ) : null}
            </span>
            I&apos;ve saved my recovery codes somewhere safe.
          </button>

            <AuthButton
              type="button"
              className="w-full"
              loading={handingOff}
              disabled={!acknowledged}
              onClick={finish}
            >
              {handingOff ? "Opening your workspace…" : "Finish setup"}
            </AuthButton>
        </div>
      )}
    </div>
  );
}

export { MfaSetupStep };