"use client";

import { useMemo, useState } from "react";
import {
  FileText,
  Package,
  Receipt,
  Users,
  Wallet,
  type LucideIcon,
} from "lucide-react";
import { PageHeader } from "@/components/dashboard/shared/page-header";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import {
  getDemoModuleSpec,
  type DemoCell,
  type DemoRow,
} from "@/lib/demo/demo-modules";
import type { DemoState } from "@/lib/demo/demo-store";

function iconFor(routePath: string): LucideIcon {
  if (routePath.startsWith("crm/")) return Users;
  if (routePath.startsWith("inventory/")) return Package;
  if (routePath.startsWith("hr/")) return Users;
  if (routePath.startsWith("finance/")) return Wallet;
  if (routePath.startsWith("payroll/")) return Receipt;
  return FileText;
}

function cellText(cell: DemoCell | undefined): string {
  return typeof cell === "string" ? cell : (cell?.text ?? "");
}

function cellMatches(row: DemoRow, query: string): boolean {
  return Object.values(row.cells).some((cell) =>
    cellText(cell).toLowerCase().includes(query),
  );
}

/**
 * Shared read-only record grid for the demo modules that previously rendered
 * the "Module Records" placeholder. Column/row definitions live in
 * `lib/demo/demo-modules.ts`; this component only handles presentation,
 * filtering and the empty state.
 */
export function DemoModuleRecords({
  routePath,
  state,
}: {
  routePath: string;
  state: DemoState;
}) {
  const spec = useMemo(
    () => getDemoModuleSpec(routePath, state),
    [routePath, state],
  );
  const [query, setQuery] = useState("");

  if (!spec) return null;

  const normalized = query.trim().toLowerCase();
  const rows = normalized
    ? spec.rows.filter((record) => cellMatches(record, normalized))
    : spec.rows;

  return (
    <div className="space-y-6">
      <PageHeader
        title={spec.title}
        description={spec.description}
        icon={iconFor(routePath)}
      />

      {spec.searchPlaceholder ? (
        <div className="flex flex-wrap items-center gap-3">
          <Input
            type="search"
            aria-label={spec.searchPlaceholder}
            placeholder={spec.searchPlaceholder}
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            className="max-w-sm"
          />
          <p role="status" className="text-xs text-muted-foreground">
            {rows.length} of {spec.rows.length} records
          </p>
        </div>
      ) : null}

      <div className="overflow-hidden rounded-xl border border-border bg-card">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="border-b bg-muted/40 text-xs font-semibold text-muted-foreground uppercase">
              <tr>
                {spec.columns.map((column) => (
                  <th
                    key={column.key}
                    scope="col"
                    className={
                      column.align === "right"
                        ? "px-4 py-3 text-right"
                        : "px-4 py-3"
                    }
                  >
                    {column.label}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-border/60">
              {rows.map((record) => (
                <tr key={record.id} className="hover:bg-muted/20">
                  {spec.columns.map((column) => {
                    const cell = record.cells[column.key];
                    const align =
                      column.align === "right" ? "text-right" : undefined;
                    return (
                      <td
                        key={column.key}
                        className={`px-4 py-3 ${align ?? ""}`.trim()}
                      >
                        {typeof cell === "string" || cell === undefined ? (
                          cell
                        ) : (
                          <Badge variant={cell.variant ?? "outline"}>
                            {cell.text}
                          </Badge>
                        )}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {rows.length === 0 ? (
          <p
            role="status"
            className="border-t border-border/60 px-4 py-8 text-center text-sm text-muted-foreground"
          >
            {normalized
              ? "No records match this filter."
              : spec.emptyMessage}
          </p>
        ) : null}
      </div>

      {spec.footnote ? (
        <p className="text-xs text-muted-foreground">{spec.footnote}</p>
      ) : null}
    </div>
  );
}
