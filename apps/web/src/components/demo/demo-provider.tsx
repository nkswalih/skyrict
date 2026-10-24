"use client";

import { createContext, useContext, useEffect, useState, useCallback } from "react";
import { usePathname } from "next/navigation";
import { getDemoState, resetDemoState, setDemoState, type DemoState } from "@/lib/demo/demo-store";
import { installDemoNetworkGuard } from "@/lib/demo/demo-network-guard";

interface DemoContextType {
  isDemo: boolean;
  state: DemoState;
  updateState: (fn: (current: DemoState) => DemoState) => void;
  reset: () => void;
}

const DemoContext = createContext<DemoContextType | null>(null);

export function DemoProvider({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  // Automatically activate when on any /demo route, eliminating "Not in demo mode" gates
  const isDemoPath = pathname?.startsWith("/demo") ?? false;
  const [state, setStateInternal] = useState<DemoState>(getDemoState);

  useEffect(() => {
    installDemoNetworkGuard();
    const handleSync = () => setStateInternal(getDemoState());
    window.addEventListener("skyrict:demo-storage-changed", handleSync);
    return () => window.removeEventListener("skyrict:demo-storage-changed", handleSync);
  }, []);

  const updateState = useCallback((fn: (current: DemoState) => DemoState) => {
    const updated = fn(getDemoState());
    setDemoState(updated);
    setStateInternal(updated);
  }, []);

  const reset = useCallback(() => {
    const fresh = resetDemoState();
    setStateInternal(fresh);
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