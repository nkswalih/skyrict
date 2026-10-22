import type { CSSProperties } from "react";

import { cn } from "@/lib/utils";

const askAiPrompt = `As a potential client, I want to concretely understand what I will receive with Skyrict (skyrict.in).

Detail step by step what the service includes: what Skyrict is, how AI business agents work, how they connect live operations, inventory, sales, cash, and orders with continuous market signals, the security and compliance features, and how it helps teams turn signals into decisions and scale.

Explain it simply, as if you were describing the real experience of the service.`;

const encodedPrompt = encodeURIComponent(askAiPrompt);

const providers = [
    {
        name: "ChatGPT",
        icon: "chatgpt.svg",
        href: `https://chatgpt.com/?q=${encodedPrompt}`,
    },
    {
        name: "Claude",
        icon: "claude.svg",
        href: `https://claude.ai/new?q=${encodedPrompt}`,
    },
    {
        name: "Google AI Mode",
        icon: "gemini.svg",
        href: `https://www.google.com/search?udm=50&source=searchlabs&q=${encodedPrompt}`,
    },
    {
        name: "Grok",
        icon: "grok.svg",
        href: `https://grok.com/?q=${encodedPrompt}`,
    },
    {
        name: "Perplexity",
        icon: "perplexity.svg",
        href: `https://www.perplexity.ai/search/new?q=${encodedPrompt}`,
    },
];

function ProviderIcon({ icon }: { icon: string }) {
    const style: CSSProperties = {
        maskImage: `url(/ai-providers/${icon})`,
        maskRepeat: "no-repeat",
        maskPosition: "center",
        maskSize: "contain",
        WebkitMaskImage: `url(/ai-providers/${icon})`,
        WebkitMaskRepeat: "no-repeat",
        WebkitMaskPosition: "center",
        WebkitMaskSize: "contain",
    };

    return (
        <span aria-hidden="true" className="size-5 bg-current" style={style} />
    );
}

function AskAiAboutSkyrict({ className }: { className?: string }) {
    return (
        <div
            className={cn("flex flex-col items-center text-center", className)}
        >
            <p className="font-mono text-[10px] font-medium uppercase tracking-[0.18em] text-marketing-muted">
                Ask AI about Skyrict
            </p>
            <ul className="mt-1.5 flex items-center justify-center gap-1.5">
                {providers.map((provider) => (
                    <li key={provider.name}>
                        <a
                            href={provider.href}
                            target="_blank"
                            rel="noopener noreferrer"
                            aria-label={`Ask ${provider.name} about Skyrict (opens in a new tab)`}
                            title={`Ask ${provider.name} about Skyrict`}
                            className="inline-flex size-9 items-center justify-center rounded-sm text-marketing-muted/80 transition-colors hover:text-marketing-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-marketing-sky/60"
                        >
                            <ProviderIcon icon={provider.icon} />
                        </a>
                    </li>
                ))}
            </ul>
        </div>
    );
}

export { AskAiAboutSkyrict };
