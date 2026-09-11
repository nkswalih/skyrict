import { FileText } from "lucide-react";

import { PageHeader } from "@/components/dashboard/shared/page-header";
import { DocumentsOverview } from "@/components/dashboard/erp/documents/documents-overview";

export default function ErpDocumentsPage() {
    return (
        <div className="space-y-8">
            <PageHeader
                title="Documents"
                description="Central document store with AI-powered extraction and tagging."
                icon={FileText}
            />
            <DocumentsOverview />
        </div>
    );
}