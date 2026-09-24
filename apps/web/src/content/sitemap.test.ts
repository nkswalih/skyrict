import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

import { docArticles, docCategories, surfacePathFor } from "@/content/docs";

const marketingHost = "https://skyrict.in";
const docsHost = "https://docs.skyrict.in";

const readLocs = (publicPath: string): string[] => {
    const xml = readFileSync(
        fileURLToPath(new URL(`../../public/${publicPath}`, import.meta.url)),
        "utf8",
    );
    return [...xml.matchAll(/<loc>(.*?)<\/loc>/g)].map((match) => match[1]);
};

const expectLocs = (actual: string[], expected: string[]): void => {
    expect([...actual].sort()).toEqual([...expected].sort());
    expect(new Set(actual).size).toBe(actual.length);
};

describe("site index (public/sitemap.xml)", () => {
    it("references the marketing and docs sitemaps on their own hosts", () => {
        expectLocs(readLocs("sitemap.xml"), [
            `${marketingHost}/sitemap-marketing.xml`,
            `${docsHost}/sitemap-docs.xml`,
        ]);
    });
});

describe("marketing sitemap (public/sitemap-marketing.xml)", () => {
    it("lists the landing, market, and legal pages on the apex host", () => {
        expectLocs(readLocs("sitemap-marketing.xml"), [
            `${marketingHost}/`,
            `${marketingHost}/product`,
            `${marketingHost}/pricing`,
            `${marketingHost}/about`,
            `${marketingHost}/contact`,
            `${marketingHost}/terms`,
            `${marketingHost}/privacy`,
        ]);
    });
});

describe("docs sitemap (public/sitemap-docs.xml)", () => {
    it("covers every category and article from the docs registry", () => {
        const expected = [
            `${docsHost}/`,
            ...docCategories.map((category) => `${docsHost}/${category.id}`),
            ...docArticles.map((article) =>
                `${docsHost}${surfacePathFor(article.categoryId, article.slug)}`,
            ),
        ];
        expectLocs(readLocs("sitemap-docs.xml"), expected);
    });

    it("never leaks the search page into the index", () => {
        expect(readLocs("sitemap-docs.xml")).not.toContain(
            `${docsHost}/search`,
        );
    });
});