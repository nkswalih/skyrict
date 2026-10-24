"use client";

import { useCallback, useEffect, useRef } from "react";

import { cn } from "@/lib/utils";

function OtpInput({
    length = 6,
    value,
    onChange,
    disabled = false,
    error = false,
    ariaLabel = "One-time code",
}: {
    length?: number;
    value: string;
    onChange: (value: string) => void;
    disabled?: boolean;
    error?: boolean;
    ariaLabel?: string;
}) {
    const refs = useRef<(HTMLInputElement | null)[]>([]);

    useEffect(() => {
        refs.current[0]?.focus();
    }, []);

    const getChars = useCallback(
        () => Array.from({ length }, (_, i) => value[i] ?? ""),
        [value, length],
    );

    const focusIndex = useCallback((index: number) => {
        const el = refs.current[index];
        if (el) {
            el.focus();
            el.select();
        }
    }, []);

    const handleChange = useCallback(
        (index: number, raw: string) => {
            const digits = raw.replace(/\D/g, "");
            const chars = getChars();
            if (digits.length > 1) {
                const pasted = digits.slice(0, length - index);
                const next = [...chars];
                pasted.split("").forEach((digit, i) => {
                    next[index + i] = digit;
                });
                onChange(next.join(""));
                focusIndex(Math.min(index + pasted.length - 1, length - 1));
                return;
            }
            const next = [...chars];
            if (digits.length === 0) {
                next[index] = "";
                onChange(next.join(""));
                if (index > 0) focusIndex(index - 1);
                return;
            }
            next[index] = digits[0];
            onChange(next.join(""));
            if (index < length - 1) focusIndex(index + 1);
        },
        [focusIndex, getChars, length, onChange],
    );

    const handleKeyDown = useCallback(
        (event: React.KeyboardEvent<HTMLInputElement>, index: number) => {
            if (event.key === "ArrowLeft") {
                event.preventDefault();
                if (index > 0) focusIndex(index - 1);
            }
            if (event.key === "ArrowRight") {
                event.preventDefault();
                if (index < length - 1) focusIndex(index + 1);
            }
            if (event.key === "Backspace" && !value[index] && index > 0) {
                event.preventDefault();
                focusIndex(index - 1);
            }
        },
        [focusIndex, length, value],
    );

    const handlePaste = useCallback(
        (event: React.ClipboardEvent<HTMLInputElement>) => {
            event.preventDefault();
            const digits = event.clipboardData
                .getData("text")
                .replace(/\D/g, "")
                .slice(0, length);
            if (digits) {
                onChange(digits);
                focusIndex(Math.min(digits.length - 1, length - 1));
            }
        },
        [focusIndex, length, onChange],
    );

    return (
        <div
            className="flex items-center justify-between gap-2"
            role="group"
            aria-label={ariaLabel}
        >
            {Array.from({ length }, (_, index) => (
                <input
                    key={index}
                    ref={(el) => {
                        refs.current[index] = el;
                    }}
                    inputMode="numeric"
                    autoComplete="one-time-code"
                    maxLength={1}
                    value={getChars()[index]}
                    onChange={(event) =>
                        handleChange(index, event.target.value)
                    }
                    onKeyDown={(event) => handleKeyDown(event, index)}
                    onPaste={handlePaste}
                    disabled={disabled}
                    aria-label={`${ariaLabel} digit ${index + 1}`}
                    aria-invalid={error}
                    className={cn(
                        "h-14 w-full rounded-lg border bg-card text-center font-mono text-xl tabular-nums shadow-xs outline-none transition-colors",
                        "focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/30",
                        "disabled:cursor-not-allowed disabled:opacity-50",
                        error
                            ? "border-destructive"
                            : "border-border hover:border-foreground/60",
                    )}
                />
            ))}
        </div>
    );
}

export { OtpInput };
