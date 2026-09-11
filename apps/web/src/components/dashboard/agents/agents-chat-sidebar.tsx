"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
    ArrowLeft,
    MessageSquareText,
    MoreHorizontal,
    Pencil,
    Pin,
    PinOff,
    ShieldCheck,
    Sparkles,
    SquarePen,
    Trash2,
} from "lucide-react";

import { Logo } from "@/components/brand/logo";
import { Button } from "@/components/ui/button";
import { UserMenu } from "@/components/dashboard/workspace/user-menu";
import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogFooter,
    DialogHeader,
    DialogTitle,
} from "@/components/ui/dialog";
import {
    DropdownMenu,
    DropdownMenuContent,
    DropdownMenuItem,
    DropdownMenuLabel,
    DropdownMenuSeparator,
    DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import {
    deleteConversation,
    getConversations,
    renameConversation,
    setConversationPinned,
} from "@/lib/api/agents-api";
import { useSession } from "@/lib/auth/session";
import { CONVERSATION_LIST_CHANGED_EVENT } from "@/lib/chat/conversation-list-events";
import { cn } from "@/lib/utils";
import type { Conversation } from "@/lib/api/agents-api";

function isActive(pathname: string, id: string): boolean {
    const normalized =
        pathname === "/"
            ? "/dashboard"
            : pathname.startsWith("/dashboard")
              ? pathname
              : `/dashboard${pathname}`;
    return normalized === `/dashboard/agents/c/${id}`;
}

function ConversationRow({
    conversation,
    active,
    collapsed,
    onSelect,
    onRename,
    onDelete,
    onTogglePin,
}: {
    conversation: Conversation;
    active: boolean;
    collapsed: boolean;
    onSelect: () => void;
    onRename: () => void;
    onDelete: () => void;
    onTogglePin: () => void;
}) {
    const pinned = Boolean(conversation.pinned);

    return (
        <div
            className={cn(
                "group flex items-center rounded-lg text-sm transition-colors",
                active
                    ? "bg-sidebar-accent font-medium text-sidebar-accent-foreground"
                    : "text-foreground hover:bg-muted/60",
            )}
        >
            <Link
                href={`/dashboard/agents/c/${conversation.id}`}
                onClick={onSelect}
                aria-current={active ? "page" : undefined}
                title={collapsed ? conversation.title : undefined}
                className={cn(
                    "flex min-w-0 flex-1 items-center gap-2",
                    collapsed ? "justify-center px-0 py-2" : "px-2.5 py-2",
                )}
            >
                {collapsed ? (
                    <MessageSquareText
                        aria-hidden="true"
                        className="size-4 shrink-0"
                    />
                ) : (
                    <>
                        {pinned ? (
                            <Pin
                                aria-hidden="true"
                                className="size-3.5 shrink-0 opacity-70"
                            />
                        ) : null}
                        <span className="min-w-0 flex-1 truncate">
                            {conversation.title}
                        </span>
                    </>
                )}
            </Link>

            {!collapsed && (
                <div className="mr-1 flex shrink-0 items-center opacity-0 transition-opacity group-hover:opacity-100 group-focus-within:opacity-100">
                    {/* Quick pin/unpin action */}
                    <button
                        type="button"
                        tabIndex={-1}
                        onClick={(event) => {
                            event.preventDefault();
                            onTogglePin();
                        }}
                        aria-label={
                            pinned
                                ? `Unpin ${conversation.title}`
                                : `Pin ${conversation.title}`
                        }
                        title={pinned ? "Unpin chat" : "Pin chat"}
                        className="flex size-6 items-center justify-center rounded-md text-current/50 transition-colors hover:text-current focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-current/50"
                    >
                        {pinned ? (
                            <PinOff aria-hidden="true" className="size-3.5" />
                        ) : (
                            <Pin aria-hidden="true" className="size-3.5" />
                        )}
                    </button>

                    {/* More actions: rename, delete, pin */}
                    <DropdownMenu>
                        <DropdownMenuTrigger asChild>
                            <button
                                type="button"
                                tabIndex={-1}
                                onClick={(event) => event.preventDefault()}
                                aria-label={`Options for ${conversation.title}`}
                                className="flex size-6 items-center justify-center rounded-md text-current/50 transition-colors hover:text-current focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-current/50 data-[state=open]:bg-current/10"
                            >
                                <MoreHorizontal
                                    aria-hidden="true"
                                    className="size-4"
                                />
                            </button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="end">
                            <DropdownMenuItem onSelect={onRename}>
                                <Pencil aria-hidden="true" />
                                Rename
                            </DropdownMenuItem>
                            <DropdownMenuItem onSelect={onTogglePin}>
                                {pinned ? (
                                    <PinOff aria-hidden="true" />
                                ) : (
                                    <Pin aria-hidden="true" />
                                )}
                                {pinned ? "Unpin chat" : "Pin chat"}
                            </DropdownMenuItem>
                            <DropdownMenuSeparator />
                            <DropdownMenuItem
                                variant="destructive"
                                onSelect={onDelete}
                            >
                                <Trash2 aria-hidden="true" />
                                Delete
                            </DropdownMenuItem>
                        </DropdownMenuContent>
                    </DropdownMenu>
                </div>
            )}
        </div>
    );
}

function NewChatButton({
    collapsed,
    onNavigate,
}: {
    collapsed: boolean;
    onNavigate: () => void;
}) {
    const router = useRouter();
    return (
        <Button
            variant="ghost"
            className={cn(
                "w-full gap-2 text-muted-foreground hover:bg-muted/60 hover:text-foreground",
                collapsed ? "justify-center px-0" : "justify-start",
            )}
            title={collapsed ? "New chat" : undefined}
            onClick={() => {
                onNavigate();
                router.push("/dashboard/agents");
            }}
        >
            <SquarePen aria-hidden="true" className="size-4" />
            {!collapsed ? "New chat" : null}
        </Button>
    );
}

export function AgentsChatSidebar({
    mobileOpen,
    onCloseMobile,
    collapsed,
}: {
    mobileOpen: boolean;
    onCloseMobile: () => void;
    collapsed: boolean;
}) {
    const pathname = usePathname();
    const router = useRouter();
    const { status } = useSession();
    const [conversations, setConversations] = useState<Conversation[]>([]);
    const [renameTarget, setRenameTarget] = useState<Conversation | null>(null);
    const [renameValue, setRenameValue] = useState("");

    const load = useCallback(() => {
        getConversations()
            .then(setConversations)
            .catch(() => setConversations([]));
    }, []);

    // Refresh when a conversation is created, the active one changes,
    // or the session hydrates (first load needs the token to exist).
    useEffect(() => {
        if (status === "authenticated") load();
    }, [pathname, load, status]);

    // Refetch when a conversation's metadata changes server-side (e.g. the AI
    // title lands a moment after a turn completes) so titles update live
    // without a manual refresh.
    useEffect(() => {
        const onConversationListChanged = () => load();
        window.addEventListener(
            CONVERSATION_LIST_CHANGED_EVENT,
            onConversationListChanged,
        );
        return () =>
            window.removeEventListener(
                CONVERSATION_LIST_CHANGED_EVENT,
                onConversationListChanged,
            );
    }, [load]);

    const handleRename = useCallback((conversation: Conversation) => {
        setRenameTarget(conversation);
        setRenameValue(conversation.title);
    }, []);

    const submitRename = useCallback(() => {
        const target = renameTarget;
        const value = renameValue.trim();
        setRenameTarget(null);
        if (!target || !value || value === target.title) return;
        void renameConversation(target.id, value).then(() => load());
    }, [renameTarget, renameValue, load]);

    const handleDelete = useCallback(
        (conversation: Conversation) => {
            void deleteConversation(conversation.id).then(() => {
                // If the deleted conversation is the one we are viewing, leave the page.
                if (isActive(pathname, conversation.id)) {
                    router.push("/dashboard/agents");
                }
                load();
            });
        },
        [pathname, router, load],
    );

    const handleTogglePin = useCallback(
        (conversation: Conversation) => {
            // Pinning re-sorts the list; optimistically update so the row moves
            // immediately, then reconcile with the server response.
            setConversations((previous) =>
                previous
                    .map((item) =>
                        item.id === conversation.id
                            ? { ...item, pinned: !Boolean(item.pinned) }
                            : item,
                    )
                    .sort(
                        (a, b) =>
                            Number(Boolean(b.pinned)) -
                                Number(Boolean(a.pinned)) ||
                            b.updated_at.localeCompare(a.updated_at),
                    ),
            );
            void setConversationPinned(
                conversation.id,
                !conversation.pinned,
            ).then(() => load());
        },
        [load],
    );

    return (
        <>
            {mobileOpen ? (
                <div
                    aria-hidden="true"
                    onClick={onCloseMobile}
                    className="fixed inset-0 z-40 bg-black/40 backdrop-blur-sm lg:hidden"
                />
            ) : null}

            <aside
                className={cn(
                    "fixed inset-y-0 left-0 z-50 flex h-dvh flex-col bg-background transition-transform duration-300 ease-out lg:static lg:z-auto lg:h-full lg:translate-x-0 lg:rounded-lg",
                    collapsed ? "w-16" : "w-72",
                    "-translate-x-full",
                    mobileOpen && "translate-x-0",
                )}
            >
                <header
                    className={cn(
                        "flex items-center border-b border-sidebar-border",
                        collapsed
                            ? "justify-center px-2 py-4"
                            : "justify-between px-4 py-4",
                    )}
                >
                    <Link
                        href="/dashboard/agents"
                        onClick={onCloseMobile}
                        aria-label="AI Agents home"
                    >
                        <Logo wordmark={false} tone="ai" />
                    </Link>
                    {!collapsed ? (
                        <span className="font-display text-sm font-semibold tracking-tight text-sidebar-foreground">
                            SkyAgent
                        </span>
                    ) : null}
                </header>

                <div className="min-h-0 flex-1 space-y-6 overflow-y-auto p-3">
                    <NewChatButton
                        collapsed={collapsed}
                        onNavigate={onCloseMobile}
                    />

                    {collapsed ? (
                        /* Collapsed sidebar: AI feature icons with dropdown lists */
                        <nav className="space-y-1" aria-label="AI features">
                            <button
                                type="button"
                                title="Sales Coach"
                                onClick={() => {
                                    onCloseMobile();
                                    router.push("/dashboard/agents/coaching");
                                }}
                                aria-current={
                                    pathname ===
                                    "/dashboard/agents/coaching"
                                        ? "page"
                                        : undefined
                                }
                                className={cn(
                                    "flex w-full items-center justify-center rounded-lg px-0 py-2 transition-colors hover:bg-muted/60",
                                    pathname ===
                                        "/dashboard/agents/coaching"
                                        ? "text-foreground"
                                        : "text-muted-foreground hover:text-foreground",
                                )}
                            >
                                <Sparkles
                                    aria-hidden="true"
                                    className="size-4"
                                />
                            </button>
                            <button
                                type="button"
                                title="Audit Guardian"
                                onClick={() => {
                                    onCloseMobile();
                                    router.push("/dashboard/agents/guardian");
                                }}
                                aria-current={
                                    pathname ===
                                    "/dashboard/agents/guardian"
                                        ? "page"
                                        : undefined
                                }
                                className={cn(
                                    "flex w-full items-center justify-center rounded-lg px-0 py-2 transition-colors hover:bg-muted/60",
                                    pathname ===
                                        "/dashboard/agents/guardian"
                                        ? "text-foreground"
                                        : "text-muted-foreground hover:text-foreground",
                                )}
                            >
                                <ShieldCheck
                                    aria-hidden="true"
                                    className="size-4"
                                />
                            </button>
                        </nav>
                    ) : (
                        /* Expanded sidebar: AI feature links */
                        <nav className="space-y-1" aria-label="AI features">
                            <p className="mb-2 px-2.5 text-[11px] font-semibold tracking-wider text-muted-foreground/80 uppercase">
                                AI features
                            </p>
                            <Link
                                href="/dashboard/agents/coaching"
                                onClick={onCloseMobile}
                                aria-current={
                                    pathname ===
                                    "/dashboard/agents/coaching"
                                        ? "page"
                                        : undefined
                                }
                                className={cn(
                                    "flex items-center gap-2 rounded-lg px-2.5 py-2 text-sm text-foreground transition-colors hover:bg-muted/60",
                                    pathname ===
                                        "/dashboard/agents/coaching" &&
                                        "bg-sidebar-accent font-medium text-sidebar-accent-foreground",
                                )}
                            >
                                <Sparkles
                                    aria-hidden="true"
                                    className="size-4 shrink-0"
                                />
                                Sales Coach
                            </Link>
                            <Link
                                href="/dashboard/agents/guardian"
                                onClick={onCloseMobile}
                                aria-current={
                                    pathname ===
                                    "/dashboard/agents/guardian"
                                        ? "page"
                                        : undefined
                                }
                                className={cn(
                                    "flex items-center gap-2 rounded-lg px-2.5 py-2 text-sm text-foreground transition-colors hover:bg-muted/60",
                                    pathname ===
                                        "/dashboard/agents/guardian" &&
                                        "bg-sidebar-accent font-medium text-sidebar-accent-foreground",
                                )}
                            >
                                <ShieldCheck
                                    aria-hidden="true"
                                    className="size-4 shrink-0"
                                />
                                Audit Guardian
                            </Link>
                        </nav>
                    )}

                    {collapsed ? (
                        /* Collapsed sidebar: category icons with dropdown lists */
                        <nav className="space-y-1" aria-label="Conversations">
                            {conversations.filter((c) => c.pinned).length >
                                0 && (
                                <DropdownMenu>
                                    <DropdownMenuTrigger asChild>
                                        <button
                                            type="button"
                                            title="Pinned chats"
                                            className="flex w-full items-center justify-center rounded-lg px-0 py-2 text-muted-foreground transition-colors hover:bg-muted/60 hover:text-foreground"
                                        >
                                            <Pin
                                                aria-hidden="true"
                                                className="size-4"
                                            />
                                        </button>
                                    </DropdownMenuTrigger>
                                    <DropdownMenuContent
                                        side="right"
                                        align="start"
                                        sideOffset={8}
                                    >
                                        <DropdownMenuLabel>
                                            Pinned
                                        </DropdownMenuLabel>
                                        <DropdownMenuSeparator />
                                        {conversations
                                            .filter(
                                                (conversation) =>
                                                    conversation.pinned,
                                            )
                                            .map((conversation) => (
                                                <DropdownMenuItem
                                                    key={conversation.id}
                                                    asChild
                                                >
                                                    <Link
                                                        href={`/dashboard/agents/c/${conversation.id}`}
                                                        onClick={onCloseMobile}
                                                        className="w-full truncate"
                                                    >
                                                        {conversation.title}
                                                    </Link>
                                                </DropdownMenuItem>
                                            ))}
                                    </DropdownMenuContent>
                                </DropdownMenu>
                            )}

                            <DropdownMenu>
                                <DropdownMenuTrigger asChild>
                                    <button
                                        type="button"
                                        title="Recent chats"
                                        className="flex w-full items-center justify-center rounded-lg px-0 py-2 text-muted-foreground transition-colors hover:bg-muted/60 hover:text-foreground"
                                    >
                                        <MessageSquareText
                                            aria-hidden="true"
                                            className="size-4"
                                        />
                                    </button>
                                </DropdownMenuTrigger>
                                <DropdownMenuContent
                                    side="right"
                                    align="start"
                                    sideOffset={8}
                                >
                                    <DropdownMenuLabel>
                                        Recents
                                    </DropdownMenuLabel>
                                    <DropdownMenuSeparator />
                                    {conversations.length > 0 ? (
                                        conversations.map((conversation) => (
                                            <DropdownMenuItem
                                                key={conversation.id}
                                                asChild
                                            >
                                                <Link
                                                    href={`/dashboard/agents/c/${conversation.id}`}
                                                    onClick={onCloseMobile}
                                                    className="w-full truncate"
                                                >
                                                    {conversation.title}
                                                </Link>
                                            </DropdownMenuItem>
                                        ))
                                    ) : (
                                        <DropdownMenuItem disabled>
                                            <span className="text-muted-foreground">
                                                No chats yet
                                            </span>
                                        </DropdownMenuItem>
                                    )}
                                </DropdownMenuContent>
                            </DropdownMenu>
                        </nav>
                    ) : (
                        /* Expanded sidebar: section headers with conversation rows */
                        <>
                            {conversations.filter((c) => c.pinned).length >
                                0 && (
                                <section
                                    className="space-y-1"
                                    aria-label="Pinned conversations"
                                >
                                    <p className="mb-2 px-2.5 text-[11px] font-semibold tracking-wider text-muted-foreground/80 uppercase">
                                        Pinned
                                    </p>
                                    {conversations
                                        .filter(
                                            (conversation) =>
                                                conversation.pinned,
                                        )
                                        .map((conversation) => (
                                            <ConversationRow
                                                key={conversation.id}
                                                conversation={conversation}
                                                active={isActive(
                                                    pathname,
                                                    conversation.id,
                                                )}
                                                collapsed={collapsed}
                                                onSelect={onCloseMobile}
                                                onRename={() =>
                                                    handleRename(conversation)
                                                }
                                                onDelete={() =>
                                                    handleDelete(conversation)
                                                }
                                                onTogglePin={() =>
                                                    handleTogglePin(
                                                        conversation,
                                                    )
                                                }
                                            />
                                        ))}
                                </section>
                            )}

                            <section
                                className="space-y-1"
                                aria-label="Recent conversations"
                            >
                                <p className="mb-2 px-2.5 text-[11px] font-semibold tracking-wider text-muted-foreground/80 uppercase">
                                    Recents
                                </p>
                                {conversations.filter((c) => !c.pinned).length >
                                0 ? (
                                    conversations
                                        .filter(
                                            (conversation) =>
                                                !conversation.pinned,
                                        )
                                        .map((conversation) => (
                                            <ConversationRow
                                                key={conversation.id}
                                                conversation={conversation}
                                                active={isActive(
                                                    pathname,
                                                    conversation.id,
                                                )}
                                                collapsed={collapsed}
                                                onSelect={onCloseMobile}
                                                onRename={() =>
                                                    handleRename(conversation)
                                                }
                                                onDelete={() =>
                                                    handleDelete(conversation)
                                                }
                                                onTogglePin={() =>
                                                    handleTogglePin(
                                                        conversation,
                                                    )
                                                }
                                            />
                                        ))
                                ) : (
                                    <p className="px-2.5 py-1 text-xs text-muted-foreground/60">
                                        No recent chats
                                    </p>
                                )}
                            </section>
                        </>
                    )}
                </div>

                <div className="border-t border-sidebar-border p-3">
                    <Link
                        href="/dashboard"
                        onClick={onCloseMobile}
                        data-tour="back-to-overview"
                        title={collapsed ? "Back to overview" : undefined}
                        className={cn(
                            "flex items-center gap-3 rounded-lg text-sm font-medium text-muted-foreground transition-colors hover:bg-muted/60 hover:text-foreground",
                            collapsed
                                ? "justify-center px-0 py-2"
                                : "px-2.5 py-2",
                        )}
                    >
                        <ArrowLeft
                            aria-hidden="true"
                            className="size-[18px] shrink-0"
                        />
                        {!collapsed ? "Back to overview" : null}
                    </Link>
                </div>

                <footer className="border-t border-sidebar-border p-3">
                    <UserMenu collapsed={collapsed} />
                </footer>
            </aside>

            <Dialog
                open={renameTarget !== null}
                onOpenChange={(open) => {
                    if (!open) setRenameTarget(null);
                }}
            >
                <DialogContent
                    className="sm:max-w-sm"
                    onOpenAutoFocus={(event) => {
                        // Focus the input so the user can start typing immediately.
                        const input = document.querySelector<HTMLInputElement>(
                            '[data-slot="rename-chat-input"]',
                        );
                        if (input) {
                            event.preventDefault();
                            input.focus();
                        }
                    }}
                >
                    <DialogHeader>
                        <DialogTitle>Rename chat</DialogTitle>
                        <DialogDescription>
                            Give this conversation a clearer name so it is easy
                            to find later.
                        </DialogDescription>
                    </DialogHeader>
                    <Input
                        data-slot="rename-chat-input"
                        value={renameValue}
                        onChange={(event) => setRenameValue(event.target.value)}
                        onKeyDown={(event) => {
                            if (event.key === "Enter") {
                                event.preventDefault();
                                submitRename();
                            }
                            if (event.key === "Escape") {
                                event.preventDefault();
                                setRenameTarget(null);
                            }
                        }}
                        placeholder="Chat name"
                        maxLength={60}
                        aria-label="Chat name"
                    />
                    <DialogFooter>
                        <Button
                            variant="outline"
                            onClick={() => setRenameTarget(null)}
                        >
                            Cancel
                        </Button>
                        <Button
                            onClick={submitRename}
                            disabled={!renameValue.trim()}
                        >
                            Save
                        </Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>
        </>
    );
}
