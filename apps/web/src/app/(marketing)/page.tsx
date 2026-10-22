import type { Metadata } from "next";

import { Agents } from "@/components/marketing/sections/agents";
import { Cta } from "@/components/marketing/sections/cta";
import { Faq } from "@/components/marketing/sections/faq";
import { Hero } from "@/components/marketing/sections/hero";
import { HowItWorks } from "@/components/marketing/sections/how-it-works";
import { Intelligence } from "@/components/marketing/sections/intelligence";
import { Operations } from "@/components/marketing/sections/operations";
import { Trust } from "@/components/marketing/sections/trust";
import { site } from "@/config";

const title = "Skyrict — the operating system for evidence-led companies";
const description =
    "Skyrict brings CRM, inventory, orders, finance, and people into one workspace, then reads the market alongside them. Run the business on live evidence.";

export const metadata: Metadata = {
    title: {
        absolute: title,
    },
    description,
    alternates: {
        canonical: "/",
    },
    openGraph: {
        title,
        description,
        url: "/",
        siteName: site.name,
        type: "website",
    },
    twitter: {
        card: "summary_large_image",
        title,
        description,
    },
};

export default function LandingPage() {
    return (
        <>
            <Hero />
            <HowItWorks />
            <Operations />
            <Intelligence />
            <Agents />
            <Trust />
            <Faq />
            <Cta />
        </>
    );
}
