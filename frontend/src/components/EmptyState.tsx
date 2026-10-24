import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";

/** Design.md §6 EmptyState: a 24 px icon, one factual line, optional guidance. No illustrations. */
export function EmptyState({ Icon, title, children }: { Icon: LucideIcon; title: string; children?: ReactNode }) {
  return (
    <div className="flex flex-col items-start gap-2 rounded-sm border border-dashed border-border p-6">
      <Icon aria-hidden="true" strokeWidth={1.5} className="size-6 text-subtle" />
      <p className="text-sm font-medium text-fg">{title}</p>
      {children && <div className="text-sm text-muted">{children}</div>}
    </div>
  );
}
