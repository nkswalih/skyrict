"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { AppSidebar } from "@/components/dashboard/workspace/app-sidebar";
import { Topbar } from "@/components/dashboard/workspace/topbar";
import { erpNavGroups, type NavGroup, type NavItem } from "@/components/dashboard/workspace/sidebar-config";
import { DemoBanner } from "@/components/demo/demo-banner";

const COLLAPSED_KEY = "skyrict:sidebar:collapsed";

function rewriteHref(href: string): string {
  if (href === "/erp") return "/demo/erp";
  if (href.startsWith("/erp/")) return "/demo" + href;
  return href;
}

function rewriteNavItem(item: NavItem): NavItem {
  return {
    ...item,
    href: rewriteHref(item.href),
    children: item.children?.map(rewriteNavItem),
  };
}

export function DemoErpShell({ children }: { children: React.ReactNode }) {
  const [collapsed, setCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);

  useEffect(() => {
    setCollapsed(localStorage.getItem(COLLAPSED_KEY) === "true");
  }, []);

  const toggleCollapsed = useCallback(() => {
    setCollapsed((v) => {
      localStorage.setItem(COLLAPSED_KEY, String(!v));
      return !v;
    });
  }, []);

  // Map 100% of real ERP navigation with demo links
  const demoNavGroups: NavGroup[] = useMemo(
    () =>
      erpNavGroups.map((group) => ({
        ...group,
        items: group.items.map(rewriteNavItem),
      })),
    []
  );

  return (
    <div className="theme-demo flex h-dvh overflow-hidden bg-background" data-theme-scope>
      <AppSidebar
        collapsed={collapsed}
        mobileOpen={mobileOpen}
        onToggleCollapsed={toggleCollapsed}
        onCloseMobile={() => setMobileOpen(false)}
        navGroups={demoNavGroups}
        accountItems={[]}
        brandHref="/demo/erp"
        logoTone="sky"
      />

      <div className="flex min-w-0 flex-1 flex-col">
        <DemoBanner />
        <Topbar onOpenMenu={() => setMobileOpen(true)} />
        <main className="flex-1 overflow-y-auto">
          <div className="mx-auto w-full max-w-6xl px-4 py-6 lg:px-6 lg:py-8">
            {children}
          </div>
        </main>
      </div>
    </div>
  );
}