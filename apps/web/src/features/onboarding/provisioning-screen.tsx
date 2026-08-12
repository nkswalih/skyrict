"use client";

import { useEffect, useState } from "react";
import { Check, LoaderCircle } from "lucide-react";

import { cn } from "@/lib/utils";

const provisionSteps = [
  { label: "Provisioning tenant", detail: "Claiming your Skyrict workspace" },
  { label: "Creating identity", detail: "Encrypting your sign-in credentials" },
  {
    label: "Establishing organization",
    detail: "Registering your business profile",
  },
  { label: "Applying security policies", detail: "Enabling MFA and recovery" },
  { label: "Wiring workspace", detail: "Linking ERP and agents" },
];

const STEP_DURATION_MS = 2000;
const INITIAL_DELAY_MS = 600;

function ProvisioningScreen({ onComplete }: { onComplete: () => void }) {
  const [index, setIndex] = useState(-1);
  const [finished, setFinished] = useState(false);

  useEffect(() => {
    const timers: ReturnType<typeof setTimeout>[] = [];
    provisionSteps.forEach((_, stepIndex) => {
      timers.push(
        setTimeout(
          () => setIndex(stepIndex),
          INITIAL_DELAY_MS + stepIndex * STEP_DURATION_MS,
        ),
      );
    });
    const doneTimer = setTimeout(() => {
      setFinished(true);
      const navTimer = setTimeout(onComplete, 1200);
      timers.push(navTimer);
    }, INITIAL_DELAY_MS + provisionSteps.length * STEP_DURATION_MS + 400);
    timers.push(doneTimer);
    return () => timers.forEach(clearTimeout);
  }, [onComplete]);

  const progress = Math.max(0, Math.min(1, (index + 1) / provisionSteps.length));

  return (
    <div className="space-y-6">
      <div className="space-y-2 text-center">
        <div className="mx-auto flex size-12 items-center justify-center rounded-full bg-primary/20">
          {finished ? (
            <Check aria-hidden="true" className="size-6 text-primary" />
          ) : (
            <LoaderCircle
              aria-hidden="true"
              className="size-6 animate-spin text-primary"
            />
          )}
        </div>
        <h2 className="font-display text-xl font-semibold text-foreground">
          {finished ? "Workspace ready" : "Setting up your workspace"}
        </h2>
        <p className="text-sm text-muted-foreground">
          {finished
            ? "Almost done \n let's secure your sign-in with MFA."
            : "This takes a few seconds. Don't close this tab."}
        </p>
      </div>

      <div>
        <div className="h-1.5 w-full overflow-hidden rounded-full bg-border">
          <div
            className="h-full rounded-full bg-primary transition-all duration-500 ease-out"
            style={{ width: `${progress * 100}%` }}
          />
        </div>
        <p className="mt-1.5 text-right font-mono text-xs tabular-nums text-muted-foreground">
          {Math.round(progress * 100)}%
        </p>
      </div>

      <ol className="space-y-1" aria-live="polite">
        {provisionSteps.map((step, stepIndex) => {
          const done = stepIndex <= index;
          const active = stepIndex === index;
          return (
            <li
              key={step.label}
              className={cn(
                "flex items-start gap-3 rounded-lg px-3 py-2.5 transition-colors",
                active && "bg-muted/50",
              )}
            >
              {done ? (
                <span className="flex size-5 shrink-0 items-center justify-center rounded-full bg-primary text-primary-foreground">
                  <Check aria-hidden="true" className="size-3" />
                </span>
              ) : (
                <span className="flex size-5 shrink-0 items-center justify-center rounded-full border border-border bg-card">
                  {active ? (
                    <LoaderCircle
                      aria-hidden="true"
                      className="size-3 animate-spin text-primary"
                    />
                  ) : (
                    <span className="size-1.5 rounded-full bg-muted-foreground/40" />
                  )}
                </span>
              )}
              <div>
                <p
                  className={cn(
                    "text-sm font-medium",
                    done || active ? "text-foreground" : "text-muted-foreground/60",
                  )}
                >
                  {step.label}
                </p>
                <p className="text-xs text-muted-foreground">{step.detail}</p>
              </div>
            </li>
          );
        })}
      </ol>
    </div>
  );
}

export { ProvisioningScreen };
