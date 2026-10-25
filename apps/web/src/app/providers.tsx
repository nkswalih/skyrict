"use client";

import { ThemeProvider } from "next-themes";

import { SessionProvider } from "@/lib/auth/session";
import { TooltipProvider } from "@/components/ui/tooltip";

export function Providers({ children }: { children: React.ReactNode }) {
    return (
        <ThemeProvider attribute="class" defaultTheme="light" enableSystem>
            <SessionProvider>
                <TooltipProvider delayDuration={300}>
                    {children}
                </TooltipProvider>
            </SessionProvider>
        </ThemeProvider>
    );
}
