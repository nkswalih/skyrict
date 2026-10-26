"use client";

import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { usePathname } from "next/navigation";
import {
  createDemoSeedState,
  ensureDemoStorage,
  getDemoState,
  resetDemoState,
  setDemoState,
  subscribeDemoState,
  type DemoState,
} from "@/lib/demo/demo-store";
import { installDemoNetworkGuard } from "@/lib/demo/demo-network-guard";

interface DemoContextType {
  isDemo: boolean;
  state: DemoState;
  updateState: (fn: (current: DemoState) => DemoState) => void;
  reset: () => void;
}

const DemoContext = createContext<DemoContextType | null>(null);

// Direct loads of a demo URL should be guarded before React hydrates. SPA
// navigation into /demo is covered by the effect below.
if (typeof window !== "undefined" && window.location.pathname.startsWith("/demo")) {
  installDemoNetworkGuard();
}

export function DemoProvider({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  // Automatically activate when on any /demo route, eliminating "Not in demo mode" gates.
  const isDemoPath = pathname?.startsWith("/demo") ?? false;

  // Server and first client render both use the deterministic seed, so the
  // markup matches. Stored edits are loaded after mount (DEMO-001).
  const [state, setStateInternal] = useState<DemoState>(() => createDemoSeedState());

  useEffect(() => {
    if (!isDemoPath) return;
    installDemoNetworkGuard();
    ensureDemoStorage();
    setStateInternal(getDemoState());
    return subscribeDemoState(() => setStateInternal(getDemoState()));
  }, [isDemoPath]);

  const updateState = useCallback((fn: (current: DemoState) => DemoState) => {
    const updated = fn(getDemoState());
    setStateInternal(setDemoState(updated));
  }, []);

  const reset = useCallback(() => {
    setStateInternal(resetDemoState());
  }, []);

  return (
    <DemoContext.Provider value={{ isDemo: isDemoPath, state, updateState, reset }}>
      {children}
    </DemoContext.Provider>
  );
}

export function useDemo() {
  const ctx = useContext(DemoContext);
  if (!ctx) throw new Error("useDemo must be rendered within DemoProvider");
  return ctx;
}
