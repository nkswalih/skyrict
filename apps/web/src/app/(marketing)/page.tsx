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

export const metadata: Metadata = {
    title: {
        absolute: site.title,
    },
    description: site.description,
    alternates: {
        canonical: "/",
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
