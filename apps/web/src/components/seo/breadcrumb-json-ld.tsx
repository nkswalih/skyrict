import { JsonLd } from "@/components/seo/json-ld";
import { site } from "@/config";

export interface BreadcrumbItem {
    name: string;
    path: string;
}

/**
 * BreadcrumbList structured data for a page.
 *
 * Paths resolve against the marketing host by default. Docs pages pass the
 * docs origin because that is their canonical host.
 */
export function BreadcrumbJsonLd({
    items,
    baseUrl = site.url,
}: {
    items: BreadcrumbItem[];
    baseUrl?: string;
}) {
    const data = {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        itemListElement: items.map((item, index) => ({
            "@type": "ListItem",
            position: index + 1,
            name: item.name,
            item: new URL(item.path, baseUrl).toString(),
        })),
    };

    return <JsonLd data={data} />;
}
