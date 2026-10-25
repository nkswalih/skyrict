"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useCallback, useState } from "react";
import {
    ArrowLeft,
    Blocks,
    ChevronDown,
    PanelLeftClose,
    PanelLeftOpen,
} from "lucide-react";

import { Logo, type LogoMarkTone } from "@/components/brand/logo";
import {
    isSidebarItemActive,
    type NavGroup,
    type NavItem,
} from "@/components/dashboard/workspace/sidebar-config";
import { UserMenu, type UserMenuProfile } from "@/components/dashboard/workspace/user-menu";
import { cn } from "@/lib/utils";

function SidebarLink({
    item,
    collapsed,
    pathname,
    onCloseMobile,
    indented = false,
}: {
    item: NavItem;
    collapsed: boolean;
    pathname: string;
    onCloseMobile: () => void;
    /** Render as a nested row inside a collapsible group (content indented, same full width). */
    indented?: boolean;
}) {
    const active = isSidebarItemActive(pathname, item);
    const Icon = item.icon;
    const padding = collapsed
        ? "justify-center px-0 py-2.5"
        : indented
          ? "h-9 px-3 rounded-lg"
          : "px-3 py-2";

    if (item.soon) {
        return (
            <div
                data-tour={item.tour}
                title={collapsed ? item.label : undefined}
                aria-disabled="true"
                className={cn(
                    "flex items-center gap-3 rounded-lg text-sm font-medium text-muted-foreground/60 select-none",
                    padding,
                )}
            >
                <Icon aria-hidden="true" className="size-[18px] shrink-0" />
                {!collapsed ? (
                    <>
                        <span className="truncate">{item.label}</span>
                        <span className="ml-auto rounded-full bg-muted px-2 py-0.5 text-[10px] font-medium tracking-wide text-muted-foreground uppercase">
                            Soon
                        </span>
                    </>
                ) : null}
            </div>
        );
    }

    return (
        <Link
            href={item.href}
            prefetch={false}
            data-tour={item.tour}
            onClick={onCloseMobile}
            title={collapsed ? item.label : undefined}
            aria-current={active ? "page" : undefined}
            className={cn(
                "group relative flex items-center gap-2.5 rounded-md transition-colors",
                indented ? "text-[13px] font-medium" : "text-sm font-medium",
                padding,
                active
                    ? indented
                        ? "bg-sidebar-accent/50 text-sidebar-accent-foreground font-medium"
                        : "bg-sidebar-accent text-sidebar-accent-foreground"
                    : indented
                      ? "text-muted-foreground hover:bg-sidebar-accent/25 hover:text-sidebar-accent-foreground"
                      : "text-muted-foreground hover:bg-muted/60 hover:text-foreground",
            )}
        >
            {!indented && active ? (
                <span
                    aria-hidden="true"
                    className="absolute top-1/2 left-0 h-5 w-0.5 -translate-y-1/2 rounded-full bg-primary"
                />
            ) : null}
            {indented && active ? (
                <span
                    aria-hidden="true"
                    className="absolute left-0 top-1/2 h-3.5 w-[3px] -translate-y-1/2 rounded-full bg-emerald-400"
                />
            ) : null}
            {indented ? (
                <Icon aria-hidden="true" className="size-4 shrink-0" />
            ) : (
                <Icon
                    aria-hidden="true"
                    className={cn(
                        "size-[18px] shrink-0",
                        active && "text-primary",
                    )}
                />
            )}
            {!collapsed ? <span className="truncate">{item.label}</span> : null}
        </Link>
    );
}

/**
 * A collapsible two-tier nav item (e.g. HR → Employees/Departments/Leave).
 * The parent row is a clickable Link that navigates to the overview AND toggles
 * the dropdown open/closed. Children step down in size/weight and auto-expand
 * when one of them is the active page.
 */
function CollapsibleNavItem({
    item,
    collapsed,
    pathname,
    onCloseMobile,
    open,
    onToggle,
}: {
    item: NavItem;
    collapsed: boolean;
    pathname: string;
    onCloseMobile: () => void;
    open: boolean;
    onToggle: () => void;
}) {
    const Icon = item.icon;
    const children = item.children ?? [];
    const parentActive = isSidebarItemActive(pathname, item);
    const hasActiveChild = children.some((child) => isSidebarItemActive(pathname, child));

    const handleParentClick = useCallback(() => {
        onCloseMobile();
    }, [onCloseMobile]);

    if (collapsed) {
        return (
            <Link
                href={item.href}
                prefetch={false}
                onClick={onCloseMobile}
                title={item.label}
                aria-current={parentActive ? "page" : undefined}
                className={cn(
                    "group relative flex items-center justify-center rounded-lg py-2.5 text-sm font-medium transition-colors",
                    parentActive
                        ? "bg-sidebar-accent text-sidebar-accent-foreground"
                        : "text-muted-foreground hover:bg-muted/60 hover:text-foreground",
                )}
            >
                <Icon aria-hidden="true" className="size-[18px] shrink-0" />
            </Link>
        );
    }

    return (
        <div className="space-y-1">
            <div
                className={cn(
                    "flex items-center gap-1 rounded-lg transition-colors",
                    hasActiveChild
                        ? "bg-sidebar-accent text-sidebar-accent-foreground"
                        : "text-muted-foreground hover:bg-muted/60 hover:text-foreground",
                )}
            >
                <Link
                    href={item.href}
                    prefetch={false}
                    onClick={handleParentClick}
                    aria-current={parentActive ? "page" : undefined}
                    className="relative flex min-w-0 flex-1 items-center gap-3 px-3 py-2 text-sm font-semibold transition-colors"
                >
                    {hasActiveChild ? (
                        <span
                            aria-hidden="true"
                            className="absolute top-1/2 left-0 h-5 w-0.5 -translate-y-1/2 rounded-full bg-primary"
                        />
                    ) : null}
                    <Icon
                        aria-hidden="true"
                        className={cn(
                            "size-[18px] shrink-0",
                            hasActiveChild && "text-primary",
                        )}
                    />
                    <span className="truncate">{item.label}</span>
                </Link>
                <button
                    type="button"
                    onClick={onToggle}
                    aria-expanded={open}
                    aria-label={`${open ? "Collapse" : "Expand"} ${item.label}`}
                    title={open ? "Collapse" : "Expand"}
                    className="mr-1 flex size-7 shrink-0 items-center justify-center rounded-md transition-colors hover:text-foreground focus-visible:ring-3 focus-visible:ring-ring/50 outline-none"
                >
                    <ChevronDown
                        aria-hidden="true"
                        className={cn(
                            "size-4 transition-transform duration-200",
                            open && "rotate-180",
                        )}
                    />
                </button>
            </div>
            {open ? (
                <div className="ml-4 space-y-0.5 border-l border-sidebar-border/30 pl-1.5">
                    {children.map((child) => (
                        <SidebarLink
                            key={child.href}
                            item={child}
                            collapsed={collapsed}
                            pathname={pathname}
                            onCloseMobile={onCloseMobile}
                            indented
                        />
                    ))}
                </div>
            ) : null}
        </div>
    );
}

export interface AppSidebarProps {
    collapsed: boolean;
    mobileOpen: boolean;
    onToggleCollapsed: () => void;
    onCloseMobile: () => void;
    navGroups: NavGroup[];
    accountItems: NavItem[];
    /** Root the sidebar logo lands on (workspace overview vs. a module home). */
    brandHref?: string;
    /** Tints the logo mark for module worlds (ERP renders a green mark). */
    logoTone?: LogoMarkTone;
    /** Module sidebars render a "Back to overview" link above the footer. */
    showBackToOverview?: boolean;
    /** Public demo persona for the footer account menu. */
    demoProfile?: UserMenuProfile | null;
}

export function AppSidebar({
    collapsed,
    mobileOpen,
    onToggleCollapsed,
    onCloseMobile,
    navGroups,
    accountItems,
    brandHref = "/",
    logoTone = "sky",
    showBackToOverview = false,
    demoProfile = null,
}: AppSidebarProps) {
    const pathname = usePathname();
    const [openGroups, setOpenGroups] = useState<Record<string, boolean>>({});

    /** A collapsible group is open once toggled; until then it defaults to open only when a sub-item is active. */
    const isGroupOpen = useCallback(
        (group: NavGroup): boolean => {
            if (!group.collapsible) return true;
            const key = `g:${group.label}`;
            if (openGroups[key] !== undefined) return openGroups[key];
            return group.items.some((item) => isSidebarItemActive(pathname, item));
        },
        [openGroups, pathname],
    );

    const toggleGroup = useCallback(
        (group: NavGroup) => {
            setOpenGroups((prev) => ({
                ...prev,
                [`g:${group.label}`]: !isGroupOpen(group),
            }));
        },
        [isGroupOpen],
    );

    /** A collapsible item (NavItem with children) is open once toggled; until then it defaults to open only when a child is active. */
    const isItemOpen = useCallback(
        (item: NavItem): boolean => {
            if (!item.children) return true;
            const key = `i:${item.label}`;
            if (openGroups[key] !== undefined) return openGroups[key];
            return item.children.some((child) => isSidebarItemActive(pathname, child));
        },
        [openGroups, pathname],
    );

    const toggleItem = useCallback(
        (item: NavItem) => {
            setOpenGroups((prev) => ({
                ...prev,
                [`i:${item.label}`]: !isItemOpen(item),
            }));
        },
        [isItemOpen],
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
                    "fixed inset-y-0 left-0 z-50 flex h-dvh flex-col border-r border-sidebar-border bg-sidebar transition-[width,transform] duration-300 ease-out",
                    collapsed ? "w-[4.5rem]" : "w-64",
                    "-translate-x-full lg:static lg:z-auto lg:translate-x-0",
                    mobileOpen && "translate-x-0",
                )}
            >
                <header
                    className={cn(
                        "flex items-center border-b border-sidebar-border py-4",
                        collapsed
                            ? "justify-center px-2"
                            : "justify-between px-4",
                    )}
                >
                    <Link
                        href={brandHref}
                        prefetch={false}
                        onClick={onCloseMobile}
                        aria-label="Skyrict dashboard"
                        className={cn(
                            "text-sidebar-foreground",
                            collapsed && "hidden",
                        )}
                    >
                        {logoTone === "erp" ? (
                            <span className="inline-flex items-center gap-2.5">
                                <span className="flex size-7 shrink-0 items-center justify-center rounded-lg bg-gradient-to-br from-emerald-300 to-emerald-400 text-emerald-950">
                                    <Blocks
                                        aria-hidden="true"
                                        className="size-4"
                                    />
                                </span>
                                {!collapsed ? (
                                    <span className="font-display text-lg font-semibold tracking-tight">
                                        Skyrict
                                    </span>
                                ) : null}
                            </span>
                        ) : (
                            <Logo wordmark={!collapsed} tone={logoTone} mark="rounded" />
                        )}
                    </Link>
                    <button
                        type="button"
                        onClick={onToggleCollapsed}
                        aria-expanded={!collapsed}
                        aria-label={
                            collapsed ? "Expand sidebar" : "Collapse sidebar"
                        }
                        title={
                            collapsed ? "Expand sidebar" : "Collapse sidebar"
                        }
                        className="flex size-8 shrink-0 items-center justify-center rounded-lg text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
                    >
                        {collapsed ? (
                            <PanelLeftOpen
                                aria-hidden="true"
                                className="size-4"
                            />
                        ) : (
                            <PanelLeftClose
                                aria-hidden="true"
                                className="size-4"
                            />
                        )}
                    </button>
                </header>

                <nav
                    className="flex-1 space-y-1 overflow-y-auto scrollbar-hide px-3 py-4"
                    aria-label="Dashboard"
                >
                    {navGroups.map((group) => {
                        const open = isGroupOpen(group);
                        const headerActive = group.collapsible
                            ? group.items.some((item) =>
                                  isSidebarItemActive(pathname, item),
                              )
                            : false;

                        let header: React.ReactNode;
                        if (group.collapsible) {
                            const Icon = group.items[0]?.icon;
                            header = (
                                <button
                                    type="button"
                                    onClick={() => toggleGroup(group)}
                                    aria-expanded={open}
                                    title={collapsed ? group.label : undefined}
                                    className={cn(
                                        "group relative flex w-full items-center gap-3 rounded-lg text-sm font-semibold transition-colors",
                                        collapsed
                                            ? "justify-center px-0 py-2.5"
                                            : "px-3 py-2",
                                        headerActive
                                            ? "bg-sidebar-accent text-sidebar-accent-foreground"
                                            : "text-foreground hover:bg-muted/60 hover:text-foreground",
                                    )}
                                >
                                    {headerActive ? (
                                        <span
                                            aria-hidden="true"
                                            className="absolute top-1/2 left-0 h-5 w-0.5 -translate-y-1/2 rounded-full bg-primary"
                                        />
                                    ) : null}
                                    {Icon ? (
                                        <Icon
                                            aria-hidden="true"
                                            className={cn(
                                                "size-[18px] shrink-0",
                                                headerActive && "text-primary",
                                            )}
                                        />
                                    ) : null}
                                    {!collapsed ? (
                                        <>
                                            <span className="truncate">
                                                {group.label}
                                            </span>
                                            <ChevronDown
                                                aria-hidden="true"
                                                className={cn(
                                                    "ml-auto size-4 shrink-0 transition-transform",
                                                    open && "rotate-180",
                                                )}
                                            />
                                        </>
                                    ) : null}
                                </button>
                            );
                        } else {
                            header = collapsed ? (
                                <div
                                    className="mx-1 h-px bg-sidebar-border"
                                    aria-hidden="true"
                                />
                            ) : (
                                <p className="px-3 pt-3 pb-1 text-[11px] font-semibold tracking-wider text-muted-foreground/80 uppercase">
                                    {group.label}
                                </p>
                            );
                        }

                        return (
                            <div key={group.label} className="space-y-1">
                                {header}
                                {!group.collapsible || (!collapsed && open) ? (
                                    <div className="space-y-1">
                                        {group.items.map((item) =>
                                            item.children ? (
                                                <CollapsibleNavItem
                                                    key={item.label}
                                                    item={item}
                                                    collapsed={collapsed}
                                                    pathname={pathname}
                                                    onCloseMobile={
                                                        onCloseMobile
                                                    }
                                                    open={isItemOpen(item)}
                                                    onToggle={() =>
                                                        toggleItem(item)
                                                    }
                                                />
                                            ) : (
                                                <SidebarLink
                                                    key={item.href}
                                                    item={item}
                                                    collapsed={collapsed}
                                                    pathname={pathname}
                                                    onCloseMobile={
                                                        onCloseMobile
                                                    }
                                                    indented={group.collapsible}
                                                />
                                            ),
                                        )}
                                    </div>
                                ) : null}
                            </div>
                        );
                    })}
                    {navGroups.length > 0 ? (
                        <div
                            className="my-1 h-px bg-sidebar-border"
                            aria-hidden="true"
                        />
                    ) : null}
                </nav>

                {showBackToOverview ? (
                    <div className="border-t border-sidebar-border p-3">
                        <Link
                            href="/"
                            prefetch={false}
                            onClick={onCloseMobile}
                            data-tour="back-to-overview"
                            title={collapsed ? "Back to overview" : undefined}
                            className={cn(
                                "group flex items-center gap-3 rounded-lg text-sm font-medium transition-colors",
                                collapsed
                                    ? "justify-center px-0 py-2.5"
                                    : "px-3 py-2",
                                "text-muted-foreground hover:bg-muted/60 hover:text-foreground",
                            )}
                        >
                            <ArrowLeft
                                aria-hidden="true"
                                className="size-[18px] shrink-0 transition-transform group-hover:-translate-x-0.5"
                            />
                            {!collapsed ? (
                                <span className="truncate">
                                    Back to overview
                                </span>
                            ) : null}
                        </Link>
                    </div>
                ) : null}

                {accountItems.length > 0 ? (
                    <div className="space-y-1 border-t border-sidebar-border p-3">
                        {accountItems.map((item) => (
                            <SidebarLink
                                key={item.href}
                                item={item}
                                collapsed={collapsed}
                                pathname={pathname}
                                onCloseMobile={onCloseMobile}
                            />
                        ))}
                    </div>
                ) : null}

                <footer
                    data-tour="sidebar-profile"
                    className="border-t border-sidebar-border p-3"
                >
                    <UserMenu collapsed={collapsed} demoProfile={demoProfile} />
                </footer>
            </aside>
        </>
    );
}
