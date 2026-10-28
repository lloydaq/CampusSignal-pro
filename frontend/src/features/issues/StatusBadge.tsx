import { Circle, CircleCheck, CircleDot, CircleX, Wrench, type LucideIcon } from "lucide-react";

import { cn } from "@/lib/utils";

import type { IssueStatus } from "./api";
import { STATUS_LABEL } from "./labels";

const LOOK: Record<IssueStatus, { Icon: LucideIcon; tone: string }> = {
  SUBMITTED: { Icon: Circle, tone: "bg-surface-sunken text-muted" },
  ACKNOWLEDGED: { Icon: CircleDot, tone: "bg-primary-subtle text-primary" },
  IN_PROGRESS: { Icon: Wrench, tone: "bg-warning-subtle text-warning-fg" },
  RESOLVED: { Icon: CircleCheck, tone: "bg-success-subtle text-success-fg" },
  REJECTED: { Icon: CircleX, tone: "bg-danger-subtle text-danger-fg" },
};

/** Design.md §6 StatusBadge for issues: always icon + text, never colour alone. */
export function StatusBadge({ status, className }: { status: IssueStatus; className?: string }) {
  const { Icon, tone } = LOOK[status];
  return (
    <span className={cn("inline-flex items-center gap-1 rounded-sm px-1.5 py-0.5 text-xs font-semibold whitespace-nowrap", tone, className)}>
      <Icon aria-hidden="true" strokeWidth={2} className="size-3.5" />
      {STATUS_LABEL[status]}
    </span>
  );
}
