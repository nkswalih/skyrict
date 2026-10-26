import { permanentRedirect } from "next/navigation";

import { getCategory, orderedArticles, pathFor } from "@/content/docs";

type PageProps = {
    params: Promise<{ category: string }>;
};

/** /docs/:category resolves to the first guide in that category. */
export default async function CategoryPage({ params }: PageProps) {
    const { category } = await params;
    const meta = getCategory(category);
    if (!meta) permanentRedirect("/docs");
    const first = orderedArticles().find(
        (article) => article.categoryId === category,
    );
    if (!first) permanentRedirect("/docs");
    permanentRedirect(pathFor(first.categoryId, first.slug));
}