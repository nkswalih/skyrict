import { Activity } from "lucide-react";

import { StockHealthOverview } from "@/components/dashboard/erp/inventory/stock-health";
import { PageHeader } from "@/components/dashboard/shared/page-header";

export default function HealthPage() {
    return (
        <div className="space-y-6">
            <PageHeader
                title="Stock Health"
                description="Dead stock, slow movers, and movement trends across warehouses."
                icon={Activity}
            />
            <StockHealthOverview />
        </div>
    );
}
