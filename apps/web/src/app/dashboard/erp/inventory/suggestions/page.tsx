import { ShoppingCart } from "lucide-react";

import { PageHeader } from "@/components/dashboard/shared/page-header";
import { RestockSuggestions } from "@/components/dashboard/erp/inventory/restock-suggestions";

export default function SuggestionsPage() {
    return (
        <div className="space-y-6">
            <PageHeader
                title="AI Suggestions"
                description="Smart restock recommendations powered by inventory AI."
                icon={ShoppingCart}
            />
            <RestockSuggestions />
        </div>
    );
}
