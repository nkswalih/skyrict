import type { Metadata } from "next";
import { DemoErpShell } from "@/components/demo/demo-erp-shell";

export const metadata: Metadata = {
  title: "Skyrict ERP Demo Interactive Operations Workspace",
  robots: {
    index: false,
    follow: false,
  },
};

export default function DemoLayout({ children }: { children: React.ReactNode }) {
  return <DemoErpShell>{children}</DemoErpShell>;
}