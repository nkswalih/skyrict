"use client";

import { useEffect, useRef } from "react";

import { cn } from "@/lib/utils";

type RevealSectionProps = {
    children: React.ReactNode;
    className?: string;
    delay?: number;
    /**
     * Media reveals use a shorter travel and a lighter blur so large screenshots
     * stay sharp while they settle.
     */
    variant?: "text" | "media";
};

type RevealCallback = () => void;

const callbacks = new WeakMap<Element, RevealCallback>();
let sharedObserver: IntersectionObserver | null = null;

function getSharedObserver(): IntersectionObserver | null {
    if (typeof window === "undefined") return null;
    if (!("IntersectionObserver" in window)) return null;
    if (sharedObserver) return sharedObserver;

    sharedObserver = new IntersectionObserver(
        (entries) => {
            for (const entry of entries) {
                if (!entry.isIntersecting) continue;
                const callback = callbacks.get(entry.target);
                if (!callback) continue;
                callbacks.delete(entry.target);
                sharedObserver?.unobserve(entry.target);
                callback();
            }
        },
        {
            // Trigger as soon as the element's leading edge is inside the
            // viewport. The old 0.15 threshold never fired for sections taller
            // than the viewport, which left them permanently hidden.
            threshold: 0,
            rootMargin: "0px 0px -8% 0px",
        },
    );

    return sharedObserver;
}

function RevealSection({
    children,
    className,
    delay = 0,
    variant = "text",
}: RevealSectionProps) {
    const ref = useRef<HTMLDivElement>(null);

    useEffect(() => {
        const element = ref.current;
        if (!element) return;
        if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
            return;
        }

        const rect = element.getBoundingClientRect();
        // Content that is already on screen should never wait for an observer.
        // Only arm the blur-fade for content that is still below the fold, so a
        // failed hydration or a disabled observer can never hide the page.
        if (rect.top < window.innerHeight * 0.96) {
            return;
        }

        element.classList.add("reveal-armed");

        const observer = getSharedObserver();
        if (!observer) {
            element.classList.remove("reveal-armed");
            return;
        }

        const reveal = () => {
            element.classList.remove("reveal-armed");
        };

        callbacks.set(element, reveal);
        observer.observe(element);

        return () => {
            callbacks.delete(element);
            observer.unobserve(element);
            element.classList.remove("reveal-armed");
        };
    }, []);

    return (
        <div
            ref={ref}
            style={
                delay
                    ? ({ "--reveal-delay": `${delay}ms` } as React.CSSProperties)
                    : undefined
            }
            className={cn(
                "reveal",
                variant === "media" ? "reveal-media" : "reveal-text",
                className,
            )}
        >
            {children}
        </div>
    );
}

export { RevealSection };
