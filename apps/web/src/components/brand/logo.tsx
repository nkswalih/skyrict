import type { SVGProps } from "react";

import { cn } from "@/lib/utils";

export type LogoMarkTone = "sky" | "erp" | "ai";

const TONES: Record<
    LogoMarkTone,
    { id: string; from: string; to: string; ink: string }
> = {
    sky: { id: "sky-mark", from: "#aedef1", to: "#4cb6e1", ink: "#0a2f3e" },
    erp: { id: "erp-mark", from: "#6ee7b7", to: "#34d399", ink: "#04211a" },
    ai: { id: "ai-mark", from: "#c7d2fe", to: "#6366f1", ink: "#1e1b4b" },
};

function LogoMark({
    className,
    tone = "sky",
}: {
    className?: string;
    tone?: LogoMarkTone;
}) {
    const colors = TONES[tone];
    return (
        <svg
            viewBox="0 0 32 32"
            role="img"
            aria-label="Skyrict"
            className={cn("size-8", className)}
        >
            <defs>
                <linearGradient id={colors.id} x1="0" y1="0" x2="1" y2="1">
                    <stop offset="0%" stopColor={colors.from} />
                    <stop offset="100%" stopColor={colors.to} />
                </linearGradient>
            </defs>
            <rect width="32" height="32" rx="9" fill={`url(#${colors.id})`} />
            {tone === "erp" ? (
                <g fill={colors.ink}>
                    <rect x="9" y="9" width="6" height="6" rx="1.6" />
                    <rect
                        x="17"
                        y="9"
                        width="6"
                        height="6"
                        rx="1.6"
                        opacity="0.45"
                    />
                    <rect
                        x="9"
                        y="17"
                        width="6"
                        height="6"
                        rx="1.6"
                        opacity="0.45"
                    />
                    <rect
                        x="17"
                        y="17"
                        width="6"
                        height="6"
                        rx="1.6"
                        opacity="0.45"
                    />
                </g>
            ) : tone === "ai" ? (
                <g fill={colors.ink}>
                    <circle
                        cx="16"
                        cy="16"
                        r="7"
                        fill="none"
                        stroke={colors.ink}
                        strokeWidth="1.7"
                        opacity="0.5"
                    />
                    <circle cx="16" cy="16" r="3.1" />
                    <circle cx="20.95" cy="11.05" r="1.7" />
                    <circle cx="11.05" cy="20.95" r="1.7" />
                </g>
            ) : (
                <>
                    <g
                        stroke={colors.ink}
                        strokeWidth="2.6"
                        strokeLinecap="round"
                    >
                        <path d="M9 22v-4" />
                        <path d="M14 22v-8" />
                        <path d="M19 22V11" />
                        <path d="M24 22v-13" />
                    </g>
                    <circle
                        cx="24"
                        cy="9"
                        r="2.1"
                        fill={colors.ink}
                        stroke="none"
                    />
                </>
            )}
        </svg>
    );
}

/**
 * Standalone AI orbit glyph that inherits `currentColor` for small inline
 * spots. Accepts the same presentation props as the lucide icons it
 * replaces (className, aria-hidden, ...), minus a background.
 */
function AiGlyph({ className, ...props }: SVGProps<SVGSVGElement>) {
    return (
        <svg
            viewBox="0 0 24 24"
            aria-hidden="true"
            className={cn("size-4", className)}
            {...props}
        >
            <circle
                cx="12"
                cy="12"
                r="8.5"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.8"
                opacity="0.5"
            />
            <circle cx="12" cy="12" r="3" fill="currentColor" />
            <circle cx="18" cy="6" r="1.7" fill="currentColor" />
            <circle cx="6" cy="18" r="1.7" fill="currentColor" />
        </svg>
    );
}

function Logo({
    className,
    wordmark = true,
    tone = "sky",
}: {
    className?: string;
    wordmark?: boolean;
    tone?: LogoMarkTone;
}) {
    return (
        <span className={cn("inline-flex items-center gap-2.5", className)}>
            <LogoMark className="size-7" tone={tone} />
            {wordmark ? (
                <span className="font-display text-lg font-semibold tracking-tight text-current">
                    Skyrict
                </span>
            ) : null}
        </span>
    );
}

export { Logo, LogoMark, AiGlyph };
