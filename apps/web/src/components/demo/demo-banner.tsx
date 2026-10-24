"use client";

import Link from "next/link";
import { ArrowRight, RotateCcw, ShieldAlert } from "lucide-react";
import { useDemo } from "./demo-provider";
import { Button } from "@/components/ui/button";

export function DemoBanner() {
  const { isDemo, reset } = useDemo();
  if (!isDemo) return null;

  return (
    <aside
      aria-label="Demo environment notice"
      className="sticky top-0 z-50 flex items-center justify-between border-b border-sky-300 bg-[#0a2f3e] px-4 py-2 text-white shadow-sm"
    >
      <div className="flex items-center gap-2.5 text-xs">
        <span className="flex items-center gap-1 rounded bg-amber-500/20 px-2 py-0.5 font-bold uppercase tracking-wider text-amber-300">
          <ShieldAlert className="size-3.5" /> Interactive Demo
        </span>
        <span className="hidden text-slate-300 md:inline">
          Running with localized sample records. Edits stay in your browser and do not affect the live servers.
        </span>
      </div>

      <div className="flex items-center gap-3">
        <button
          type="button"
          onClick={reset}
          className="flex items-center gap-1 text-xs text-slate-300 underline-offset-4 hover:text-white hover:underline"
        >
          <RotateCcw className="size-3" /> Reset sample data
        </button>
        <Button asChild size="sm" variant="brand" className="h-7 text-xs font-semibold">
          <Link href="/signup">
            Create real workspace <ArrowRight className="ml-1 size-3" />
          </Link>
        </Button>
      </div>
    </aside>
  );
}