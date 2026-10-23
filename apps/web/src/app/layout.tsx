import type { Metadata } from "next";
import { Bricolage_Grotesque, Inter, JetBrains_Mono } from "next/font/google";

import { Providers } from "@/app/providers";
import { site } from "@/config";
import "@/styles/globals.css";

const inter = Inter({
    subsets: ["latin"],
    variable: "--font-sans",
});

const bricolage = Bricolage_Grotesque({
    subsets: ["latin"],
    variable: "--font-display",
});

const jetbrainsMono = JetBrains_Mono({
    subsets: ["latin"],
    variable: "--font-mono",
});

export const metadata: Metadata = {
    metadataBase: new URL(site.url),
    title: {
        default: site.title,
        template: `%s · ${site.name}`,
    },
    description: site.description,
    keywords: [
        "Skyrict",
        "AI business operating system",
        "AI ERP platform",
        "business operations software",
        "inventory management software",
        "sales and order management",
        "AI agents for business",
    ],
    authors: [{ name: site.name }],
    applicationName: site.name,
    manifest: "/site.webmanifest",
    icons: {
        icon: [
            {
                url: "/favicon.ico",
                sizes: "any",
                type: "image/x-icon",
            },
            {
                url: "/favicon-16x16.png",
                sizes: "16x16",
                type: "image/png",
            },
            {
                url: "/favicon-32x32.png",
                sizes: "32x32",
                type: "image/png",
            },
            {
                url: "/android-chrome-192x192.png",
                sizes: "192x192",
                type: "image/png",
            },
            {
                url: "/android-chrome-512x512.png",
                sizes: "512x512",
                type: "image/png",
            },
        ],
        shortcut: "/favicon.ico",
        apple: [
            {
                url: "/apple-touch-icon.png",
                sizes: "180x180",
                type: "image/png",
            },
        ],
    },
    appleWebApp: {
        capable: true,
        title: site.name,
        statusBarStyle: "default",
    },
    openGraph: {
        type: "website",
        locale: "en_US",
        url: "/",
        siteName: site.name,
        title: site.title,
        description: site.description,
    },
    twitter: {
        card: "summary_large_image",
        title: site.title,
        description: site.description,
    },
};

export default function RootLayout({
    children,
}: {
    children: React.ReactNode;
}) {
    return (
        <html
            lang="en"
            suppressHydrationWarning
            data-scroll-behavior="smooth"
            className={`${inter.variable} ${bricolage.variable} ${jetbrainsMono.variable}`}
        >
            <body>
                <Providers>{children}</Providers>
            </body>
        </html>
    );
}
