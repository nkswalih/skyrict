import { BarChart3 } from "lucide-react";

import { PageHeader } from "@/components/dashboard/shared/page-header";
import { AbcTable } from "@/components/dashboard/erp/inventory/abc-table";

export default function AbcPage() {
    return (
        <div className="space-y-6">
            <PageHeader
                title="ABC Classification"
                description="Pareto analysis by revenue contribution — A (top 80%), B (next 15%), C (remaining 5%)."
                icon={BarChart3}
            />
            <AbcTable />
        </div>
    );
}
