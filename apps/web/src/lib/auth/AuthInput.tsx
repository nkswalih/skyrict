"use client";

import { forwardRef } from "react";
import type { LucideIcon } from "lucide-react";

import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { cn } from "@/lib/utils";

type AuthInputProps = React.ComponentProps<typeof Input> & {
    label: string;
    error?: string;
    hint?: string;
    icon?: LucideIcon;
    trailing?: React.ReactNode;
    hideLabel?: boolean;
};

const AuthInput = forwardRef<HTMLInputElement, AuthInputProps>(
    function AuthInput(
        {
            label,
            error,
            hint,
            trailing,
            id,
            className,
            hideLabel = false,
            ...props
        },
        ref,
    ) {
        return (
            <div className="space-y-1.5">
                <Label
                    htmlFor={id}
                    className={hideLabel ? "sr-only" : undefined}
                >
                    {label}
                </Label>
                <div className="relative">
                    <Input
                        ref={ref}
                        id={id}
                        aria-invalid={error ? true : undefined}
                        aria-describedby={
                            error || hint ? `${id}-desc` : undefined
                        }
                        className={cn(
                            "h-10",
                            trailing && "pr-10",
                            error && "pr-3",
                            className,
                        )}
                        {...props}
                    />
                    {trailing ? (
                        <span className="absolute top-0 right-0 flex h-full items-center">
                            {trailing}
                        </span>
                    ) : null}
                </div>
                <div id={`${id}-desc`} className="space-y-0.5">
                    {error ? (
                        <p className="text-xs font-medium text-destructive">
                            {error}
                        </p>
                    ) : hint ? (
                        <p className="text-xs text-muted-foreground">{hint}</p>
                    ) : null}
                </div>
            </div>
        );
    },
);

export { AuthInput, type AuthInputProps };
