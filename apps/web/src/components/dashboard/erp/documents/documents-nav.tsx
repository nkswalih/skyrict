"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { FileText, FolderOpen, LayoutDashboard, type LucideIcon } from "lucide-react";

import { cn } from "@/lib/utils";

const DOCUMENTS_ITEMS: { href: string; label: string; icon: LucideIcon }[] = [
    {
        href: "/dashboard/erp/documents",
        label: "Overview",
        icon: LayoutDashboard,
    },
    {
        href: "/dashboard/erp/documents/list",
        label: "All documents",
        icon: FolderOpen,
    },
];

export function DocumentsNav() {
    const pathname = usePathname();

    return (
        <nav
            aria-label="Documents sections"
            className="flex flex-wrap items-center gap-1.5"
        >
            {DOCUMENTS_ITEMS.map((item) => {
                const Icon = item.icon;
                const active =
                    item.href === "/dashboard/erp/documents"
                        ? pathname === item.href
                        : pathname === item.href ||
                          pathname.startsWith(`${item.href}/`);
                return (
                    <Link
                        key={item.href}
                        href={item.href}
                        aria-current={active ? "page" : undefined}
                        className={cn(
                            "inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 text-sm font-medium transition-colors",
                            active
                                ? "bg-primary text-primary-foreground"
                                : "text-muted-foreground hover:bg-muted hover:text-foreground",
                        )}
                    >
                        <Icon aria-hidden="true" className="size-4" />
                        {item.label}
                    </Link>
                );
            })}
        </nav>
    );
}

/** Small brand mark used in the page header (mirrors other modules). */
export function DocumentsIcon({ className }: { className?: string }) {
    return <FileText aria-hidden="true" className={className} />;
}