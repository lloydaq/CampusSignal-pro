import { CircleAlert, CircleCheck, Info, TriangleAlert, type LucideIcon } from "lucide-react";
import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

type Tone = "info" | "success" | "warning" | "danger";

const TONES: Record<Tone, { Icon: LucideIcon; box: string; icon: string }> = {
  info: { Icon: Info, box: "border-border bg-surface-sunken", icon: "text-muted" },
  success: { Icon: CircleCheck, box: "border-success bg-success-subtle", icon: "text-success-fg" },
  warning: { Icon: TriangleAlert, box: "border-warning bg-warning-subtle", icon: "text-warning-fg" },
  danger: { Icon: CircleAlert, box: "border-danger bg-danger-subtle", icon: "text-danger-fg" },
};

/**
 * An inline message for a region or form: icon + text, never colour alone (Design.md §8).
 * Errors use role="alert" so screen readers announce them; other tones are polite.
 */
export function Callout({ tone, title, children, className }: { tone: Tone; title?: string; children?: ReactNode; className?: string }) {
  const { Icon, box, icon } = TONES[tone];
  return (
    <div role={tone === "danger" ? "alert" : "status"} className={cn("flex gap-3 rounded-sm border p-3", box, className)}>
      <Icon aria-hidden="true" strokeWidth={1.5} className={cn("mt-0.5 size-4 shrink-0", icon)} />
      <div className="space-y-1 text-sm text-fg">
        {title && <p className="font-medium">{title}</p>}
        {children}
      </div>
    </div>
  );
}
