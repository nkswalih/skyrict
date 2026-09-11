import { FolderOpen } from "lucide-react";

import { PageHeader } from "@/components/dashboard/shared/page-header";
import { DocumentsList } from "@/components/dashboard/erp/documents/documents-list";

export default function ErpDocumentsListPage() {
    return (
        <div className="space-y-8">
            <PageHeader
                title="All documents"
                description="Browse, search, and manage the complete document library."
                icon={FolderOpen}
            />
            <DocumentsList />
        </div>
    );
}