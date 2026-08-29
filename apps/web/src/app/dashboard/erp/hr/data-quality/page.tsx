import type { Metadata } from "next";

import { ModuleAccessBoundary } from "@/components/dashboard/shared/module-access-boundary";
import { DataQualityClient } from "./data-quality";

export const metadata: Metadata = {
  title: "Data quality · HR",
};

export default function DataQualityPage() {
  return (
    <ModuleAccessBoundary module="erp" permission="erp.hr.read">
      <DataQualityClient />
    </ModuleAccessBoundary>
  );
}