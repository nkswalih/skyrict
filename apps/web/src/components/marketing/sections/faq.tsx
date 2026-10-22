import { Plus } from "lucide-react";
import Link from "next/link";

import { RevealSection } from "@/components/marketing/reveal-section";

const faqItems = [
    {
        question: "What is Skyrict?",
        answer: "Skyrict is an AI Business Operating System. It reads your live operations—inventory, sales, cash, and orders—alongside continuous market signals, then returns the next move with the evidence attached.",
    },
    {
        question: "How is this different from a dashboard?",
        answer: "A dashboard shows what happened. Skyrict reads what is happening now, connects it to the market, and explains what to do next. Every recommendation carries the reasoning, so you can inspect it before you act.",
    },
    {
        question: "Do I have to replace my ERP?",
        answer: "No. Skyrict connects to the systems you already run and starts with the operational slice that matters most. You add sources progressively; there is no rip-and-replace migration.",
    },
    {
        question: "What can I connect?",
        answer: "Inventory, orders, sales, cash, and payroll from your existing tools, plus signals from Google Trends, YouTube, Reddit, GitHub, and news. Start with one source and expand as your workspace grows.",
    },
    {
        question: "How is my data protected?",
        answer: "Every workspace is tenant-scoped, with role-based permissions, MFA, and email verification. The security model is documented in the open, and the source is public.",
    },
    {
        question: "How do I get started?",
        answer: "Starter is free forever. Paid plans begin with a 14-day trial, no credit card required. Create an account, connect your first source, and Skyrict will surface the first signal. For a guided rollout, book a demo.",
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
