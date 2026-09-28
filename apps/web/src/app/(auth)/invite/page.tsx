import type { Metadata } from "next";
import Link from "next/link";
import {
    CheckCheck,
    CircleAlert,
    Clock3,
    MailX,
    ServerCrash,
} from "lucide-react";

import { InviteAcceptForm } from "@/features/auth/invite-accept-form";
import { AuthButton } from "@/lib/auth/AuthButton";
import { classifyInviteProblem } from "@/lib/invitation-problem-types";
import { apiBase } from "@/lib/server/auth";

export const metadata: Metadata = {
    title: "Join your workspace",
    description: "Accept your invitation to join a Skyrict workspace.",
};

export const dynamic = "force-dynamic";

interface VerifyData {
    email: string;
    roleName: string;
    organizationName: string | null;
    expiresAt: string;
}

type VerifyResult =
    | { status: "ok"; data: VerifyData }
    | { status: "expired" }
    | { status: "used" }
    | { status: "invalid" }
    | { status: "unavailable" };

async function verifyInvitation(token: string): Promise<VerifyResult> {
    try {
        const res = await fetch(
            `${apiBase()}/api/v1/invitations/verify?token=${encodeURIComponent(token)}`,
            { cache: "no-store" },
        );
        const payload = (await res.json().catch(() => ({}))) as {
            data?: {
                email?: string;
                role_name?: string;
                organization_name?: string | null;
                expires_at?: string;
            } | null;
            type?: string;
        };
        if (res.ok && payload.data) {
            return {
                status: "ok",
                data: {
                    email: payload.data.email ?? "",
                    roleName: payload.data.role_name ?? "",
                    organizationName: payload.data.organization_name ?? null,
                    expiresAt: payload.data.expires_at ?? "",
                },
            };
        }
        const problem = classifyInviteProblem(payload.type);
        if (problem === "expired") return { status: "expired" };
        if (problem === "alreadyUsed") return { status: "used" };
        return { status: "invalid" };
    } catch {
        return { status: "unavailable" };
    }
}

function StateCard({
    icon,
    title,
    body,
    actionLabel,
    actionHref,
}: {
    icon: React.ReactNode;
    title: string;
    body: string;
    actionLabel: string;
    actionHref: string;
}) {
    return (
        <div className="space-y-6">
            <div className="flex items-start gap-3">
                <div className="flex size-10 shrink-0 items-center justify-center rounded-lg bg-primary/15">
                    {icon}
                </div>
                <div className="space-y-1">
                    <h2 className="font-display text-lg font-semibold text-foreground">
                        {title}
                    </h2>
                    <p className="text-sm text-muted-foreground">{body}</p>
                </div>
            </div>
            <Link href={actionHref} className="block">
                <AuthButton className="w-full">{actionLabel}</AuthButton>
            </Link>
        </div>
    );
}

export default async function InvitePage({
    searchParams,
}: {
    searchParams: Promise<{ token?: string }>;
}) {
    const params = await searchParams;
    const token = params.token?.trim() ?? "";

    let content: React.ReactNode;

    if (!token) {
        content = (
            <StateCard
                icon={
                    <MailX aria-hidden="true" className="size-5 text-primary" />
                }
                title="Invitation link incomplete"
                body="The invitation link is missing its access token. Ask the person who invited you to resend it."
                actionLabel="Return to sign in"
                actionHref="/signin"
            />
        );
    } else {
        const result = await verifyInvitation(token);
        switch (result.status) {
            case "ok":
                content = (
                    <InviteAcceptForm
                        token={token}
                        email={result.data.email}
                        roleName={result.data.roleName}
                        organizationName={result.data.organizationName}
                    />
                );
                break;
            case "expired":
                content = (
                    <StateCard
                        icon={
                            <Clock3
                                aria-hidden="true"
                                className="size-5 text-primary"
                            />
                        }
                        title="Invitation expired"
                        body="This invitation link has expired. Ask the person who invited you to send a new one."
                        actionLabel="Return to sign in"
                        actionHref="/signin"
                    />
                );
                break;
            case "used":
                content = (
                    <StateCard
                        icon={
                            <CheckCheck
                                aria-hidden="true"
                                className="size-5 text-primary"
                            />
                        }
                        title="Invitation already used"
                        body="This invitation has already been accepted. Sign in to access your workspace."
                        actionLabel="Sign in"
                        actionHref="/signin"
                    />
                );
                break;
            case "unavailable":
                content = (
                    <StateCard
                        icon={
                            <ServerCrash
                                aria-hidden="true"
                                className="size-5 text-primary"
                            />
                        }
                        title="Something went wrong"
                        body="We couldn't check this invitation right now. Please try again in a moment."
                        actionLabel="Try again"
                        actionHref={`/invite?token=${encodeURIComponent(token)}`}
                    />
                );
                break;
            default:
                content = (
                    <StateCard
                        icon={
                            <CircleAlert
                                aria-hidden="true"
                                className="size-5 text-primary"
                            />
                        }
                        title="Invitation not found"
                        body="This invitation link isn't valid. It may be mistyped or the link may be broken ask the person who invited you to resend it."
                        actionLabel="Return to sign in"
                        actionHref="/signin"
                    />
                );
        }
    }

    return (
        <div className="space-y-8">
            <div className="space-y-2">
                <p className="font-mono text-xs uppercase tracking-[0.2em] text-primary">
                    Invitation
                </p>
                <h1 className="font-display text-2xl font-semibold text-foreground">
                    Join your workspace
                </h1>
                <p className="text-sm text-muted-foreground">
                    Set up your account to start using your workspace.
                </p>
            </div>

            {content}
        </div>
    );
}
