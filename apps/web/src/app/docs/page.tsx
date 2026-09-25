import type { Metadata } from "next";
import Link from "next/link";
import { ChevronRight } from "lucide-react";

import {
    docArticles,
    docCategories,
    pathFor,
    popularArticles,
} from "@/content/docs";
import { cn } from "@/lib/utils";

export const metadata: Metadata = {
    alternates: {
        // Docs-surface root: resolved against the docs layout metadataBase
        // (https://docs.skyrict.in), with no /docs prefix in the browser URL.
        canonical: "/",
    },
};

function GuideRow({
    href,
    title,
    description,
    index,
}: {
    href: string;
    title: string;
    description: string;
    index: number;
}) {
    return (
        <li>
            <Link
                href={href}
                className="group flex items-center gap-4 px-4 py-3.5 outline-none transition-colors hover:bg-muted/50 focus-visible:bg-muted/50"
            >
                <span className="hidden w-6 shrink-0 font-mono text-xs text-muted-foreground/60 sm:block">
                    {String(index).padStart(2, "0")}
                </span>
                <span className="min-w-0 flex-1">
                    <span className="block truncate text-sm font-medium text-foreground">
                        {title}
                    </span>
                    <span className="mt-0.5 block truncate text-xs text-muted-foreground">
                        {description}
                    </span>
                </span>
                <ChevronRight
                    aria-hidden="true"
                    className={cn(
                        "size-4 shrink-0 text-muted-foreground/40",
                        "transition-colors group-hover:text-foreground",
                    )}
                />
            </Link>
        </li>
    );
}

function GuideList({
    articles,
    startIndex = 1,
}: {
    articles: typeof docArticles;
    startIndex?: number;
}) {
    return (
        <ol className="divide-y divide-border overflow-hidden rounded-xl border border-border bg-card">
            {articles.map((article, position) => (
                <GuideRow
                    key={`${article.categoryId}/${article.slug}`}
                    href={pathFor(article.categoryId, article.slug)}
                    title={article.title}
                    description={article.description}
                    index={startIndex + position}
                />
            ))}
        </ol>
    );
}

export default function DocsHomePage() {
    return (
        <div className="mx-auto w-full max-w-3xl px-6 py-10 lg:py-14">
            <h1 className="font-display text-3xl font-semibold tracking-tight text-foreground">
                Skyrict Docs
            </h1>
            <p className="mt-2 max-w-2xl text-sm leading-relaxed text-muted-foreground">
                Guides for connecting operations, reading live signals, and
                running your business with Skyrict.
            </p>

            <section aria-labelledby="popular-heading" className="mt-10">
                <h2
                    id="popular-heading"
                    className="font-mono text-[11px] uppercase tracking-[0.16em] text-muted-foreground"
                >
                    Popular
                </h2>
                <div className="mt-3">
                    <GuideList articles={popularArticles} />
                </div>
            </section>

            <div className="mt-12 space-y-12">
                {docCategories.map((category) => {
                    const guides = docArticles.filter(
                        (article) => article.categoryId === category.id,
                    );
                    if (guides.length === 0) return null;
                    return (
                        <section
                            key={category.id}
                            aria-labelledby={`${category.id}-heading`}
                        >
                            <div className="flex items-baseline justify-between gap-4">
                                <h2
                                    id={`${category.id}-heading`}
                                    className="font-mono text-[11px] uppercase tracking-[0.16em] text-muted-foreground"
                                >
                                    {category.name}
                                </h2>
                                <span className="font-mono text-xs text-muted-foreground/60">
                                    {guides.length}
                                </span>
                            </div>
                            <div className="mt-3">
                                <GuideList
                                    articles={guides}
                                    startIndex={categoryStart(category.id)}
                                />
                            </div>
                        </section>
                    );
                })}
            </div>
        </div>
    );
}

/** Global first index of a category across the flattened guide order. */
function categoryStart(categoryId: string): number {
    let position = 1;
    for (const category of docCategories) {
        if (category.id === categoryId) break;
        position += docArticles.filter(
            (article) => article.categoryId === category.id,
        ).length;
    }
    return position;
}