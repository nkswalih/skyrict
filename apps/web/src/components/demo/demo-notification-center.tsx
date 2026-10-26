"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import {
  ArrowLeft,
  BellRing,
  Check,
  CheckCheck,
  Clock,
  Inbox,
  Settings2,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { useDemo } from "@/components/demo/demo-provider";
import {
  DEMO_NOTIFICATIONS,
  DEMO_NOTIFICATION_SEVERITY,
  formatDemoAbsolute,
  formatDemoRelative,
  type DemoNotification,
} from "@/lib/demo/demo-notifications";
import { cn } from "@/lib/utils";

/**
 * Demo-only bell + inbox drawer.
 *
 * This mirrors the live `NotificationCenter` interaction model (bell, unread
 * badge, list, detail, read, snooze, preferences) without importing the
 * `/api/v1/notifications` client. The active demo snapshot is the only data
 * source, so nothing here can reach the backend.
 */
export function DemoNotificationCenter() {
  const { state, updateState } = useDemo();
  const [open, setOpen] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const readIds = useMemo(
    () => new Set(state.notificationsReadIds),
    [state.notificationsReadIds],
  );
  const snoozedIds = useMemo(
    () => new Set(state.notificationsSnoozedIds),
    [state.notificationsSnoozedIds],
  );

  const items = useMemo(
    () => DEMO_NOTIFICATIONS.filter((item) => !snoozedIds.has(item.id)),
    [snoozedIds],
  );
  const unreadCount = items.filter((item) => !readIds.has(item.id)).length;
  const selected = items.find((item) => item.id === selectedId) ?? null;
  const now = new Date();

  const markRead = (id: string) => {
    if (readIds.has(id)) return;
    updateState((current) => ({
      ...current,
      notificationsReadIds: [...current.notificationsReadIds, id],
    }));
  };

  const markAllRead = () => {
    updateState((current) => ({
      ...current,
      notificationsReadIds: Array.from(
        new Set([
          ...current.notificationsReadIds,
          ...items.map((item) => item.id),
        ]),
      ),
    }));
  };

  const snooze = (id: string) => {
    updateState((current) => ({
      ...current,
      notificationsSnoozedIds: Array.from(
        new Set([...current.notificationsSnoozedIds, id]),
      ),
    }));
    setSelectedId(null);
  };

  return (
    <>
      <button
        type="button"
        aria-label={
          unreadCount > 0
            ? `Notifications (${unreadCount} unread)`
            : "Notifications"
        }
        title="Notifications"
        onClick={() => setOpen(true)}
        className="relative flex size-9 shrink-0 items-center justify-center rounded-lg text-foreground transition-colors hover:bg-muted/60"
      >
        <BellRing aria-hidden="true" className="size-5" />
        {unreadCount > 0 && (
          <span className="absolute top-1 right-1 flex min-w-4 items-center justify-center rounded-full bg-destructive px-1 text-[0.65rem] leading-4 font-semibold text-white">
            {unreadCount > 99 ? "99+" : unreadCount}
          </span>
        )}
      </button>

      <Dialog
        open={open}
        onOpenChange={(next) => {
          setOpen(next);
          if (!next) setSelectedId(null);
        }}
      >
        <DialogContent
          showCloseButton={false}
          className="top-0 right-0 bottom-0 left-auto h-dvh w-full max-w-md translate-x-0 translate-y-0 grid-rows-[auto_minmax(0,1fr)_auto] gap-0 rounded-none rounded-l-xl p-0 data-open:animate-in data-open:fade-in-0 data-open:zoom-in-0 data-open:slide-in-from-right-5 data-closed:animate-out data-closed:fade-out-0 data-closed:zoom-out-0 data-closed:slide-out-to-right-5"
        >
          <DialogHeader className="border-b border-border/70 px-4 py-3">
            {selected ? (
              <div className="flex items-center gap-1.5">
                <Button
                  variant="ghost"
                  size="icon-sm"
                  aria-label="Back to all notifications"
                  onClick={() => setSelectedId(null)}
                >
                  <ArrowLeft aria-hidden="true" />
                </Button>
                <DialogTitle className="text-base">
                  Notification details
                </DialogTitle>
              </div>
            ) : (
              <div className="flex items-center justify-between gap-2">
                <DialogTitle className="flex items-center gap-2 text-base">
                  <Inbox aria-hidden="true" className="size-4 text-primary" />
                  Notifications
                </DialogTitle>
                <div className="flex items-center gap-1.5">
                  {unreadCount > 0 && (
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={markAllRead}
                    >
                      <CheckCheck aria-hidden="true" />
                      Mark all read
                    </Button>
                  )}
                  <Button variant="ghost" size="icon-sm" asChild>
                    <Link
                      href="/demo/erp/settings/notifications"
                      prefetch={false}
                      aria-label="Notification preferences"
                      title="Notification preferences"
                    >
                      <Settings2 aria-hidden="true" />
                    </Link>
                  </Button>
                </div>
              </div>
            )}
            <DialogDescription className="sr-only">
              Your demo notification inbox with read, snooze, and preferences.
            </DialogDescription>
          </DialogHeader>

          {selected ? (
            <div className="flex min-h-0 flex-1 flex-col">
              <div className="min-h-0 flex-1 overflow-y-auto px-4 py-4">
                <div className="flex flex-wrap items-center gap-2">
                  <span
                    aria-hidden="true"
                    className={cn(
                      "size-2 rounded-full",
                      DEMO_NOTIFICATION_SEVERITY[selected.severity].dot,
                    )}
                  />
                  <span
                    className={cn(
                      "rounded-full px-2 py-0.5 text-[0.7rem] font-medium",
                      DEMO_NOTIFICATION_SEVERITY[selected.severity].badge,
                    )}
                  >
                    {DEMO_NOTIFICATION_SEVERITY[selected.severity].label}
                  </span>
                  <span className="rounded-full bg-muted px-2 py-0.5 text-[0.7rem] text-muted-foreground">
                    {selected.category}
                  </span>
                  {readIds.has(selected.id) ? (
                    <span className="rounded-full bg-muted px-2 py-0.5 text-[0.7rem] text-muted-foreground">
                      Read
                    </span>
                  ) : (
                    <span className="rounded-full bg-primary/15 px-2 py-0.5 text-[0.7rem] font-medium text-primary">
                      Unread
                    </span>
                  )}
                </div>
                <h3 className="mt-3 text-base leading-snug font-semibold text-foreground">
                  {selected.title}
                </h3>
                <p className="mt-1.5 text-xs text-muted-foreground">
                  {formatDemoAbsolute(selected.occurredAt)}
                </p>
                <p className="mt-4 text-sm leading-relaxed whitespace-pre-wrap text-foreground/90">
                  {selected.body}
                </p>
                <dl className="mt-4 grid grid-cols-[auto_1fr] gap-x-3 gap-y-1.5 text-xs">
                  <dt className="text-muted-foreground">Module</dt>
                  <dd className="text-foreground">{selected.module}</dd>
                  <dt className="text-muted-foreground">Received</dt>
                  <dd className="text-foreground">
                    {formatDemoRelative(selected.occurredAt, now)}
                  </dd>
                  <dt className="text-muted-foreground">Source</dt>
                  <dd className="text-foreground">
                    Seeded demo notification
                  </dd>
                </dl>
                {selected.actionHref ? (
                  <Button className="mt-5" size="sm" asChild>
                    <Link href={selected.actionHref} prefetch={false}>
                      {selected.actionLabel ?? "Open record"}
                    </Link>
                  </Button>
                ) : null}
              </div>
              <div className="flex items-center gap-2 border-t border-border/70 px-4 py-2.5">
                {!readIds.has(selected.id) ? (
                  <Button
                    size="sm"
                    onClick={() => markRead(selected.id)}
                  >
                    <Check aria-hidden="true" />
                    Mark as read
                  </Button>
                ) : null}
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => snooze(selected.id)}
                >
                  <Clock aria-hidden="true" />
                  Snooze 1 hour
                </Button>
              </div>
            </div>
          ) : (
            <div className="min-h-0 flex-1 overflow-y-auto">
              {items.length === 0 ? (
                <div className="flex flex-col items-center gap-2 px-4 py-10 text-center">
                  <Inbox
                    aria-hidden="true"
                    className="size-8 text-muted-foreground/50"
                  />
                  <p className="text-sm font-medium text-foreground">
                    You&apos;re all caught up
                  </p>
                  <p className="text-xs text-muted-foreground">
                    Every demo notification is read or snoozed.
                  </p>
                </div>
              ) : (
                <ul className="flex flex-col gap-2 px-3 py-3">
                  {items.map((item) => (
                    <DemoNotificationRow
                      key={item.id}
                      item={item}
                      now={now}
                      unread={!readIds.has(item.id)}
                      onOpen={() => {
                        markRead(item.id);
                        setSelectedId(item.id);
                      }}
                      onRead={() => markRead(item.id)}
                      onSnooze={() => snooze(item.id)}
                    />
                  ))}
                </ul>
              )}
            </div>
          )}

          <div className="border-t border-border/70 px-4 py-2.5">
            <Button variant="ghost" size="sm" className="w-full" asChild>
              <Link href="/demo/erp/settings/notifications" prefetch={false}>
                <Settings2 aria-hidden="true" />
                Notification preferences
              </Link>
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
}

function DemoNotificationRow({
  item,
  now,
  unread,
  onOpen,
  onRead,
  onSnooze,
}: {
  item: DemoNotification;
  now: Date;
  unread: boolean;
  onOpen: () => void;
  onRead: () => void;
  onSnooze: () => void;
}) {
  return (
    <li
      role="button"
      tabIndex={0}
      aria-label={`Open notification: ${item.title}`}
      onClick={onOpen}
      onKeyDown={(event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          onOpen();
        }
      }}
      className={cn(
        "flex cursor-pointer items-start gap-2.5 rounded-xl border px-3.5 py-3 transition-colors",
        unread
          ? "border-primary/25 bg-primary/[0.04] hover:bg-muted/50"
          : "border-border/60 bg-card/40 opacity-80 hover:bg-muted/40 hover:opacity-100",
        "focus-visible:ring-2 focus-visible:ring-ring/50 focus-visible:outline-none",
      )}
    >
      <div className="flex min-w-0 flex-1 flex-col gap-1">
        <div className="flex items-center gap-2">
          <span
            aria-hidden="true"
            className={cn(
              "size-2 shrink-0 rounded-full",
              DEMO_NOTIFICATION_SEVERITY[item.severity].dot,
            )}
          />
          <p className="truncate text-sm font-medium text-foreground">
            {item.title}
          </p>
        </div>
        <p className="line-clamp-2 text-xs leading-relaxed text-muted-foreground">
          {item.body}
        </p>
        <p className="text-[0.7rem] text-muted-foreground/80">
          {item.category} ·{" "}
          {DEMO_NOTIFICATION_SEVERITY[item.severity].label} ·{" "}
          {formatDemoRelative(item.occurredAt, now)}
          {item.pinned ? " · Pinned" : ""}
        </p>
      </div>
      <div className="flex shrink-0 items-center gap-1">
        {unread ? (
          <Button
            variant="ghost"
            size="icon-sm"
            aria-label="Mark as read"
            title="Mark as read"
            onClick={(event) => {
              event.stopPropagation();
              onRead();
            }}
          >
            <Check aria-hidden="true" />
          </Button>
        ) : null}
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button
              variant="ghost"
              size="icon-sm"
              aria-label="Snooze"
              title="Snooze"
              onClick={(event) => event.stopPropagation()}
            >
              <Clock aria-hidden="true" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuItem onClick={onSnooze}>In 1 hour</DropdownMenuItem>
            <DropdownMenuItem onClick={onSnooze}>
              Tomorrow 9:00
            </DropdownMenuItem>
            <DropdownMenuItem onClick={onSnooze}>In 1 week</DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </li>
  );
}
