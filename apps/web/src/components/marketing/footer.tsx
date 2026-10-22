import Link from "next/link";
import { ArrowUpRight, Mail } from "lucide-react";

import { Logo } from "@/components/brand/logo";
import { AskAiAboutSkyrict } from "@/components/marketing/ask-ai";
import { cn } from "@/lib/utils";
import {
    contactEmail,
    footerColumns,
    footerLegalLinks,
    site,
    type FooterLink,
} from "@/config";

const githubUrl = "https://github.com/nkswalih/skyrict";

const footerLinkClass =
    "group inline-flex min-h-9 items-center gap-1.5 text-sm text-marketing-ink/70 transition-colors hover:text-marketing-ink hover:underline hover:decoration-marketing-sky hover:underline-offset-4 focus-visible:rounded-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-marketing-sky/60";

function isExternal(href?: string) {
    return href?.startsWith("http") ?? false;
}

function GitHubMark({ className }: { className?: string }) {
    return (
        <svg
            viewBox="0 0 24 24"
            aria-hidden="true"
            className={className}
            fill="currentColor"
        >
            <path d="M12 .5C5.73.5.5 5.73.5 12a11.5 11.5 0 0 0 7.86 10.92c.58.1.79-.25.79-.56v-2.02c-3.2.7-3.88-1.36-3.88-1.36-.52-1.33-1.28-1.68-1.28-1.68-1.04-.71.08-.7.08-.7 1.15.08 1.76 1.18 1.76 1.18 1.02 1.75 2.68 1.25 3.33.95.1-.74.4-1.25.73-1.54-2.55-.29-5.23-1.28-5.23-5.68 0-1.25.45-2.28 1.18-3.08-.12-.29-.51-1.46.11-3.04 0 0 .96-.31 3.15 1.18a10.9 10.9 0 0 1 5.74 0c2.19-1.49 3.15-1.18 3.15-1.18.62 1.58.23 2.75.11 3.04.73.8 1.18 1.83 1.18 3.08 0 4.41-2.69 5.38-5.25 5.67.41.36.78 1.08.78 2.18v3.23c0 .31.21.67.8.56A11.5 11.5 0 0 0 23.5 12C23.5 5.73 18.27.5 12 .5Z" />
        </svg>
    );
}

function FooterLinkItem({ link }: { link: FooterLink }) {
    if (link.soon || !link.href) {
        return (
            <li className="flex min-h-9 items-center gap-2 text-sm text-marketing-muted/50">
                {link.label}
                <span className="rounded-full border border-marketing-line px-1.5 py-0.5 font-mono text-[9px] uppercase tracking-[0.12em] text-marketing-muted/70">
                    Soon
                </span>
            </li>
        );
    }

    if (isExternal(link.href)) {
        return (
            <li>
                <a
                    href={link.href}
                    target="_blank"
                    rel="noopener noreferrer"
                    aria-label={`${link.label} (opens in a new tab)`}
                    className={footerLinkClass}
                >
                    {link.label}
                    <ArrowUpRight
                        aria-hidden="true"
                        className="size-3.5 text-marketing-muted transition-transform duration-200 group-hover:-translate-y-0.5 group-hover:translate-x-0.5 group-hover:text-marketing-ink"
                    />
                </a>
            </li>
        );
    }

    return (
        <li>
            <Link href={link.href} className={footerLinkClass}>
                {link.label}
            </Link>
        </li>
    );
}

function Footer() {
    const year = new Date().getFullYear();

    return (
        <footer className="border-t border-marketing-line bg-card">
            <div className="mx-auto w-full max-w-6xl px-6 pt-8 pb-4 sm:pt-10 sm:pb-6 lg:pt-16 lg:pb-8">
                <div className="grid gap-6 sm:gap-8 lg:grid-cols-[minmax(0,1.05fr)_minmax(0,1.95fr)] lg:gap-12">
                    <div className="max-w-sm">
                        <Link
                            href="/"
                            aria-label="Skyrict home"
                            className="inline-flex min-h-9 items-center rounded-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-marketing-sky/60"
                        >
                            <Logo className="text-marketing-ink" mark="image" />
                        </Link>

                        <p className="mt-4 font-display text-2xl font-semibold leading-[1.08] tracking-tight text-marketing-ink sm:mt-6 sm:text-[2rem]">
                            The whole picture, in time.
                        </p>

                        <AskAiAboutSkyrict className="mt-4 flex items-start text-left sm:mt-5 lg:hidden" />

                        <div className="mt-3 flex flex-wrap items-center gap-x-5 gap-y-2 sm:mt-4 lg:mt-6">
                            <a
                                href={githubUrl}
                                target="_blank"
                                rel="noopener noreferrer"
                                aria-label="Skyrict on GitHub (opens in a new tab)"
                                className="group inline-flex min-h-9 items-center gap-2 text-sm text-marketing-ink/70 transition-colors hover:text-marketing-ink"
                            >
                                <GitHubMark className="size-4" />
                                GitHub
                                <ArrowUpRight
                                    aria-hidden="true"
                                    className="size-3.5 text-marketing-muted transition-transform duration-200 group-hover:-translate-y-0.5 group-hover:translate-x-0.5 group-hover:text-marketing-ink"
                                />
                            </a>
                            <a
                                href={`mailto:${contactEmail}`}
                                className="inline-flex min-h-9 items-center gap-2 text-sm text-marketing-ink/70 transition-colors hover:text-marketing-ink"
                            >
                                <Mail aria-hidden="true" className="size-4" />
                                {contactEmail}
                            </a>
                        </div>
                    </div>

                    <nav
                        aria-label="Footer"
                        className="grid grid-cols-2 gap-x-8 gap-y-6 sm:grid-cols-3 sm:gap-x-10 sm:gap-y-8"
                    >
                        {footerColumns.map((column, index) => {
                            const spansOddLastColumn =
                                index === footerColumns.length - 1 &&
                                footerColumns.length % 2 === 1;

                            return (
                                <div
                                    key={column.title}
                                    className={cn(
                                        spansOddLastColumn &&
                                            "col-span-2 sm:col-span-1 lg:row-span-2",
                                    )}
                                >
                                    <p className="font-mono text-[10px] font-medium uppercase tracking-[0.18em] text-marketing-muted">
                                        {column.title}
                                    </p>
                                    <ul
                                        className={cn(
                                            "mt-2.5 space-y-0.5 sm:mt-3 sm:space-y-1",
                                            spansOddLastColumn &&
                                                "grid grid-cols-2 gap-x-8 gap-y-0.5 space-y-0 sm:block sm:space-y-1",
                                        )}
                                    >
                                        {column.links.map((link) => (
                                            <FooterLinkItem
                                                key={link.label}
                                                link={link}
                                            />
                                        ))}
                                    </ul>
                                </div>
                            );
                        })}
                        <AskAiAboutSkyrict className="hidden lg:col-span-2 lg:flex lg:self-end lg:justify-self-center" />
                    </nav>
                </div>

                <div className="mt-5 pb-2 sm:mt-8 sm:pb-2 lg:mt-10 lg:pb-3">
                    <div aria-hidden="true" className="flex items-center gap-3">
                        <span className="h-px flex-1 bg-marketing-line" />
                        <span className="size-1.5 rounded-full bg-marketing-sky" />
                    </div>
                    <p
                        aria-hidden="true"
                        className="marketing-footer-wordmark mt-1.5 select-none font-display tracking-[-0.075em] sm:-mt-1 lg:-mt-4"
                    >
                        Skyrict.
                    </p>
                </div>

                <div className="mt-3 flex flex-col gap-2 border-t border-marketing-line/80 pt-3 sm:mt-3 sm:flex-row sm:items-center sm:justify-between sm:gap-4 sm:pt-4">
                    <p className="font-mono text-[10px] uppercase tracking-[0.12em] text-marketing-muted sm:tracking-[0.16em]">
                        &copy; {year} {site.name}. All rights reserved.
                    </p>
                    <nav
                        aria-label="Legal"
                        className="flex flex-wrap items-center gap-x-5 gap-y-2"
                    >
                        {footerLegalLinks.map((link) => (
                            <Link
                                key={link.label}
                                href={link.href ?? "#"}
                                className="inline-flex min-h-9 items-center font-mono text-[10px] uppercase tracking-[0.16em] text-marketing-muted transition-colors hover:text-marketing-ink focus-visible:rounded-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-marketing-sky/60"
                            >
                                {link.label}
                            </Link>
                        ))}
                    </nav>
                </div>
            </div>
        </footer>
    );
}

export { Footer };
