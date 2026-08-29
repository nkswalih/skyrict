import { Calendar } from "lucide-react";

import { PageHeader } from "@/components/dashboard/shared/page-header";
import { ForecastChart } from "@/components/dashboard/erp/inventory/forecast-chart";

export default function ForecastPage() {
    return (
        <div className="space-y-6">
            <PageHeader
                title="Demand Forecast"
                description="Predictive demand analysis and stockout risk projections."
                icon={Calendar}
            />
            <ForecastChart />
        </div>
    );
}
