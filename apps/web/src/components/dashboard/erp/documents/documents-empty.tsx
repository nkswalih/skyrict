import type { LucideIcon } from "lucide-react";

/**
 * Shared empty state for documents tables with no rows yet. Mirrors the
 * existing ERP empty-state styling so no page-local one-offs are needed.
 */
export function DocumentsEmpty({
    title,
    description,
    icon: Icon,
    action,
}: {
    title: string;
    description: string;
    icon: LucideIcon;
    action?: React.ReactNode;
}) {
    return (
        <div className="flex flex-col items-center justify-center rounded-xl border border-dashed border-border bg-card px-6 py-14 text-center">
            <div className="flex size-11 items-center justify-center rounded-xl bg-muted text-muted-foreground">
                <Icon aria-hidden="true" className="size-5" />
            </div>
            <h3 className="mt-4 font-display text-base font-semibold tracking-tight text-foreground">
                {title}
            </h3>
            <p className="mt-1.5 max-w-sm text-sm leading-relaxed text-muted-foreground">
                {description}
            </p>
            {action ? <div className="mt-5">{action}</div> : null}
        </div>
    );
}