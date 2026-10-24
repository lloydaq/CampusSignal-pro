import { Fragment, type ReactNode } from "react";

import { cn } from "@/lib/utils";

export interface Column<T> {
  header: string;
  cell: (row: T) => ReactNode;
  className?: string;
}

/**
 * Admin table (Design.md §6 Table): sticky header, tabular figures; below md, rows stack
 * as "label: value" pairs. `detail` renders a full-width row under a row (an expanded panel).
 */
export function DataTable<T>({
  caption,
  columns,
  rows,
  rowKey,
  detail,
}: {
  caption: string;
  columns: Column<T>[];
  rows: T[];
  rowKey: (row: T) => string;
  detail?: (row: T) => ReactNode;
}) {
  return (
    <div className="rounded-sm border border-border md:overflow-x-auto">
      <table className="w-full text-left text-sm tabular-nums">
        <caption className="sr-only">{caption}</caption>
        <thead className="hidden bg-surface-sunken md:table-header-group">
          <tr>
            {columns.map((column) => (
              <th key={column.header} scope="col" className="sticky top-0 bg-surface-sunken px-4 py-2 font-medium text-muted">
                {column.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => {
            const extra = detail?.(row);
            return (
              <Fragment key={rowKey(row)}>
                <tr className="block border-t border-border px-4 py-3 first:border-t-0 md:table-row md:p-0 md:first:border-t">
                  {columns.map((column) => (
                    <td
                      key={column.header}
                      data-label={column.header}
                      className={cn(
                        "flex gap-3 py-0.5 align-top before:w-28 before:shrink-0 before:text-muted before:content-[attr(data-label)] md:table-cell md:px-4 md:py-3 md:before:content-none",
                        column.className,
                      )}
                    >
                      <div className="min-w-0">{column.cell(row)}</div>
                    </td>
                  ))}
                </tr>
                {extra && (
                  <tr className="block md:table-row">
                    <td colSpan={columns.length} className="block border-t border-border bg-surface-sunken/50 px-4 py-4 md:table-cell">
                      {extra}
                    </td>
                  </tr>
                )}
              </Fragment>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
