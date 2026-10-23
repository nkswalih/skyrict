"use client";

import {
    ArrowUp,
    Pencil,
    Plus,
    RotateCcw,
    Sparkles,
} from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

import { AiGlyph } from "@/components/brand/logo";
import { cn } from "@/lib/utils";

const PROMPT =
    "Draft a concise follow-up email to Zephyr Airlines about the loyalty rebuild opportunity. Mention the $310,000 proposal and ask for a decision by 16 November.";

const ANSWER = `Subject: Zephyr Airlines — loyalty rebuild proposal

Hi Zephyr team,

Following up on the loyalty rebuild opportunity. Our proposal is for $310,000 and covers the full rebuild scope.

We would like to confirm a decision by 16 November so we can hold the delivery window. Happy to walk through the plan or adjust the scope before then.

Best,
Aarav Deshmukh
Vastraline Industries`;

const ANSWER_TOKENS = ANSWER.match(/\S+\s*/g) ?? [];

const SOURCES = [
    {
        label: "Opportunity",
        value: "Zephyr Airlines — loyalty rebuild",
    },
    {
        label: "Value",
        value: "$310,000",
    },
    {
        label: "Stage",
        value: "Negotiation · 70%",
    },
    {
        label: "CRM close date",
        value: "17 Nov 2026",
    },
];

type Phase = "typing" | "sending" | "thinking" | "streaming" | "sources" | "done";

function SkyAgentReplay() {
    const sectionRef = useRef<HTMLDivElement>(null);
    const messageRef = useRef<HTMLDivElement>(null);
    const [inView, setInView] = useState(false);
    const [reducedMotion, setReducedMotion] = useState(false);
    const [phase, setPhase] = useState<Phase>("typing");
    const [typedPrompt, setTypedPrompt] = useState("");
    const [visibleWords, setVisibleWords] = useState(0);

    const showPrompt = phase !== "typing";
    const answer = useMemo(
        () => ANSWER_TOKENS.slice(0, visibleWords).join(""),
        [visibleWords],
    );
    const isStreaming = phase === "streaming";
    const isThinking = phase === "thinking";
    const showSources = phase === "sources" || phase === "done";

    useEffect(() => {
        const element = sectionRef.current;
        if (!element) return;

        const motionQuery = window.matchMedia(
            "(prefers-reduced-motion: reduce)",
        );
        if (motionQuery.matches) {
            setReducedMotion(true);
            setInView(true);
            setPhase("done");
            setTypedPrompt(PROMPT);
            setVisibleWords(ANSWER_TOKENS.length);
            return;
        }

        if (!("IntersectionObserver" in window)) {
            setInView(true);
            return;
        }

        const observer = new IntersectionObserver(
            ([entry]) => {
                setInView(entry.isIntersecting);
            },
            { threshold: 0, rootMargin: "0px 0px -10% 0px" },
        );
        observer.observe(element);

        return () => observer.disconnect();
    }, []);

    useEffect(() => {
        if (!inView || reducedMotion) return;

        let timer: number | undefined;

        if (phase === "typing") {
            if (typedPrompt.length >= PROMPT.length) {
                timer = window.setTimeout(() => setPhase("sending"), 420);
            } else {
                timer = window.setTimeout(() => {
                    setTypedPrompt(
                        PROMPT.slice(0, Math.min(typedPrompt.length + 2, PROMPT.length)),
                    );
                }, 20);
            }
        } else if (phase === "sending") {
            timer = window.setTimeout(() => setPhase("thinking"), 520);
        } else if (phase === "thinking") {
            timer = window.setTimeout(() => setPhase("streaming"), 1500);
        } else if (phase === "streaming") {
            if (visibleWords >= ANSWER_TOKENS.length) {
                timer = window.setTimeout(() => setPhase("sources"), 360);
            } else {
                timer = window.setTimeout(() => {
                    setVisibleWords((count) =>
                        Math.min(count + 2, ANSWER_TOKENS.length),
                    );
                }, 42);
            }
        } else if (phase === "sources") {
            timer = window.setTimeout(() => setPhase("done"), 900);
        } else if (phase === "done") {
            timer = window.setTimeout(() => {
                setTypedPrompt("");
                setVisibleWords(0);
                setPhase("typing");
            }, 5600);
        }

        return () => {
            if (timer) window.clearTimeout(timer);
        };
    }, [inView, reducedMotion, phase, typedPrompt, visibleWords]);

    useEffect(() => {
        const node = messageRef.current;
        if (!node) return;
        node.scrollTop = node.scrollHeight;
    }, [visibleWords, phase]);

    const replay = () => {
        setTypedPrompt("");
        setVisibleWords(0);
        setPhase("typing");
    };

    return (
        <div
            ref={sectionRef}
            className="relative overflow-hidden rounded-[1.5rem] border border-[#dcd9ff] bg-[#f7f6ff] shadow-[0_40px_120px_-70px_rgba(42,36,120,0.7)]"
        >
            <div className="flex min-h-[560px] flex-col sm:min-h-[610px] sm:flex-row">
                {/* SkyAgent rail, reduced to the parts this view uses. */}
                <aside className="hidden w-[220px] shrink-0 flex-col border-r border-[#e4e1ff] bg-[#f0eeff] px-4 py-5 sm:flex">
                    <div className="flex items-center gap-2 px-1">
                        <span className="flex size-8 items-center justify-center rounded-[0.65rem] bg-[#8b87f4] text-white shadow-[inset_0_1px_0_rgba(255,255,255,0.4)]">
                            <AiGlyph aria-hidden="true" className="size-4" />
                        </span>
                        <span className="font-display text-sm font-semibold tracking-tight text-[#24204a]">
                            SkyAgent
                        </span>
                    </div>

                    <button
                        type="button"
                        onClick={replay}
                        className="mt-7 flex items-center gap-2 rounded-lg px-2 py-2 text-left text-sm font-medium text-[#514ccf] transition-colors hover:bg-white/70 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#8b87f4]"
                    >
                        <Pencil aria-hidden="true" className="size-4" />
                        New chat
                    </button>

                    <div className="mt-7 space-y-1">
                        <div className="flex items-center gap-2 rounded-lg bg-white/70 px-2 py-1.5 text-xs font-medium text-[#4a4675]">
                            <Sparkles
                                aria-hidden="true"
                                className="size-3.5 text-[#5b57e8]"
                            />
                            <span className="flex-1">CRM Assistant</span>
                            <span
                                aria-hidden="true"
                                className="size-1.5 rounded-full bg-emerald-500"
                            />
                        </div>
                    </div>

                    <p className="mt-7 px-2 font-mono text-[9px] font-medium uppercase tracking-[0.18em] text-[#8d89b8]">
                        Recents
                    </p>
                    <div className="mt-2 rounded-lg bg-white/70 px-2.5 py-2">
                        <p className="truncate text-xs font-medium text-[#3b376e]">
                            Draft a concise follow-up…
                        </p>
                        <p className="mt-0.5 text-[10px] text-[#8d89b8]">
                            Zephyr Airlines
                        </p>
                    </div>

                    <div className="mt-auto flex items-center gap-2 border-t border-[#e4e1ff] pt-4">
                        <span className="flex size-7 items-center justify-center rounded-full bg-[#23203d] font-mono text-[9px] font-semibold text-white">
                            AD
                        </span>
                        <div className="min-w-0">
                            <p className="truncate text-xs font-medium text-[#3b376e]">
                                Aarav Deshmukh
                            </p>
                            <p className="truncate text-[10px] text-[#8d89b8]">
                                Vastraline Industries
                            </p>
                        </div>
                    </div>
                </aside>

                <div className="flex min-w-0 flex-1 flex-col">
                    <div className="flex items-center justify-between gap-3 border-b border-[#eceaff] bg-white/80 px-4 py-3 sm:px-5">
                        <div className="flex min-w-0 items-center gap-2.5">
                            <span className="flex size-7 shrink-0 items-center justify-center rounded-lg bg-[#8b87f4]/12 text-[#5b57e8] sm:hidden">
                                <AiGlyph aria-hidden="true" className="size-4" />
                            </span>
                            <p className="truncate text-xs font-medium text-[#2f2b57] sm:text-sm">
                                Draft a concise follow-up email to Zephyr Airlines
                                about the loyalty rebuild opportunity…
                            </p>
                        </div>
                        <button
                            type="button"
                            onClick={replay}
                            className="group flex shrink-0 items-center gap-1.5 rounded-full border border-[#dcd9ff] bg-white px-2.5 py-1.5 font-mono text-[9px] font-medium uppercase tracking-[0.12em] text-[#5b57e8] transition-colors hover:border-[#8b87f4] hover:bg-[#f4f2ff] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#8b87f4]"
                        >
                            <RotateCcw
                                aria-hidden="true"
                                className="size-3 transition-transform duration-300 group-hover:-rotate-45"
                            />
                            Run again
                        </button>
                    </div>

                    <div
                        ref={messageRef}
                        className="min-h-0 flex-1 overflow-y-auto px-4 py-5 sm:px-7 sm:py-6"
                    >
                        <div className="mx-auto flex max-w-[620px] flex-col items-center gap-2">
                            <span className="font-mono text-[9px] uppercase tracking-[0.14em] text-[#8d89b8]">
                                Today
                            </span>
                            <span className="font-mono text-[9px] text-[#8d89b8]">
                                6:20 PM
                            </span>
                        </div>

                        <div className="mx-auto mt-3 flex max-w-[620px] flex-col gap-5">
                            {showPrompt ? (
                                <div className="flex justify-end">
                                    <div className="sky-pop-in max-w-[86%] rounded-[1.15rem] rounded-tr-md bg-[#5b57e8] px-4 py-3 text-sm leading-relaxed text-white shadow-[0_12px_28px_-20px_rgba(72,66,168,0.8)]">
                                        {PROMPT}
                                    </div>
                                </div>
                            ) : null}

                            {phase !== "typing" && phase !== "sending" ? (
                                <div className="flex gap-2.5">
                                    <span className="mt-0.5 flex size-6 shrink-0 items-center justify-center rounded-full bg-[#8b87f4]/12 text-[#5b57e8]">
                                        <Sparkles
                                            aria-hidden="true"
                                            className="size-3.5"
                                        />
                                    </span>
                                    <div className="min-w-0 flex-1">
                                        <p className="font-mono text-[9px] font-semibold uppercase tracking-[0.16em] text-[#5b57e8]">
                                            CRM Assistant
                                        </p>

                                        {isThinking ? (
                                            <div className="mt-3 flex items-center gap-2 text-sm text-[#8d89b8]">
                                                <span>Thinking</span>
                                                <span className="flex items-center gap-1">
                                                    {[0, 1, 2].map((dot) => (
                                                        <span
                                                            key={dot}
                                                            className="agent-thinking-dot size-1.5 rounded-full bg-[#8b87f4]"
                                                            style={{
                                                                animationDelay: `${dot * 140}ms`,
                                                            }}
                                                        />
                                                    ))}
                                                </span>
                                            </div>
                                        ) : null}

                                        {!isThinking ? (
                                            <div className="mt-2 whitespace-pre-wrap text-sm leading-relaxed text-[#2f2b57]">
                                                {answer}
                                                {isStreaming ? (
                                                    <span
                                                        aria-hidden="true"
                                                        className="agent-caret ml-0.5 inline-block h-4 w-[2px] translate-y-0.5 bg-[#5b57e8]"
                                                    />
                                                ) : null}
                                            </div>
                                        ) : null}

                                        {showSources ? (
                                            <div className="mt-4 rounded-xl border border-[#e4e1ff] bg-white/70 p-3">
                                                <p className="font-mono text-[9px] font-medium uppercase tracking-[0.16em] text-[#8d89b8]">
                                                    Records used
                                                </p>
                                                <div className="mt-2 grid gap-2 sm:grid-cols-2">
                                                    {SOURCES.map((source, index) => (
                                                        <div
                                                            key={source.label}
                                                            className="sky-pop-in rounded-lg border border-[#eceaff] bg-[#fbfaff] px-2.5 py-2"
                                                            style={{
                                                                animationDelay: `${index * 90}ms`,
                                                            }}
                                                        >
                                                            <p className="font-mono text-[8px] uppercase tracking-[0.14em] text-[#8d89b8]">
                                                                {source.label}
                                                            </p>
                                                            <p className="mt-0.5 text-[11px] font-medium leading-snug text-[#3b376e]">
                                                                {source.value}
                                                            </p>
                                                        </div>
                                                    ))}
                                                </div>
                                                <p className="mt-2.5 text-[10px] leading-relaxed text-[#8d89b8]">
                                                    A draft only. SkyAgent stops
                                                    before anything is sent.
                                                </p>
                                            </div>
                                        ) : null}
                                    </div>
                                </div>
                            ) : null}
                        </div>
                    </div>

                    <div className="border-t border-[#eceaff] bg-white/70 px-4 py-3 sm:px-5 sm:py-4">
                        <div className="mx-auto flex max-w-[620px] items-center gap-2 rounded-full border border-[#dcd9ff] bg-white px-3 py-2 shadow-[inset_0_1px_0_rgba(255,255,255,0.9)]">
                            <Plus
                                aria-hidden="true"
                                className="size-4 shrink-0 text-[#8d89b8]"
                            />
                            <div className="min-w-0 flex-1 truncate text-xs text-[#8d89b8] sm:text-sm">
                                {phase === "typing" ? (
                                    <span className="text-[#3b376e]">
                                        {typedPrompt}
                                        <span
                                            aria-hidden="true"
                                            className="agent-caret ml-0.5 inline-block h-3.5 w-[2px] translate-y-0.5 bg-[#5b57e8]"
                                        />
                                    </span>
                                ) : (
                                    "Continue the conversation…"
                                )}
                            </div>
                            <span
                                aria-hidden="true"
                                className={cn(
                                    "flex size-7 shrink-0 items-center justify-center rounded-full transition-colors",
                                    phase === "typing"
                                        ? "bg-[#5b57e8] text-white"
                                        : "bg-[#efeeff] text-[#a7a4f6]",
                                )}
                            >
                                <ArrowUp className="size-3.5" />
                            </span>
                        </div>
                        <p className="mx-auto mt-2 max-w-[620px] text-center text-[9px] leading-relaxed text-[#a5a1c8]">
                            SkyAgent is AI and can make mistakes. Please
                            double-check responses.
                        </p>
                    </div>
                </div>
            </div>

            {/* The animation is decorative; this is the transcript a screen
                reader receives. */}
            <div className="sr-only">
                <p>Prompt: {PROMPT}</p>
                <p>CRM Assistant answer: {ANSWER}</p>
                <p>
                    Records used: Zephyr Airlines loyalty rebuild, $310,000,
                    negotiation at 70%, CRM close date 17 November 2026.
                </p>
            </div>
        </div>
    );
}

export { SkyAgentReplay };
