"use client";

import { Spinner } from "@/components/ui/spinner";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import {
    Check,
    Copy,
    MailPlus,
    Plus,
    UserPlus,
} from "lucide-react";

import { PageHeader } from "@/components/dashboard/shared/page-header";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
    Select,
    SelectContent,
    SelectItem,
    SelectSeparator,
    SelectTrigger,
    SelectValue,
} from "@/components/ui/select";
import { useModuleAccess } from "@/lib/access/modules";
import { ApiError } from "@/lib/api/http";
import {
    createInvitation,
    expireInvitation,
    listInvitations,
    listRoles,
    roleDisplayName,
    type InvitationCreated,
    type InvitationSummary,
    type RoleSummary,
} from "@/lib/api/identity-api";
import { invitationState, type InvitationStatus } from "@/lib/invitation-status";
import { ListSkeleton } from "@/components/ui/page-skeletons";
import { cn, copyToClipboard } from "@/lib/utils";
import { deriveApex } from "@/lib/auth/apex";

type Status =
    | { state: "loading" }
    | { state: "error"; message: string }
    | {
          state: "ready";
          invitations: InvitationSummary[];
          roles: RoleSummary[];
          busy: string | null;
      };

function formatInvitedAt(value: string): string {
    return new Date(value).toLocaleDateString(undefined, {
        month: "short",
        day: "numeric",
        year: "numeric",
    });
}

function initialsFor(email: string): string {
    const [local] = email.split("@");
    const parts = (local ?? "").split(/[._-]/).filter(Boolean);
    if (parts.length > 1) {
        return `${parts[0][0] ?? ""}${parts[1][0] ?? ""}`.toUpperCase();
    }
    return (local ?? "").slice(0, 2).toUpperCase() || "SK";
}

const statusConfig: Record<
    InvitationStatus,
    { label: string; dot: string; chip: string }
> = {
    used: {
        label: "Joined",
        dot: "bg-emerald-500",
        chip: "bg-emerald-500/10 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-300",
    },
    expired: {
        label: "Expired",
        dot: "bg-muted-foreground/50",
        chip: "bg-muted text-muted-foreground",
    },
    pending: {
        label: "Awaiting",
        dot: "bg-primary",
        chip: "bg-primary/10 text-primary",
    },
};

function StatusBadge({ state }: { state: InvitationStatus }) {
    const config = statusConfig[state];
    return (
        <span
            className={cn(
                "inline-flex shrink-0 items-center gap-1.5 rounded-full px-2 py-0.5 text-xs font-medium",
                config.chip,
            )}
        >
            <span
                aria-hidden="true"
                className={cn("size-1.5 rounded-full", config.dot)}
            />
            {config.label}
        </span>
    );
}

function SkeletonRows() {
    return <ListSkeleton rows={3} />;
}

/** `{slug}.signin.{apex}/invite?token=...` link for a freshly created invite. */
function inviteLink(token: string): string {
    const hostname = window.location.hostname;
    const signinHost = `${hostname.split(".")[0]}.signin.${deriveApex(hostname)}`;
    const port = window.location.port ? `:${window.location.port}` : "";
    return `${window.location.protocol}//${signinHost}${port}/invite?token=${encodeURIComponent(token)}`;
}

export default function InviteClient() {
    const router = useRouter();
    const access = useModuleAccess();
    const { status: accessStatus, permissions } = access;
    const canInvite =
        permissions.includes("*") || permissions.includes("invitations:send");

    const [status, setStatus] = useState<Status>({ state: "loading" });
    const [email, setEmail] = useState("");
    const [roleName, setRoleName] = useState("");
    const [submitting, setSubmitting] = useState(false);
    const [copied, setCopied] = useState(false);
    const [formError, setFormError] = useState<string | null>(null);
    const [actionError, setActionError] = useState<string | null>(null);
    const [created, setCreated] = useState<InvitationCreated | null>(null);

    const load = useCallback(async () => {
        setStatus({ state: "loading" });
        try {
            const [invitations, roles] = await Promise.all([
                listInvitations(),
                listRoles(),
            ]);
            setStatus({ state: "ready", invitations, roles, busy: null });
        } catch (error) {
            const message =
                error instanceof ApiError
                    ? error.message
                    : "Could not load invitations.";
            setStatus({ state: "error", message });
        }
    }, []);

    useEffect(() => {
        if (canInvite && accessStatus !== "loading") void load();
    }, [accessStatus, canInvite, load]);

    const defaultRole = useMemo(
        () =>
            status.state === "ready" && status.roles.length > 0
                ? status.roles[0].name
                : "",
        [status],
    );

    useEffect(() => {
        setRoleName((current) => current || defaultRole);
    }, [defaultRole]);

    async function onSubmit(event: React.FormEvent<HTMLFormElement>) {
        event.preventDefault();
        setFormError(null);
        setCreated(null);
        setSubmitting(true);
        try {
            const result = await createInvitation(email, roleName);
            setEmail("");
            setCreated(result);
            await load();
        } catch (error) {
            setFormError(
                error instanceof ApiError
                    ? error.message
                    : "The invitation could not be sent.",
            );
        } finally {
            setSubmitting(false);
        }
    }

    async function onExpire(invitationId: string) {
        if (status.state !== "ready") return;
        setStatus({ ...status, busy: invitationId });
        setActionError(null);
        try {
            await expireInvitation(invitationId);
            await load();
        } catch (error) {
            setActionError(
                error instanceof ApiError
                    ? error.message
                    : "The invitation could not be expired.",
            );
            setStatus((current) =>
                current.state === "ready"
                    ? { ...current, busy: null }
                    : current,
            );
        }
    }

    async function copyInviteLink(url: string) {
        try {
            await copyToClipboard(url);
            setCopied(true);
            setTimeout(() => setCopied(false), 2000);
        } catch {
            // Clipboard unavailable - the link stays visible for manual copying.
        }
    }

    const createdUrl = created ? inviteLink(created.token) : "";

    return (
        <div className="space-y-6">
            <PageHeader
                title="Invite member"
                description="Invite a member with a link and keep an eye on pending invitations."
                icon={UserPlus}
            />

            {actionError ? (
                <p
                    role="alert"
                    className="rounded-lg border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm font-medium text-destructive"
                >
                    {actionError}
                </p>
            ) : null}

            <div className="grid items-start gap-6 lg:grid-cols-[21rem_minmax(0,1fr)]">
                <section className="rounded-xl border border-border bg-card p-5 lg:sticky lg:top-6">
                    <div className="flex items-center gap-3">
                        <div className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
                            <UserPlus aria-hidden="true" className="size-4.5" />
                        </div>
                        <div className="min-w-0">
                            <h2 className="font-display text-sm font-semibold text-foreground">
                                Invite a member
                            </h2>
                            <p className="text-xs text-muted-foreground">
                                They will get a link to join your workspace.
                            </p>
                        </div>
                    </div>

                    <form
                        onSubmit={(event) => void onSubmit(event)}
                        className="mt-4 space-y-3"
                    >
                        <div className="space-y-1.5">
                            <Label htmlFor="invite-email">Email address</Label>
                            <Input
                                id="invite-email"
                                type="email"
                                required
                                autoComplete="email"
                                value={email}
                                onChange={(event) =>
                                    setEmail(event.target.value)
                                }
                                placeholder="teammate@example.com"
                                aria-invalid={formError ? true : undefined}
                            />
                        </div>
                        <div className="space-y-1.5">
                            <Label htmlFor="invite-role">Role</Label>
                            <Select
                                value={roleName}
                                onValueChange={(value) => {
                                    if (value === "__create_custom_role__") {
                                        router.push("/roles");
                                        return;
                                    }
                                    setRoleName(value);
                                }}
                            >
                                <SelectTrigger
                                    id="invite-role"
                                    className="w-full"
                                >
                                    <SelectValue placeholder="Choose a role" />
                                </SelectTrigger>
                                <SelectContent>
                                    {status.state === "ready" &&
                                    status.roles.length > 0
                                        ? status.roles.map((role) => (
                                              <SelectItem
                                                  key={role.id}
                                                  value={role.name}
                                              >
                                                  {roleDisplayName(role.name)}
                                              </SelectItem>
                                          ))
                                        : null}
                                    <SelectSeparator />
                                    <SelectItem value="__create_custom_role__">
                                        <span className="flex items-center gap-2 text-primary">
                                            <Plus
                                                aria-hidden="true"
                                                className="size-3.5"
                                            />
                                            Create custom role
                                        </span>
                                    </SelectItem>
                                </SelectContent>
                            </Select>
                        </div>
                        {formError ? (
                            <p
                                role="alert"
                                className="text-sm font-medium text-destructive"
                            >
                                {formError}
                            </p>
                        ) : null}
                        <Button
                            type="submit"
                            className="w-full"
                            disabled={submitting || !roleName}
                        >
                            {submitting ? (
                                <Spinner
                                    aria-hidden="true"
                                    className="size-4"
                                />
                            ) : (
                                <UserPlus
                                    aria-hidden="true"
                                    className="size-4"
                                />
                            )}
                            Send invite
                        </Button>
                    </form>

                    {created ? (
                        <div className="mt-4 space-y-2 rounded-lg border border-primary/30 bg-primary/5 p-3">
                            <p className="text-sm font-medium text-foreground">
                                Invitation sent to {created.email}
                            </p>
                            <p className="text-xs text-muted-foreground">
                                {roleDisplayName(created.roleName)} · the link
                                below works once.
                            </p>
                            <div className="flex items-center gap-1.5">
                                <code
                                    title={createdUrl}
                                    className="min-w-0 flex-1 truncate rounded-md border border-border bg-background/70 px-2 py-1 font-mono text-xs text-foreground"
                                >
                                    {createdUrl}
                                </code>
                                <Button
                                    type="button"
                                    variant="outline"
                                    size="icon-sm"
                                    aria-label="Copy invite link"
                                    title="Copy invite link"
                                    onClick={() =>
                                        void copyInviteLink(createdUrl)
                                    }
                                >
                                    {copied ? (
                                        <Check
                                            aria-hidden="true"
                                            className="text-emerald-600 dark:text-emerald-400"
                                        />
                                    ) : (
                                        <Copy aria-hidden="true" />
                                    )}
                                </Button>
                            </div>
                        </div>
                    ) : null}
                </section>

                <section className="rounded-xl border border-border bg-card">
                    <header className="flex items-center justify-between gap-3 border-b border-border px-5 py-3.5">
                        <h2 className="flex items-center gap-2 font-display text-sm font-semibold text-foreground">
                            <MailPlus
                                aria-hidden="true"
                                className="size-4 text-primary"
                            />
                            Invitations
                        </h2>
                        {status.state === "ready" ? (
                            <span className="rounded-full bg-muted px-2 py-0.5 text-xs font-medium text-muted-foreground tabular-nums">
                                {status.invitations.length}
                            </span>
                        ) : null}
                    </header>

                    <div className="p-5">
                        {status.state === "loading" ? <SkeletonRows /> : null}

                        {status.state === "error" ? (
                            <div className="flex flex-col items-center justify-center px-6 py-10 text-center">
                                <p className="text-sm font-medium text-destructive">
                                    {status.message}
                                </p>
                                <Button
                                    type="button"
                                    variant="outline"
                                    size="sm"
                                    className="mt-3"
                                    onClick={() => void load()}
                                >
                                    Try again
                                </Button>
                            </div>
                        ) : null}

                        {status.state === "ready" &&
                        status.invitations.length === 0 ? (
                            <div className="flex flex-col items-center justify-center px-6 py-10 text-center">
                                <div className="flex size-12 items-center justify-center rounded-2xl bg-primary/10 text-primary">
                                    <UserPlus
                                        aria-hidden="true"
                                        className="size-5"
                                    />
                                </div>
                                <h3 className="mt-3 font-display text-sm font-semibold text-foreground">
                                    No invites yet
                                </h3>
                                <p className="mt-1 max-w-60 text-xs leading-relaxed text-muted-foreground">
                                    Invite your first teammate with the panel on
                                    the left. They will get a link to join.
                                </p>
                            </div>
                        ) : null}

                        {status.state === "ready" &&
                        status.invitations.length > 0 ? (
                            <ul className="divide-y divide-border">
                                {status.invitations.map((item) => {
                                    const state = invitationState(item);
                                    return (
                                        <li
                                            key={item.id}
                                            className="flex items-center gap-3 py-3.5 transition-colors first:pt-0 last:pb-0"
                                        >
                                            <div className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-xs font-semibold text-primary">
                                                {initialsFor(item.email)}
                                            </div>
                                            <div className="min-w-0 flex-1">
                                                <p className="truncate text-sm font-medium text-foreground">
                                                    {item.email}
                                                </p>
                                                <p className="truncate text-xs text-muted-foreground">
                                                    {roleDisplayName(
                                                        item.roleName,
                                                    )}{" "}
                                                    · invited{" "}
                                                    {formatInvitedAt(
                                                        item.createdAt,
                                                    )}
                                                </p>
                                            </div>
                                            <StatusBadge state={state} />
                                            {state === "pending" ? (
                                                <Button
                                                    type="button"
                                                    variant="ghost"
                                                    size="sm"
                                                    disabled={
                                                        status.busy !== null
                                                    }
                                                    onClick={() =>
                                                        void onExpire(item.id)
                                                    }
                                                >
                                                    {status.busy === item.id ? (
                                                        <Spinner
                                                            aria-hidden="true"
                                                            className="size-3.5"
                                                        />
                                                    ) : null}
                                                    Expire
                                                </Button>
                                            ) : null}
                                        </li>
                                    );
                                })}
                            </ul>
                        ) : null}
                    </div>
                </section>
            </div>
        </div>
    );
}
