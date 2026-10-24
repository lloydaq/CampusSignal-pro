import { cn } from "@/lib/utils";

/**
 * Who can see a notice or post (Design.md §3.3, required on NoticeItem and PostItem).
 * College: primary-subtle fill. Department: neutral outline, "Dept · CODE".
 * (Public is reserved for future cross-college content and isn't offered yet.)
 */
export function AudienceBadge({ department, className }: { department: { code: string } | null; className?: string }) {
  const base = "inline-flex items-center rounded-sm px-1.5 py-0.5 text-xs font-medium whitespace-nowrap";
  if (!department) return <span className={cn(base, "bg-primary-subtle text-primary", className)}>College</span>;
  return <span className={cn(base, "border border-border-strong text-muted", className)}>Dept · {department.code}</span>;
}
