import type { Metadata } from "next";

import { Footer } from "@/components/marketing/footer";
import { Header } from "@/components/marketing/header";
import { JsonLd } from "@/components/seo/json-ld";
import { site } from "@/config";

export const metadata: Metadata = {
    robots: {
        index: true,
        follow: true,
        googleBot: {
            index: true,
            follow: true,
            "max-image-preview": "large",
            "max-snippet": -1,
            "max-video-preview": -1,
        },
    },
    alternates: {
        canonical: "/",
    },
};

export default function MarketingLayout({
    children,
}: {
    children: React.ReactNode;
}) {
    const organization = {
        "@context": "https://schema.org",
        "@type": "Organization",
        "@id": `${site.url}/#organization`,
        name: site.name,
        url: site.url,
        logo: {
            "@type": "ImageObject",
            "@id": `${site.url}/#logo`,
            url: `${site.url}/skyrict_logo.png`,
            contentUrl: `${site.url}/skyrict_logo.png`,
            width: 1000,
            height: 1000,
            caption: site.name,
        },
        image: `${site.url}/skyrict_logo.png`,
        description: site.description,
        sameAs: ["https://github.com/nkswalih/skyrict"],
    };

    const website = {
        "@context": "https://schema.org",
        "@type": "WebSite",
        "@id": `${site.url}/#website`,
        url: site.url,
        name: site.name,
        description: site.description,
        publisher: {
            "@id": `${site.url}/#organization`,
        },
    };

    return (
        <div className="marketing-theme flex min-h-screen flex-col bg-marketing-paper text-marketing-ink">
            <JsonLd data={organization} />
            <JsonLd data={website} />
            <a
                href="#main-content"
                className="sr-only z-50 rounded-full bg-marketing-ink px-4 py-2 text-sm font-medium text-marketing-paper focus:not-sr-only focus:fixed focus:top-4 focus:left-4"
            >
                Skip to content
            </a>
            <Header />
            <main id="main-content" className="flex-1">
                {children}
            </main>
            <Footer />
        </div>
    );
}
