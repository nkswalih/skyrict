import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { ChevronLeft, ChevronRight } from "lucide-react";

import { CopyPageLink } from "@/components/docs/copy-page-link";
import { Feedback } from "@/components/docs/feedback";
import { Toc } from "@/components/docs/toc";
import {
    docArticles,
    getArticle,
    getCategory,
    orderedArticles,
    pathFor,
    relatedFor,
    surfacePathFor,
    type DocArticle,
} from "@/content/docs";
import { cn } from "@/lib/utils";

type PageProps = {
    params: Promise<{ category: string; slug: string }>;
};

export function generateStaticParams() {
    return docArticles.map((article) => ({
        category: article.categoryId,
        slug: article.slug,
    }));
}

export async function generateMetadata({
    params,
}: PageProps): Promise<Metadata> {
    const { category, slug } = await params;
    const article = getArticle(category, slug);
    if (!article) return {};
    return {
        title: article.title,
        description: article.description,
        alternates: {
            canonical: surfacePathFor(category, slug),
        },
    };
}

function Breadcrumb({ article }: { article: DocArticle }) {
    const category = getCategory(article.categoryId);
    const firstInCategory = orderedArticles().find(
        (entry) => entry.categoryId === article.categoryId,
    );

    return (
        <nav aria-label="Breadcrumb">
            <ol className="flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
                <li>
                    <Link
                        href="/docs"
                        className="underline-offset-4 hover:text-foreground hover:underline"
                    >
                        Docs
                    </Link>
                </li>
                <li aria-hidden="true">
                    <ChevronRight className="size-3" />
                </li>
                <li>
                    {category && firstInCategory ? (
                        <Link
                            href={pathFor(
                                firstInCategory.categoryId,
                                firstInCategory.slug,
                            )}
                            className="underline-offset-4 hover:text-foreground hover:underline"
                        >
                            {category.name}
                        </Link>
                    ) : (
                        <span>{category?.name ?? ""}</span>
                    )}
                </li>
                <li aria-hidden="true">
                    <ChevronRight className="size-3" />
                </li>
                <li aria-current="page" className="text-foreground">
                    {article.title}
                </li>
            </ol>
        </nav>
    );
}

function Sections({ article }: { article: DocArticle }) {
    return (
        <>
            {article.sections.map((section) => (
                <section
                    key={section.id}
                    aria-labelledby={section.id}
                    className="mt-10"
                >
                    <h2
                        id={section.id}
                        className="scroll-mt-20 font-display text-lg font-semibold tracking-tight text-foreground"
                    >
                        {section.title}
                    </h2>
                    {section.paragraphs?.map((paragraph, index) => (
                        <p
                            key={index}
                            className="mt-3 text-[15px] leading-7 text-foreground/85"
                        >
                            {paragraph}
                        </p>
                    ))}
                    {section.bullets && section.bullets.length > 0 ? (
                        <ul className="mt-4 space-y-2">
                            {section.bullets.map((item, index) => (
                                <li
                                    key={index}
                                    className="flex gap-3 text-[15px] leading-7 text-foreground/85"
                                >
                                    <span
                                        aria-hidden="true"
                                        className="mt-[0.65em] size-1 shrink-0 rounded-full bg-primary/60"
                                    />
                                    {item}
                                </li>
                            ))}
                        </ul>
                    ) : null}
                    {section.steps && section.steps.length > 0 ? (
                        <ol className="mt-4 space-y-3">
                            {section.steps.map((step, index) => (
                                <li key={index} className="flex gap-3">
                                    <span
                                        aria-hidden="true"
                                        className="mt-0.5 flex size-5 shrink-0 items-center justify-center rounded-md border border-border bg-card font-mono text-[11px] text-muted-foreground"
                                    >
                                        {index + 1}
                                    </span>
                                    <span className="text-[15px] leading-7 text-foreground/85">
                                        {step}
                                    </span>
                                </li>
                            ))}
                        </ol>
                    ) : null}
                    {section.note ? (
                        <div className="mt-4 rounded-r-lg border-l-2 border-primary/50 bg-primary/5 py-3 pl-4 pr-4">
                            <p className="text-sm leading-relaxed text-foreground/80">
                                <span className="font-medium text-foreground">
                                    Note.{" "}
                                </span>
                                {section.note}
                            </p>
                        </div>
                    ) : null}
                </section>
            ))}
        </>
    );
}

function RelatedGuides({ article }: { article: DocArticle }) {
    const related = relatedFor(article);
    if (related.length === 0) return null;
    return (
        <section
            aria-labelledby="related-guides"
            className="mt-12 border-t border-border pt-6"
        >
            <h2
                id="related-guides"
                className="font-mono text-[11px] uppercase tracking-[0.16em] text-muted-foreground"
            >
                Related guides
            </h2>
            <ul className="mt-3 grid gap-2 sm:grid-cols-2">
                {related.map((entry) => (
                    <li key={entry.href}>
                        <Link
                            href={entry.href}
                            className={cn(
                                "group flex items-center justify-between gap-3 rounded-lg border border-border bg-card px-3.5 py-2.5 text-sm font-medium text-foreground transition-colors",
                                "hover:border-primary/40 focus-visible:ring-3 focus-visible:ring-ring/50 outline-none",
                            )}
                        >
                            {entry.title}
                            <ChevronRight
                                aria-hidden="true"
                                className="size-3.5 shrink-0 text-muted-foreground/40 transition-colors group-hover:text-foreground"
                            />
                        </Link>
                    </li>
                ))}
            </ul>
        </section>
    );
}

function Pager({ index }: { index: number }) {
    const order = orderedArticles();
    const previous = index > 0 ? order[index - 1] : null;
    const next = index < order.length - 1 ? order[index + 1] : null;

    return (
        <nav
            aria-label="Guide navigation"
            className="mt-12 grid gap-3 border-t border-border pt-6 sm:grid-cols-2"
        >
            {previous ? (
                <Link
                    href={pathFor(previous.categoryId, previous.slug)}
                    className={cn(
                        "group rounded-lg border border-border bg-card px-4 py-3.5 outline-none transition-colors",
                        "hover:border-primary/40 focus-visible:ring-3 focus-visible:ring-ring/50",
                    )}
                >
                    <span className="flex items-center gap-1.5 font-mono text-[11px] uppercase tracking-[0.14em] text-muted-foreground">
                        <ChevronLeft
                            aria-hidden="true"
                            className="size-3 transition-transform group-hover:-translate-x-0.5"
                        />
                        Previous guide
                    </span>
                    <span className="mt-1.5 block truncate text-sm font-medium text-foreground">
                        {previous.title}
                    </span>
                </Link>
            ) : (
                <span aria-hidden="true" />
            )}
            {next ? (
                <Link
                    href={pathFor(next.categoryId, next.slug)}
                    className={cn(
                        "group rounded-lg border border-border bg-card px-4 py-3.5 text-right outline-none transition-colors",
                        "hover:border-primary/40 focus-visible:ring-3 focus-visible:ring-ring/50",
                    )}
                >
                    <span className="flex items-center justify-end gap-1.5 font-mono text-[11px] uppercase tracking-[0.14em] text-muted-foreground">
                        Next guide
                        <ChevronRight
                            aria-hidden="true"
                            className="size-3 transition-transform group-hover:translate-x-0.5"
                        />
                    </span>
                    <span className="mt-1.5 block truncate text-sm font-medium text-foreground">
                        {next.title}
                    </span>
                </Link>
            ) : (
                <span aria-hidden="true" />
            )}
        </nav>
    );
}

export default async function ArticlePage({ params }: PageProps) {
    const { category, slug } = await params;
    const article = getArticle(category, slug);
    if (!article) notFound();

    const order = orderedArticles();
    const index = order.findIndex(
        (entry) =>
            entry.categoryId === article.categoryId &&
            entry.slug === article.slug,
    );
    const href = pathFor(article.categoryId, article.slug);

    return (
        <div className="mx-auto flex w-full max-w-[960px] justify-center gap-10 px-6 py-10 lg:py-12">
            <div className="min-w-0 w-full max-w-2xl">
                <Breadcrumb article={article} />

                <div className="mt-6 flex items-start justify-between gap-4">
                    <h1 className="font-display text-2xl font-semibold tracking-tight text-foreground sm:text-3xl">
                        {article.title}
                    </h1>
                    <CopyPageLink href={href} />
                </div>

                <p className="mt-3 max-w-xl text-base leading-relaxed text-muted-foreground">
                    {article.description}
                </p>

                {article.cta ? (
                    <div className="mt-6 rounded-lg border border-primary/25 bg-primary/5 px-4 py-3.5">
                        <p className="text-sm leading-relaxed text-foreground/85">
                            Some steps in this guide require a Skyrict account.
                        </p>
                        <Link
                            href="/signup"
                            className="mt-2 inline-flex items-center gap-1.5 rounded-md bg-primary px-3 py-1.5 text-sm font-medium text-primary-foreground transition-colors outline-none hover:bg-primary/80 focus-visible:ring-3 focus-visible:ring-ring/50"
                        >
                            Create a Skyrict account
                        </Link>
                    </div>
                ) : null}

                <Sections article={article} />

                <RelatedGuides article={article} />

                <Pager index={index} />

                <Feedback />
            </div>

            <Toc
                sections={article.sections}
                className="sticky top-20 hidden w-52 shrink-0 self-start pt-14 xl:block"
            />
        </div>
    );
}