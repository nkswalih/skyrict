"use client";

import { ThemeProvider } from "next-themes";

import { SessionProvider } from "@/lib/auth/session";
import { TooltipProvider } from "@/components/ui/tooltip";
import { DemoProvider } from "@/components/demo/demo-provider";

export function Providers({ children }: { children: React.ReactNode }) {
    return (
        <ThemeProvider attribute="class" defaultTheme="light" enableSystem>
            <SessionProvider>
                <DemoProvider>
                    <TooltipProvider delayDuration={300}>
                        {children}
                    </TooltipProvider>
                </DemoProvider>
            </SessionProvider>
        </ThemeProvider>
    );
}
