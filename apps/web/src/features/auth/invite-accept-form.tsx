"use client";

import { useEffect, useRef, useState } from "react";
import { useForm } from "react-hook-form";
import { useRouter } from "next/navigation";
import { zodResolver } from "@hookform/resolvers/zod";
import { Lock, Mail, UserRound } from "lucide-react";
import { z } from "zod";

import { NETWORK_ERROR_MESSAGE } from "@/lib/api/error-messages";
import { AuthButton } from "@/lib/auth/AuthButton";
import { AuthInput } from "@/lib/auth/AuthInput";

const MAX_AVATAR_BYTES = 10 * 1024 * 1024;
const ALLOWED_AVATAR_MIME_TYPES = new Set([
    "image/jpeg",
    "image/png",
    "image/webp",
    "image/gif",
]);

const acceptSchema = z
    .object({
        fullName: z.string().trim().min(2, "Enter your full name"),
        password: z
            .string()
            .regex(
                /^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[^A-Za-z0-9]).{12,}$/,
                "Use at least 12 characters with uppercase, lowercase, a number, and a special character.",
            ),
        confirmPassword: z.string().min(1, "Confirm your password"),
    })
    .refine((values) => values.password === values.confirmPassword, {
        path: ["confirmPassword"],
        message: "Passwords do not match",
    });

type AcceptValues = z.infer<typeof acceptSchema>;

function InviteAcceptForm({
    token,
    email,
    roleName,
    organizationName,
}: {
    token: string;
    email: string;
    roleName: string;
    organizationName: string | null;
}) {
    const router = useRouter();
    const fileInputRef = useRef<HTMLInputElement>(null);
    const [avatar, setAvatar] = useState<File | null>(null);
    const [avatarError, setAvatarError] = useState<string | null>(null);
    const [submitError, setSubmitError] = useState<string | null>(null);
    const [fatal, setFatal] = useState<"expired" | "used" | null>(null);
    const [previewUrl, setPreviewUrl] = useState<string | null>(null);

    const {
        register,
        handleSubmit,
        formState: { errors, isSubmitting },
    } = useForm<AcceptValues>({
        resolver: zodResolver(acceptSchema),
        defaultValues: { fullName: "", password: "", confirmPassword: "" },
    });

    useEffect(() => {
        return () => {
            if (previewUrl) URL.revokeObjectURL(previewUrl);
        };
    }, [previewUrl]);

    function handleFileChange(event: React.ChangeEvent<HTMLInputElement>) {
        const file = event.target.files?.[0];
        event.target.value = "";
        setAvatarError(null);
        if (!file) return;
        if (!ALLOWED_AVATAR_MIME_TYPES.has(file.type)) {
            setAvatar(null);
            if (previewUrl) URL.revokeObjectURL(previewUrl);
            setPreviewUrl(null);
            setAvatarError("Please choose a JPG, PNG, WEBP, or GIF image.");
            return;
        }
        if (file.size > MAX_AVATAR_BYTES) {
            setAvatar(null);
            if (previewUrl) URL.revokeObjectURL(previewUrl);
            setPreviewUrl(null);
            setAvatarError("Image must be 10 MB or smaller.");
            return;
        }
        if (!file.type.startsWith("image/")) {
            setAvatar(null);
            if (previewUrl) URL.revokeObjectURL(previewUrl);
            setPreviewUrl(null);
            setAvatarError("Please choose an image file.");
            return;
        }
        if (previewUrl) URL.revokeObjectURL(previewUrl);
        setAvatar(file);
        setPreviewUrl(URL.createObjectURL(file));
    }

    function handleRemoveAvatar() {
        if (previewUrl) URL.revokeObjectURL(previewUrl);
        setAvatar(null);
        setPreviewUrl(null);
        setAvatarError(null);
    }

    async function onSubmit(values: AcceptValues) {
        setSubmitError(null);
        setFatal(null);

        const form = new FormData();
        form.append("token", token);
        form.append("email", email);
        form.append("full_name", values.fullName);
        form.append("password", values.password);
        if (avatar) form.append("avatar", avatar);

        let res: Response;
        try {
            res = await fetch("/api/auth/invite/accept", {
                method: "POST",
                body: form,
                cache: "no-store",
            });
        } catch {
            setSubmitError(NETWORK_ERROR_MESSAGE);
            return;
        }

        const payload = (await res.json().catch(() => ({}))) as {
            error?: string;
            type?: string | null;
        };
        if (!res.ok) {
            const type = payload.type ?? "";
            if (type.endsWith("/invitation-expired")) {
                setFatal("expired");
            } else if (type.endsWith("/invitation-already-used")) {
                setFatal("used");
            } else {
                setSubmitError(
                    payload.error ??
                        "Could not accept the invitation. Please try again.",
                );
            }
            return;
        }

        router.push("/signin?accepted=1");
    }

    if (fatal) {
        return (
            <div className="space-y-6">
                <div className="flex items-start gap-3">
                    <div className="flex size-10 shrink-0 items-center justify-center rounded-lg bg-primary/15">
                        <Lock
                            aria-hidden="true"
                            className="size-5 text-primary"
                        />
                    </div>
                    <div className="space-y-1">
                        <h2 className="font-display text-lg font-semibold text-foreground">
                            {fatal === "expired"
                                ? "Invitation expired"
                                : "Invitation already used"}
                        </h2>
                        <p className="text-sm text-muted-foreground">
                            {fatal === "expired"
                                ? "This invitation link has expired. Ask the person who invited you to send a new one."
                                : "This invitation has already been accepted. Sign in to access your workspace."}
                        </p>
                    </div>
                </div>
                <AuthButton
                    type="button"
                    className="w-full"
                    onClick={() => router.push("/signin")}
                >
                    Sign in
                </AuthButton>
            </div>
        );
    }

    return (
        <form
            onSubmit={handleSubmit(onSubmit)}
            className="space-y-5"
            noValidate
        >
            <div className="rounded-lg border border-border bg-muted/40 px-3 py-2.5">
                <p className="text-sm font-medium text-foreground">
                    {organizationName
                        ? `You've been invited to ${organizationName}`
                        : "You've been invited to join a workspace"}
                </p>
                <p className="text-xs text-muted-foreground">
                    You&apos;ll be added as{" "}
                    <span className="font-medium">{roleName}</span>.
                </p>
            </div>

            <AuthInput
                label="Email"
                id="email"
                type="email"
                autoComplete="off"
                icon={Mail}
                value={email}
                disabled
            />

            <AuthInput
                label="Full name"
                id="fullName"
                type="text"
                autoComplete="name"
                placeholder="Full name"
                icon={UserRound}
                error={errors.fullName?.message}
                {...register("fullName")}
            />

            <AuthInput
                label="Password"
                id="password"
                type="password"
                autoComplete="new-password"
                placeholder="Password"
                icon={Lock}
                hint="At least 12 characters with uppercase, lowercase, a number, and a special character."
                error={errors.password?.message}
                {...register("password")}
            />

            <AuthInput
                label="Confirm password"
                id="confirmPassword"
                type="password"
                autoComplete="new-password"
                placeholder="Confirm password"
                icon={Lock}
                error={errors.confirmPassword?.message}
                {...register("confirmPassword")}
            />

            <div className="space-y-1.5">
                <div className="flex items-center gap-4">
                    {previewUrl ? (
                        <div
                            role="img"
                            aria-label="Avatar preview"
                            className="size-16 shrink-0 rounded-full bg-cover bg-center ring-1 ring-border"
                            style={{ backgroundImage: `url("${previewUrl}")` }}
                        />
                    ) : (
                        <div className="flex size-16 shrink-0 items-center justify-center rounded-full bg-primary/15 text-xl font-semibold text-primary-foreground">
                            {email.slice(0, 2).toUpperCase()}
                        </div>
                    )}
                    <div className="flex min-w-0 flex-col gap-2">
                        <div className="flex flex-wrap items-center gap-2">
                            <button
                                type="button"
                                onClick={() => fileInputRef.current?.click()}
                                disabled={isSubmitting}
                                className="rounded-lg border border-border px-3 py-1.5 text-sm font-medium text-foreground transition-colors hover:bg-muted/60 disabled:opacity-50"
                            >
                                Add photo
                            </button>
                            {avatar && (
                                <button
                                    type="button"
                                    onClick={handleRemoveAvatar}
                                    disabled={isSubmitting}
                                    className="rounded-lg px-3 py-1.5 text-sm font-medium text-destructive transition-colors hover:bg-destructive/10 disabled:opacity-50"
                                >
                                    Remove
                                </button>
                            )}
                        </div>
                        <p className="text-xs text-muted-foreground">
                            Optional. Square image, resized and optimized
                            automatically.
                        </p>
                        {avatarError && (
                            <p className="text-xs text-destructive">
                                {avatarError}
                            </p>
                        )}
                    </div>
                </div>
                <input
                    ref={fileInputRef}
                    type="file"
                    accept="image/*"
                    aria-label="Choose a profile photo"
                    className="hidden"
                    onChange={(event) => void handleFileChange(event)}
                />
            </div>

            {submitError ? (
                <div
                    role="alert"
                    className="rounded-lg border border-destructive/30 bg-destructive/5 px-3 py-2 text-sm text-destructive"
                >
                    {submitError}
                </div>
            ) : null}

            <AuthButton type="submit" className="w-full" loading={isSubmitting}>
                Accept invitation
            </AuthButton>

            <div className="space-y-3">
                <button
                    type="button"
                    onClick={() => router.push("/signin")}
                    className="w-full text-center text-sm text-muted-foreground underline-offset-4 hover:underline"
                >
                    Sign in instead
                </button>
            </div>
        </form>
    );
}

export { InviteAcceptForm };
