"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { Menu, Search, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { Logo } from "@/components/brand/logo";
import { Button } from "@/components/ui/button";
import { docCategories, docsActiveHref, docsNav } from "@/content/docs";
import { cn } from "@/lib/utils";

function NavSidebar({
    activeHref,
    onNavigate,
    className,
    id,
}: {
    activeHref: string;
    onNavigate?: () => void;
    className?: string;
    id?: string;
}) {
    const nav = docsNav();

    return (
        <nav
            id={id}
            aria-label="Documentation"
            className={cn("overflow-y-auto px-3 py-6", className)}
        >
            {docCategories.map((category) => (
                <div key={category.id} className="mb-7">
                    <p className="px-2 pb-2 font-mono text-[11px] uppercase tracking-[0.14em] text-muted-foreground">
                        {category.name}
                    </p>
                    <ul className="space-y-0.5">
                        {nav
                            .filter((link) => link.category.id === category.id)
                            .map((link) => {
                                const active = activeHref === link.href;
                                return (
                                    <li key={link.href}>
                                        <Link
                                            href={link.href}
                                            onClick={onNavigate}
                                            aria-current={
                                                active ? "page" : undefined
                                            }
                                            className={cn(
                                                "block truncate rounded-md px-2 py-1.5 text-sm outline-none transition-colors focus-visible:ring-2 focus-visible:ring-ring/50",
                                                active
                                                    ? "bg-primary/5 font-medium text-primary"
                                                    : "text-muted-foreground hover:bg-muted/60 hover:text-foreground",
                                            )}
                                        >
                                            {link.title}
                                        </Link>
                                    </li>
                                );
                            })}
                    </ul>
                </div>
            ))}
        </nav>
    );
}

function DocsShell({ children }: { children: React.ReactNode }) {
    const pathname = usePathname();
    const router = useRouter();
    const [navigationOpen, setNavigationOpen] = useState(false);
    const menuButtonRef = useRef<HTMLButtonElement>(null);

    // On docs.skyrict.in the middleware serves the /docs tree at the surface
    // root, so usePathname() reports /getting-started while nav hrefs use the
    // /docs form; normalize so the sidebar highlights the current article on
    // every surface (docs hostname, apex, and Vercel fallback).
    const activeHref = docsActiveHref(pathname);

    useEffect(() => {
        function onKeyDown(event: KeyboardEvent) {
            if (
                (event.metaKey || event.ctrlKey) &&
                event.key.toLowerCase() === "k"
            ) {
                event.preventDefault();
                router.push("/docs/search");
            }
        }
        window.addEventListener("keydown", onKeyDown);
        return () => window.removeEventListener("keydown", onKeyDown);
    }, [router]);

    useEffect(() => {
        if (!navigationOpen) return;

        const previousOverflow = document.body.style.overflow;
        document.body.style.overflow = "hidden";

        const menuButton = menuButtonRef.current;

        function onKeyDown(event: KeyboardEvent) {
            if (event.key === "Escape") closeNavigation();
        }

        window.addEventListener("keydown", onKeyDown);
        return () => {
            document.body.style.overflow = previousOverflow;
            window.removeEventListener("keydown", onKeyDown);
            menuButton?.focus();
        };
    }, [navigationOpen]);

    function closeNavigation() {
        setNavigationOpen(false);
    }

    return (
        <>
            <header className="sticky top-0 z-40 border-b border-border/70 bg-background/95 backdrop-blur supports-backdrop-filter:bg-background/80">
                <div className="flex h-14 items-center gap-3 px-4 lg:px-6">
                    <Button
                        ref={menuButtonRef}
                        variant="ghost"
                        size="icon-sm"
                        className="lg:hidden"
                        aria-expanded={navigationOpen}
                        aria-controls="docs-navigation"
                        aria-label="Toggle documentation navigation"
                        onClick={() =>
                            setNavigationOpen((open) => !open)
                        }
                    >
                        {navigationOpen ? (
                            <X aria-hidden="true" />
                        ) : (
                            <Menu aria-hidden="true" />
                        )}
                    </Button>

                    <Link
                        href="/"
                        aria-label="Skyrict home"
                        className="flex min-w-0 items-center gap-2.5 text-foreground outline-none focus-visible:ring-2 focus-visible:ring-ring/50"
                    >
                        <Logo wordmark={false} className="[&>svg]:size-6" />
                        <span className="text-[15px] font-medium tracking-tight">
                            Skyrict
                        </span>
                    </Link>
                    <Link
                        href="/docs"
                        aria-label="Docs home"
                        className="hidden min-w-0 items-center gap-2.5 outline-none transition-colors focus-visible:ring-2 focus-visible:ring-ring/50 sm:flex"
                    >
                        <span
                            aria-hidden="true"
                            className="h-4 w-px bg-border"
                        />
                        <span className="text-sm text-muted-foreground">
                            Docs
                        </span>
                    </Link>

                    <div className="ml-auto flex items-center gap-2">
                        <Link
                            href="/docs/search"
                            className="hidden h-8 w-56 items-center gap-2 rounded-lg border border-border bg-card px-2.5 text-sm text-muted-foreground outline-none transition-colors hover:bg-muted/70 focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 sm:flex"
                        >
                            <Search
                                aria-hidden="true"
                                className="size-3.5 shrink-0"
                            />
                            <span className="flex-1 truncate text-left">
                                Search docs
                            </span>
                            <kbd className="rounded border border-border bg-background px-1 font-mono text-[10px] text-muted-foreground">
                                Ctrl K
                            </kbd>
                        </Link>

                        <Button
                            variant="ghost"
                            size="icon-sm"
                            asChild
                            className="sm:hidden"
                            aria-label="Search documentation"
                        >
                            <Link href="/docs/search">
                                <Search aria-hidden="true" />
                            </Link>
                        </Button>

                        <Button size="sm" asChild>
                            <Link href="/signup">Create account</Link>
                        </Button>
                    </div>
                </div>
            </header>

            <div className="flex flex-1 items-stretch">
                <NavSidebar
                    activeHref={activeHref}
                    className="sticky top-14 hidden max-h-[calc(100dvh-3.5rem)] w-64 shrink-0 self-start border-r border-border/70 lg:block"
                />

                <main className="min-w-0 flex-1">{children}</main>
            </div>

            {navigationOpen ? (
                <div className="fixed inset-0 z-50 lg:hidden">
                    <button
                        type="button"
                        aria-label="Close documentation navigation"
                        onClick={closeNavigation}
                        className="absolute inset-0 animate-in fade-in-0 bg-black/20 duration-150"
                    />
                    <div
                        role="dialog"
                        aria-modal="true"
                        aria-label="Documentation navigation"
                        className="absolute inset-y-0 left-0 w-72 max-w-[85vw] animate-in slide-in-from-left-full border-r border-border bg-background shadow-xl duration-200"
                    >
                        <div className="flex h-14 items-center justify-between border-b border-border/70 px-4">
                            <span className="flex items-center gap-2 text-foreground">
                                <Link
                                    href="/"
                                    aria-label="Skyrict home"
                                    className="flex items-center gap-2 outline-none focus-visible:ring-2 focus-visible:ring-ring/50"
                                >
                                    <Logo wordmark={false} className="[&>svg]:size-6" />
                                </Link>
                                <span className="text-[15px] font-medium tracking-tight">
                                    Docs
                                </span>
                            </span>
                            <Button
                                variant="ghost"
                                size="icon-sm"
                                onClick={closeNavigation}
                                aria-label="Close navigation"
                            >
                                <X aria-hidden="true" />
                            </Button>
                        </div>
                        <NavSidebar
                            id="docs-navigation"
                            activeHref={activeHref}
                            onNavigate={closeNavigation}
                            className="h-[calc(100dvh-3.5rem)]"
                        />
                    </div>
                </div>
            ) : null}
        </>
    );
}

export { DocsShell };