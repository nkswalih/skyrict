import { FileText } from "lucide-react";

import { PageHeader } from "@/components/dashboard/shared/page-header";
import { DocumentDetail } from "@/components/dashboard/erp/documents/document-detail";

export default async function ErpDocumentDetailPage({
    params,
}: {
    params: Promise<{ id: string }>;
}) {
    const { id } = await params;
    return (
        <div className="space-y-8">
            <PageHeader
                title="Document"
                description="View document details, versions, and AI-extracted content."
                icon={FileText}
            />
            <DocumentDetail id={id} />
        </div>
    );
}