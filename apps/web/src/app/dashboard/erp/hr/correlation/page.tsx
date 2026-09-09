import type { Metadata } from "next";

import { ModuleAccessBoundary } from "@/components/dashboard/shared/module-access-boundary";
import { CorrelationClient } from "./correlation";

export const metadata: Metadata = {
    title: "Leave · pay correlation · HR",
};

export default function CorrelationPage() {
    return (
        <ModuleAccessBoundary module="erp" permission="erp.hr.ai.read">
            <CorrelationClient />
        </ModuleAccessBoundary>
    );
}