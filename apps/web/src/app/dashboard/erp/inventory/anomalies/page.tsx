import { AlertTriangle } from "lucide-react";

import { PageHeader } from "@/components/dashboard/shared/page-header";
import { AnomalyFeed } from "@/components/dashboard/erp/inventory/anomaly-feed";

export default function AnomaliesPage() {
    return (
        <div className="space-y-6">
            <PageHeader
                title="Anomaly Feed"
                description="Automated detection of unusual inventory patterns."
                icon={AlertTriangle}
            />
            <AnomalyFeed />
        </div>
    );
}
