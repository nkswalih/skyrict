import { Plus } from "lucide-react";
import Link from "next/link";

import { RevealSection } from "@/components/marketing/reveal-section";

const faqItems = [
    {
        question: "What is Skyrict?",
        answer: "Skyrict is a scoped ERP with an AI agent workspace on top. It brings inventory, sales, cash, orders, CRM, and people into one system, and SkyAgent answers questions from those live records.",
    },
    {
        question: "How is this different from a dashboard?",
        answer: "A dashboard shows what happened. Skyrict holds the live records and lets you ask questions across them in plain language. SkyAgent can point to the records and sources behind an answer so you can check it before you act.",
    },
    {
        question: "Do I have to replace my ERP?",
        answer: "Skyrict is its own scoped ERP, not a connector for an existing one. You start with the modules you need instead of a full 400-module rollout. If you already run an ERP, talk to us about what you need to bring across.",
    },
    {
        question: "What does Skyrict cover?",
        answer: "The live modules are inventory, orders, sales, finance, CRM, HR, payroll, documents, approvals, and reporting. Market signals are in development: the signal collection engine is planned, and the intelligence workspace is in progress.",
    },
    {
        question: "How is my data protected?",
        answer: "Every workspace is tenant-scoped, with role-based permissions, MFA, and email verification. The security model is documented in the open, and the source is public.",
    },
    {
        question: "How do I get started?",
        answer: "Starter is free forever. Paid plans begin with a 14-day trial, no credit card required. Create an account, set up your workspace, and ask SkyAgent your first question. For a guided rollout, book a demo.",
    },
];

function Faq() {
    return (
        <section
            id="faq"
            aria-labelledby="faq-heading"
            className="scroll-mt-24 border-t border-marketing-line/80"
        >
            <div className="mx-auto w-full max-w-6xl px-6 py-20 sm:py-24">
                <RevealSection>
                    <div className="grid gap-12 lg:grid-cols-[minmax(0,0.8fr)_minmax(0,1.2fr)] lg:gap-20">
                        <div className="lg:pt-1">
                            <p className="font-mono text-[10px] font-medium uppercase tracking-[0.18em] text-marketing-muted">
                                FAQ
                            </p>
                            <h2
                                id="faq-heading"
                                className="mt-4 font-display text-3xl font-semibold leading-[1.08] tracking-tight text-marketing-ink sm:text-4xl"
                            >
                                Common questions
                            </h2>
                            <p className="mt-4 max-w-sm text-sm leading-relaxed text-marketing-muted">
                                Still deciding? Read the{" "}
                                <Link
                                    href="/docs"
                                    className="text-marketing-ink underline decoration-marketing-sky underline-offset-4 transition-colors hover:decoration-marketing-ink"
                                >
                                    docs
                                </Link>{" "}
                                or{" "}
                                <Link
                                    href="/contact"
                                    className="text-marketing-ink underline decoration-marketing-sky underline-offset-4 transition-colors hover:decoration-marketing-ink"
                                >
                                    talk to us
                                </Link>
                                . We answer in the open.
                            </p>
                        </div>

                        <div className="border-t border-marketing-line">
                            {faqItems.map((item, index) => (
                                <details
                                    key={item.question}
                                    open={index === 0}
                                    className="group border-b border-marketing-line [&[open]_svg]:rotate-45"
                                >
                                    <summary className="flex cursor-pointer list-none items-center justify-between gap-6 py-5 text-left font-display text-base font-semibold tracking-tight text-marketing-ink focus-visible:rounded-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-marketing-sky/60 focus-visible:ring-offset-2 focus-visible:ring-offset-marketing-paper sm:text-lg [&::-webkit-details-marker]:hidden">
                                        {item.question}
                                        <Plus
                                            aria-hidden="true"
                                            className="size-4 shrink-0 text-marketing-muted transition-transform duration-300 group-hover:text-marketing-ink"
                                        />
                                    </summary>
                                    <p className="max-w-2xl pb-5 pr-10 text-sm leading-relaxed text-marketing-muted">
                                        {item.answer}
                                    </p>
                                </details>
                            ))}
                        </div>
                    </div>
                </RevealSection>
            </div>
        </section>
    );
}

export { Faq };
