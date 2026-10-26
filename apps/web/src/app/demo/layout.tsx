"use client";

import { DemoProvider } from "@/components/demo/demo-provider";

/**
 * Demo-only boundary: the store, seed data and network guard load with the
 * `/demo` route chunk instead of every route in the app.
 */
export default function DemoLayout({
    children,
}: {
    children: React.ReactNode;
}) {
    return <DemoProvider>{children}</DemoProvider>;
}
