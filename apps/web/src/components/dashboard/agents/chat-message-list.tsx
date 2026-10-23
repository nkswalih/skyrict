"use client";

import { memo, useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
    ArrowDown,
    BookOpen,
    Check,
    Copy,
    FileText,
    Image,
    Pencil,
    RefreshCw,
    RotateCw,
} from "lucide-react";
import Markdown from "react-markdown";

import { AiGlyph } from "@/components/brand/logo";
import { cn, copyToClipboard } from "@/lib/utils";
import { apiFetchRaw } from "@/lib/api/http";
import type {
    AgentChatMessage,
    ChatAttachment,
} from "@/lib/chat/use-agent-chat";

/* ------------------------------------------------------------------ */
/*  Utility helpers                                                    */
/* ------------------------------------------------------------------ */

/** Split a timestamp into a date-group title and its time string.
 *  Recent week → "Today" / "Yesterday" / "Friday" (+ time to the right).
 *  Older → full date, e.g. "Sep 3, 2026" (+ time to the right). */
function dateGroupParts(iso: string): { title: string; time: string } {
    const date = new Date(iso);
    const now = new Date();
    const DAY = 86_400_000;
    // Compute day difference on midnight copies so `date` keeps its real time.
    const today = new Date(now);
    today.setHours(0, 0, 0, 0);
    const dayStart = new Date(date);
    dayStart.setHours(0, 0, 0, 0);
    const dayDiff = Math.floor((today.getTime() - dayStart.getTime()) / DAY);
    const time = Number.isNaN(date.getTime())
        ? ""
        : date.toLocaleTimeString(undefined, {
              hour: "numeric",
              minute: "2-digit",
              hour12: true,
          });

    if (Number.isNaN(date.getTime())) return { title: iso, time: "" };
    if (dayDiff < 7) {
        if (dayDiff < 1) return { title: "Today", time };
        if (dayDiff < 2) return { title: "Yesterday", time };
        return {
            title: date.toLocaleDateString(undefined, { weekday: "long" }),
            time,
        };
    }
    return {
        title: date.toLocaleDateString(undefined, {
            month: "short",
            day: "numeric",
            year: "numeric",
        }),
        time,
    };
}

/** True if two ISO timestamps fall on different calendar days. */
function differentDay(a: string, b: string): boolean {
    const da = new Date(a);
    const db = new Date(b);
    return (
        da.getFullYear() !== db.getFullYear() ||
        da.getMonth() !== db.getMonth() ||
        da.getDate() !== db.getDate()
    );
}

/* ------------------------------------------------------------------ */
/*  File attachment cards                                              */
/* ------------------------------------------------------------------ */

function fileTypeLabel(mimeType: string): string {
    if (mimeType.startsWith("image/")) return "Image";
    if (mimeType === "application/pdf") return "PDF";
    if (
        mimeType.includes("spreadsheet") ||
        mimeType.includes("csv") ||
        mimeType.includes("excel")
    )
        return "Spreadsheet";
    if (mimeType.includes("text/")) return "Document";
    if (mimeType.includes("word") || mimeType.includes("document"))
        return "Document";
    return "File";
}

function AttachmentCard({ attachment }: { attachment: ChatAttachment }) {
    // Persisted attachments carry a server URL instead of an object URL; the
    // blob must be fetched with the in-memory session token and previewed
    // through a temporary object URL (same pattern as document detail previews).
    // Fresh (unsent) attachments carry previewUrl directly.
    const [remotePreview, setRemotePreview] = useState<string | null>(null);
    const isRemoteImage =
        !attachment.previewUrl &&
        Boolean(attachment.url) &&
        attachment.type.startsWith("image/");

    useEffect(() => {
        if (!isRemoteImage || !attachment.url) return;
        let cancelled = false;
        let objectUrl: string | null = null;
        void apiFetchRaw(attachment.url)
            .then((response) => {
                if (!response.ok) throw new Error(`HTTP ${response.status}`);
                return response.blob();
            })
            .then((blob) => {
                if (cancelled) return;
                objectUrl = URL.createObjectURL(blob);
                setRemotePreview(objectUrl);
            })
            .catch(() => {
                if (cancelled) return;
                setRemotePreview(null);
            });
        return () => {
            cancelled = true;
            if (objectUrl) URL.revokeObjectURL(objectUrl);
        };
    }, [attachment.url, attachment.type, isRemoteImage]);

    const previewSrc = attachment.previewUrl ?? remotePreview;

    return (
        <div className="flex min-w-0 max-w-[260px] items-center gap-2.5 rounded-xl border border-border/60 bg-background/80 px-3 py-2 text-sm backdrop-blur-sm">
            {previewSrc ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img
                    src={previewSrc}
                    alt=""
                    className="size-8 shrink-0 rounded-md object-cover"
                />
            ) : (
                <div className="flex size-8 shrink-0 items-center justify-center rounded-md bg-muted">
                    {attachment.type === "application/pdf" ? (
                        <span className="text-[10px] font-bold text-red-500">
                            PDF
                        </span>
                    ) : attachment.type.startsWith("image/") ? (
                        // eslint-disable-next-line jsx-a11y/alt-text -- lucide Image is an SVG icon, not <img>
                        <Image
                            aria-hidden="true"
                            className="size-4 text-muted-foreground"
                        />
                    ) : (
                        <FileText
                            aria-hidden="true"
                            className="size-4 text-muted-foreground"
                        />
                    )}
                </div>
            )}
            <div className="min-w-0 flex-1">
                <p className="truncate text-xs font-medium text-foreground">
                    {attachment.name}
                </p>
                <p className="text-[11px] text-muted-foreground">
                    {fileTypeLabel(attachment.type)}
                </p>
            </div>
        </div>
    );
}

/* ------------------------------------------------------------------ */
/*  Action buttons                                                     */
/* ------------------------------------------------------------------ */

function CopyButton({ text }: { text: string }) {
    const [copied, setCopied] = useState(false);
    const handleCopy = useCallback(() => {
        void copyToClipboard(text);
        setCopied(true);
        window.setTimeout(() => setCopied(false), 1500);
    }, [text]);
    return (
        <button
            type="button"
            onClick={handleCopy}
            aria-label="Copy message"
            title="Copy"
            className="flex size-7 shrink-0 items-center justify-center rounded-lg text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
        >
            {copied ? (
                <Check
                    aria-hidden="true"
                    className="size-3.5 text-emerald-500"
                />
            ) : (
                <Copy aria-hidden="true" className="size-3.5" />
            )}
        </button>
    );
}

function EditButton({ onClick }: { onClick: () => void }) {
    return (
        <button
            type="button"
            onClick={onClick}
            aria-label="Edit message"
            title="Edit"
            className="flex size-7 shrink-0 items-center justify-center rounded-lg text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
        >
            <Pencil aria-hidden="true" className="size-3.5" />
        </button>
    );
}

function ResendButton({ onClick }: { onClick: () => void }) {
    return (
        <button
            type="button"
            onClick={onClick}
            aria-label="Resend message"
            title="Resend"
            className="flex size-7 shrink-0 items-center justify-center rounded-lg text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
        >
            <RotateCw aria-hidden="true" className="size-3.5" />
        </button>
    );
}

function RetryButton({ onClick }: { onClick: () => void }) {
    return (
        <button
            type="button"
            onClick={onClick}
            aria-label="Try again"
            title="Try again"
            className="flex size-7 shrink-0 items-center justify-center rounded-lg text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
        >
            <RefreshCw aria-hidden="true" className="size-3.5" />
        </button>
    );
}

/* ------------------------------------------------------------------ */
/*  Citations                                                          */
/* ------------------------------------------------------------------ */

function AgentCitations({ message }: { message: AgentChatMessage }) {
    const citations = message.citations ?? [];
    if (citations.length === 0) return null;
    return (
        <div className="mt-3 space-y-1.5 border-t border-border/70 pt-2.5">
            <p className="flex items-center gap-1.5 text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
                <BookOpen aria-hidden="true" className="size-3" />
                Sources
            </p>
            <ul className="space-y-1">
                {citations.map((citation, index) => (
                    <li key={`${citation.sourceRef}-${index}`}>
                        <a
                            href={citation.url ?? citation.sourceRef}
                            target={citation.url ? "_blank" : undefined}
                            rel="noreferrer"
                            className="text-xs font-medium text-foreground underline decoration-primary/70 decoration-1 underline-offset-2 hover:decoration-foreground"
                        >
                            {citation.title}
                            {citation.module ? (
                                <span className="ml-1.5 text-muted-foreground">
                                    · {citation.module}
                                </span>
                            ) : null}
                        </a>
                    </li>
                ))}
            </ul>
        </div>
    );
}

/* ------------------------------------------------------------------ */
/*  Date separator                                                     */
/* ------------------------------------------------------------------ */

function DateSeparator({ iso }: { iso: string }) {
    const { title, time } = dateGroupParts(iso);
    return (
        <div className="flex items-center justify-center gap-2 py-4">
            <span className="text-[13px] font-semibold text-muted-foreground">
                {title}
            </span>
            {time ? (
                <span className="text-xs font-normal text-muted-foreground/70">
                    {time}
                </span>
            ) : null}
        </div>
    );
}

/* ------------------------------------------------------------------ */
/*  Message bubble                                                     */
/* ------------------------------------------------------------------ */

export const MessageBubble = memo(function MessageBubble({
    message,
    onResend,
    isLastAi = false,
}: {
    message: AgentChatMessage;
    onResend?: (content: string) => void;
    isLastAi?: boolean;
}) {
    const isUser = message.role === "user";
    const streaming =
        !isUser && message.content === "" && message.failed !== true;
    // The AI logo appears only on the newest agent reply (or while the agent
    // is still thinking): keep earlier replies logo-free.
    const showLogoMark = !isUser && (streaming || isLastAi);
    const [editing, setEditing] = useState(false);

    return (
        <div
            className={cn(
                "group flex gap-3",
                isUser ? "justify-end" : "justify-start",
            )}
        >
            <div
                className={cn(
                    "relative flex max-w-[85%] flex-col sm:max-w-[75%]",
                    isUser ? "items-end" : "ml-4 items-start",
                )}
            >
                {/* File attachments - stacked above the message bubble */}
                {isUser &&
                message.attachments &&
                message.attachments.length > 0 ? (
                    <div className="mb-1.5 flex flex-col gap-1.5">
                        {message.attachments.map((attachment) => (
                            <AttachmentCard
                                key={attachment.id}
                                attachment={attachment}
                            />
                        ))}
                    </div>
                ) : null}

                <div
                    className={cn(
                        "leading-relaxed",
                        isUser
                            ? "whitespace-pre-wrap rounded-2xl bg-primary px-3.5 py-2 text-[15px] text-primary-foreground"
                            : "text-[15px] text-foreground",
                        message.failed
                            ? "text-muted-foreground italic"
                            : null,
                    )}
                >
                    {message.agentName &&
                    !isUser &&
                    message.agentName.toLowerCase() !== "supervisor" ? (
                        <p className="mb-1 text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
                            {message.agentName}
                        </p>
                    ) : null}
                    {streaming ? (
                        <span
                            className="chat-thinking text-[15px]"
                            aria-label="Thinking"
                        >
                            Thinking…
                        </span>
                    ) : isUser ? (
                        message.content
                    ) : (
                        <div className="chat-markdown">
                            <Markdown>{message.content}</Markdown>
                        </div>
                    )}
                    {!isUser && message.content ? (
                        <AgentCitations message={message} />
                    ) : null}
                </div>

                {/* Footer under the bubble - AI logo (left) + hover actions,
                    Claude-style: actions appear on hover in the same row. */}
                {showLogoMark || (!streaming && message.content) ? (
                    <div
                        className={cn(
                            "mt-1 flex items-center gap-0.5",
                            isUser ? "justify-end" : "justify-start",
                        )}
                    >
                        {showLogoMark ? (
                            <AiGlyph
                                aria-hidden="true"
                                className="size-5 shrink-0 text-primary"
                            />
                        ) : null}
                        {!streaming && message.content ? (
                            <div className="flex items-center gap-0.5 opacity-0 transition-opacity group-hover:opacity-100">
                                <CopyButton text={message.content} />
                                {isUser ? (
                                    <>
                                        <EditButton
                                            onClick={() => setEditing(!editing)}
                                        />
                                        {onResend ? (
                                            <ResendButton
                                                onClick={() =>
                                                    onResend(message.content)
                                                }
                                            />
                                        ) : null}
                                    </>
                                ) : onResend ? (
                                    <RetryButton
                                        onClick={() =>
                                            onResend(message.content)
                                        }
                                    />
                                ) : null}
                            </div>
                        ) : null}
                    </div>
                ) : null}
            </div>
        </div>
    );
});

/* ------------------------------------------------------------------ */
/*  Message list                                                       */
/* ------------------------------------------------------------------ */

export function MessageList({
    messages,
    userDisplay,
    onResend,
}: {
    messages: AgentChatMessage[];
    userDisplay: string;
    onResend?: (content: string) => void;
}) {
    const scrollRef = useRef<HTMLDivElement>(null);
    const messageCountRef = useRef(messages.length);
    // Ref + state pair: the ref answers "should we stick to the bottom?"
    // synchronously inside effects, the state only drives the jump-to-latest
    // button (set exclusively when the boolean flips, so scrolling never
    // re-renders the list per pixel).
    const isAtBottomRef = useRef(true);
    const [isAtBottom, setIsAtBottom] = useState(true);

    const scrollToBottom = useCallback((behavior: ScrollBehavior) => {
        const node = scrollRef.current;
        if (node) node.scrollTo({ top: node.scrollHeight, behavior });
    }, []);

    // Opening a conversation must land on the NEWEST message, not the first:
    // this component mounts after the history is already loaded, so the
    // message-count growth effect below never fires for the initial fill.
    // The rAF re-pin catches late layout (images, markdown) shifting height
    // after the first synchronous scroll.
    useEffect(() => {
        const node = scrollRef.current;
        if (node) node.scrollTop = node.scrollHeight;
        const frame = requestAnimationFrame(() => {
            const pinned = scrollRef.current;
            if (pinned) pinned.scrollTop = pinned.scrollHeight;
        });
        return () => cancelAnimationFrame(frame);
    }, []);

    // Stick-to-bottom: follow new messages ONLY while the reader is already
    // near the bottom - scrolling up to re-read history is never yanked back.
    useEffect(() => {
        if (messages.length > messageCountRef.current && isAtBottomRef.current) {
            scrollToBottom("auto");
        }
        messageCountRef.current = messages.length;
    }, [messages.length, scrollToBottom]);

    const handleScroll = useCallback(() => {
        const node = scrollRef.current;
        if (!node) return;
        const atBottom = node.scrollHeight - node.scrollTop - node.clientHeight < 96;
        if (atBottom !== isAtBottomRef.current) {
            isAtBottomRef.current = atBottom;
            setIsAtBottom(atBottom);
        }
    }, []);

    // The AI logo attaches only to the newest agent message (keeping the
    // per-bubble logos off earlier replies) - scan backwards to find it.
    // Hoisted above the empty-state return so hook order never varies with
    // message count (Rules of Hooks).
    const lastAgentIndex = useMemo(() => {
        for (let i = messages.length - 1; i >= 0; i--) {
            if (messages[i].role !== "user") return i;
        }
        return -1;
    }, [messages]);

    if (messages.length === 0) {
        return (
            <div className="flex flex-1 flex-col items-center justify-center px-4 text-center">
                <p className="text-sm text-muted-foreground">
                    Start the conversation - ask anything about your business or
                    the market.
                </p>
            </div>
        );
    }

    return (
        <div className="relative flex min-h-0 flex-1 flex-col">
            <div
                ref={scrollRef}
                onScroll={handleScroll}
                className="flex-1 overflow-y-auto px-4"
            >
                <div className="mx-auto flex w-full max-w-[44rem] flex-col gap-3 pb-8 pt-4">
                    {messages.map((message, index) => {
                        const prev = index > 0 ? messages[index - 1] : null;
                        const showDateSep =
                            !prev ||
                            differentDay(prev.createdAt, message.createdAt);

                        return (
                            <div key={message.id}>
                                {showDateSep ? (
                                    <DateSeparator
                                        iso={message.createdAt}
                                    />
                                ) : null}
                                <MessageBubble
                                    message={message}
                                    onResend={onResend}
                                    isLastAi={index === lastAgentIndex}
                                />
                            </div>
                        );
                    })}
                </div>
                <p className="sr-only">{`Chatting as ${userDisplay || "you"}`}</p>
            </div>
            {/* Fade the newest messages into the composer area - a soft
                gradient dissolve instead of a hard edge between the chat
                and the input box. */}
            <div
                aria-hidden="true"
                className="pointer-events-none absolute inset-x-0 bottom-0 h-16 bg-gradient-to-t from-sidebar via-sidebar/40 to-transparent"
            />
            {/* Jump-to-latest: only visible once the reader scrolled up, the
                standard AI-chat affordance (ChatGPT-style floating arrow). */}
            {!isAtBottom ? (
                <button
                    type="button"
                    onClick={() => scrollToBottom("smooth")}
                    aria-label="Scroll to latest message"
                    className="absolute bottom-3 left-1/2 z-10 flex size-9 -translate-x-1/2 items-center justify-center rounded-full border border-border/60 bg-background/90 text-foreground shadow-lg backdrop-blur transition-colors hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/50"
                >
                    <ArrowDown aria-hidden="true" className="size-4" />
                </button>
            ) : null}
        </div>
    );
}
