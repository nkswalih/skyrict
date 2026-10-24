"use client";

import Link from "next/link";
import { ArrowUpRight, CheckCircle2, Lock, Sparkles } from "lucide-react";
import { Button } from "@/components/ui/button";

interface DemoAiGateProps {
  title: string;
  description: string;
  features: string[];
}

export function DemoAiGate({ title, description, features }: DemoAiGateProps) {
  return (
    <div className="relative overflow-hidden rounded-2xl border border-sky-200 bg-gradient-to-br from-white via-sky-50/40 to-white p-6 shadow-sm">
      <div className="flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-primary">
        <Sparkles className="size-4 text-primary" /> Autonomous AI & Orchestration
      </div>
      <h3 className="mt-2 font-display text-xl font-bold tracking-tight text-foreground">{title}</h3>
      <p className="mt-1 max-w-2xl text-sm leading-relaxed text-muted-foreground">{description}</p>

      <div className="mt-5 grid gap-2.5 sm:grid-cols-2">
        {features.map((feat) => (
          <div key={feat} className="flex items-center gap-2 text-xs font-medium text-foreground">
            <CheckCircle2 className="size-4 shrink-0 text-emerald-500" />
            <span>{feat}</span>
          </div>
        ))}
      </div>

      <div className="mt-6 flex flex-wrap items-center gap-3 border-t border-sky-100 pt-4">
        <Button asChild variant="brand" size="sm">
          <Link href="/signup">
            Enable on your live workspace <ArrowUpRight className="ml-1 size-3.5" />
          </Link>
        </Button>
        <span className="flex items-center gap-1 text-xs text-muted-foreground">
          <Lock className="size-3.5" /> Available exclusively with live accounts
        </span>
      </div>
    </div>
  );
}