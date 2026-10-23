"use client";

import { useEffect, useState } from "react";
import { ArrowUpRight, Menu, X } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";

import { Logo } from "@/components/brand/logo";
import { Button } from "@/components/ui/button";
import {
    Dialog,
    DialogClose,
    DialogContent,
    DialogTitle,
} from "@/components/ui/dialog";
import { navLinks } from "@/config";
import { cn } from "@/lib/utils";

function Header() {
    const [open, setOpen] = useState(false);
    const pathname = usePathname();

    useEffect(() => {
        const media = window.matchMedia("(min-width: 1024px)");
        const onChange = () => {
            if (media.matches) setOpen(false);
        };

        media.addEventListener("change", onChange);
        return () => media.removeEventListener("change", onChange);
    }, []);

    const isActive = (href: string) =>
        href === "/"
            ? pathname === "/"
            : pathname === href || pathname.startsWith(`${href}/`);

    return (
        <>
            <header
                className={cn(
                    "sticky top-0 z-40 px-4 pt-4 sm:px-6",
                    open && "pointer-events-none z-[60]",
                )}
            >
                <div className="relative mx-auto h-16 w-full max-w-[1120px]">
                    <div className="absolute inset-x-0 top-0 grid h-16 grid-cols-[1fr_auto] items-center gap-4 rounded-full border border-marketing-ink/10 bg-white px-3 lg:grid-cols-[auto_1fr_auto] lg:px-4">
                        <Link
                            href="/"
                            aria-label="Skyrict home"
                            className="flex w-fit items-center rounded-full outline-none focus-visible:ring-3 focus-visible:ring-marketing-sky/60"
                        >
                            <Logo className="text-marketing-ink" mark="image" />
                        </Link>

                        <nav
                            aria-label="Primary"
                            className="hidden justify-self-center rounded-full border border-marketing-ink/[0.06] bg-marketing-ink/[0.035] p-1 lg:flex"
                        >
                            {navLinks.map((link) => {
                                const active = isActive(link.href);
                                return (
                                    <Link
                                        key={link.href}
                                        href={link.href}
                                        aria-current={
                                            active ? "page" : undefined
                                        }
                                        className={cn(
                                            "group flex items-center gap-2 rounded-full px-3.5 py-2 text-[13px] font-medium transition-colors",
                                            active
                                                ? "bg-white text-marketing-ink shadow-[0_3px_2px_rgba(10,47,62,0.08)]"
                                                : "text-marketing-muted hover:bg-marketing-paper/70 hover:text-marketing-ink",
                                        )}
                                    >
                                        {/* <span
                                            aria-hidden="true"
                                            className={cn(
                                                "size-1.5 rounded-full bg-marketing-sky transition-opacity",
                                                active
                                                    ? "opacity-100"
                                                    : "opacity-0 group-hover:opacity-70",
                                            )}
                                        /> */}
                                        {link.label}
                                    </Link>
                                );
                            })}
                        </nav>

                        <div className="hidden items-center gap-1 justify-self-end lg:flex">
                            <Button
                                asChild
                                variant="ghost"
                                size="pill"
                                className="text-marketing-muted hover:bg-marketing-ink/[0.04] hover:text-marketing-ink"
                            >
                                <Link href="/contact">Book a walkthrough</Link>
                            </Button>
                            <Button asChild variant="brand" size="pill">
                                <Link href="/signup">
                                    Get started
                                    <ArrowUpRight
                                        aria-hidden="true"
                                        className="size-4 transition-transform duration-200 group-hover/button:-translate-y-0.5 group-hover/button:translate-x-0.5"
                                    />
                                </Link>
                            </Button>
                        </div>

                        <Button
                            type="button"
                            variant="brand"
                            size="icon-lg"
                            className="size-10 justify-self-end rounded-full lg:hidden"
                            onClick={() => setOpen(true)}
                            aria-label="Open menu"
                            aria-haspopup="dialog"
                            aria-expanded={open}
                            aria-controls="marketing-mobile-nav"
                        >
                            <Menu aria-hidden="true" className="size-5" />
                        </Button>
                    </div>
                </div>
            </header>

            <Dialog open={open} onOpenChange={setOpen}>
                <DialogContent
                    id="marketing-mobile-nav"
                    showCloseButton={false}
                    overlayClassName="bg-marketing-ink/20 supports-backdrop-filter:backdrop-blur-none"
                    className="marketing-theme fixed left-4 right-4 top-[88px] z-50 flex max-h-[calc(100dvh-104px)] w-auto max-w-none translate-x-0 translate-y-0 flex-col gap-0 rounded-[1.75rem] border border-marketing-line bg-card p-0 text-marketing-ink shadow-[0_24px_60px_-20px_rgba(10,47,62,0.3)] ring-0 outline-none duration-150 data-open:animate-in data-open:fade-in-0 data-open:slide-in-from-top-2 data-open:zoom-in-100 data-open:duration-200 data-closed:animate-out data-closed:fade-out-0 data-closed:slide-out-to-top-2 data-closed:zoom-out-100 data-closed:duration-150 sm:left-6 sm:right-6 sm:max-w-none"
                >
                    <DialogTitle className="sr-only">Navigation</DialogTitle>

                    <div className="flex h-11 shrink-0 items-center justify-end border-b border-marketing-line/80 pr-3">
                        <DialogClose asChild>
                            <Button
                                variant="brand"
                                size="icon-lg"
                                className="size-9 rounded-full"
                                aria-label="Close menu"
                            >
                                <X aria-hidden="true" className="size-4" />
                            </Button>
                        </DialogClose>
                    </div>

                    <nav
                        aria-label="Mobile"
                        className="flex min-h-0 flex-col overflow-y-auto overscroll-contain"
                    >
                        {navLinks.map((link, index) => {
                            const active = isActive(link.href);
                            return (
                                <Link
                                    key={link.href}
                                    href={link.href}
                                    onClick={() => setOpen(false)}
                                    aria-current={active ? "page" : undefined}
                                    className="sky-anim group flex items-center gap-3 border-b border-marketing-line/80 px-5 py-3 last:border-b-0"
                                    style={{
                                        animationDelay: `${50 + index * 30}ms`,
                                        animationDuration: "280ms",
                                    }}
                                >
                                    <span
                                        className={cn(
                                            "font-display text-[clamp(1.5rem,5.5vw,1.9rem)] leading-none font-semibold tracking-tight",
                                            active
                                                ? "text-marketing-ink"
                                                : "text-marketing-ink/75 group-hover:text-marketing-ink",
                                        )}
                                    >
                                        {link.label}
                                    </span>
                                    <ArrowUpRight
                                        aria-hidden="true"
                                        className="ml-auto size-4 text-marketing-muted transition-transform duration-200 group-hover:-translate-y-0.5 group-hover:translate-x-0.5 group-hover:text-marketing-ink"
                                    />
                                </Link>
                            );
                        })}
                    </nav>

                    <div
                        className="sky-anim flex shrink-0 items-center gap-2 border-t border-marketing-line/80 px-4 py-3 pb-[max(0.75rem,env(safe-area-inset-bottom))]"
                        style={{
                            animationDelay: `${50 + navLinks.length * 30}ms`,
                            animationDuration: "280ms",
                        }}
                    >
                        <Button
                            asChild
                            variant="outline"
                            size="pill"
                            className="flex-1 rounded-full border-marketing-ink/15 bg-transparent px-3.5 text-marketing-ink hover:bg-marketing-ink/[0.04]"
                        >
                            <Link
                                href="/contact"
                                onClick={() => setOpen(false)}
                            >
                                Book a walkthrough
                            </Link>
                        </Button>
                        <Button
                            asChild
                            variant="brand"
                            size="pill"
                            className="flex-1 px-3.5"
                        >
                            <Link href="/signup" onClick={() => setOpen(false)}>
                                Get started
                                <ArrowUpRight
                                    aria-hidden="true"
                                    className="size-3.5"
                                />
                            </Link>
                        </Button>
                    </div>
                </DialogContent>
            </Dialog>
        </>
    );
}

export { Header };
