"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { CircleHelp, Menu, Settings } from "lucide-react";

import { NotificationCenter } from "@/features/notifications/notification-center";
import {
    Tooltip,
    TooltipContent,
    TooltipTrigger,
} from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";
import { resolvePageTitle } from "@/lib/page-title";
import { PAGE_TITLE_EVENT } from "@/lib/topbar-title";

interface TopbarProps {
    onOpenMenu: () => void;
    /** Public demo shell: demo-safe settings and inbox routing. */
    demoMode?: boolean;
    /** Injected by the demo shell so the live bundle never imports demo code. */
    notificationSlot?: React.ReactNode;
}

export function Topbar({
    onOpenMenu,
    demoMode = false,
    notificationSlot,
}: TopbarProps) {
    const pathname = usePathname();
    const [dynamicTitle, setDynamicTitle] = useState<string | null>(null);

    useEffect(() => {
        setDynamicTitle(null);
    }, [pathname]);

    useEffect(() => {
        function handleTitle(event: Event) {
            const { title } =
                (event as CustomEvent<{ title: string | null }>).detail ?? {};
            setDynamicTitle(
                typeof title === "string" && title.trim() ? title : null,
            );
        }
        window.addEventListener(PAGE_TITLE_EVENT, handleTitle);
        return () => window.removeEventListener(PAGE_TITLE_EVENT, handleTitle);
    }, []);

    const baseTitle = resolvePageTitle(pathname);
    const title = dynamicTitle ? `${baseTitle} · ${dynamicTitle}` : baseTitle;

    return (
        <header
            className={cn(
                "flex h-16 shrink-0 items-center justify-between gap-4 border-b border-border/70 bg-card/85 px-4 backdrop-blur-md lg:px-6",
            )}
        >
            <div className="flex min-w-0 items-center gap-2">
                <button
                    type="button"
                    onClick={onOpenMenu}
                    aria-label="Open sidebar"
                    className="flex size-9 shrink-0 items-center justify-center rounded-lg text-foreground transition-colors hover:bg-muted/60 lg:hidden"
                >
                    <Menu aria-hidden="true" className="size-5" />
                </button>
                <p className="truncate font-display text-lg font-semibold tracking-tight text-foreground">
                    {title}
                </p>
            </div>

            <div className="flex shrink-0 items-center gap-2">
                {demoMode ? (
                    <>
                        <Tooltip>
                            <TooltipTrigger asChild>
                                <Link
                                    href="/demo/erp/settings"
                                    aria-label="Settings"
                                    className="flex size-9 shrink-0 items-center justify-center rounded-lg text-foreground transition-colors hover:bg-muted/60"
                                >
                                    <Settings
                                        aria-hidden="true"
                                        className="size-5"
                                    />
                                </Link>
                            </TooltipTrigger>
                            <TooltipContent side="bottom" sideOffset={6}>
                                Settings
                            </TooltipContent>
                        </Tooltip>
                        {notificationSlot}
                    </>
                ) : (
                    <>
                        {(pathname === "/" || pathname === "/dashboard") && (
                            <Tooltip>
                                <TooltipTrigger asChild>
                                    <button
                                        type="button"
                                        aria-label="Replay product tour"
                                        onClick={() =>
                                            window.dispatchEvent(
                                                new Event("skyrict:start-tour"),
                                            )
                                        }
                                        className="flex size-9 shrink-0 items-center justify-center rounded-lg text-foreground transition-colors hover:bg-muted/60"
                                    >
                                        <CircleHelp
                                            aria-hidden="true"
                                            className="size-5"
                                        />
                                    </button>
                                </TooltipTrigger>
                                <TooltipContent side="bottom" sideOffset={6}>
                                    Replay tour
                                </TooltipContent>
                            </Tooltip>
                        )}
                        <Tooltip>
                            <TooltipTrigger asChild>
                                <Link
                                    href="/settings"
                                    aria-label="Settings"
                                    className="flex size-9 shrink-0 items-center justify-center rounded-lg text-foreground transition-colors hover:bg-muted/60"
                                >
                                    <Settings
                                        aria-hidden="true"
                                        className="size-5"
                                    />
                                </Link>
                            </TooltipTrigger>
                            <TooltipContent side="bottom" sideOffset={6}>
                                Settings
                            </TooltipContent>
                        </Tooltip>
                        <NotificationCenter />
                    </>
                )}
            </div>
        </header>
    );
}
