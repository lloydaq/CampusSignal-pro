import { Link } from "react-router";

import { AudienceBadge } from "@/components/AudienceBadge";
import { formatDateTime } from "@/lib/datetime";
import { cn } from "@/lib/utils";

import type { NoticeSummary } from "./api";
import { CATEGORY_LABEL, issuer } from "./labels";

/** Priority as a text badge (Design.md §6 NoticeItem): Urgent = danger, High = warning, Normal = none. */
export function PriorityBadge({ priority }: { priority: NoticeSummary["priority"] }) {
  if (priority === "NORMAL") return null;
  const urgent = priority === "URGENT";
  return (
    <span className={cn("inline-flex rounded-sm px-1.5 py-0.5 text-xs font-semibold", urgent ? "bg-danger-subtle text-danger-fg" : "bg-warning-subtle text-warning-fg")}>
      {urgent ? "Urgent" : "High"}
    </span>
  );
}

export function StateBadge({ notice }: { notice: Pick<NoticeSummary, "status" | "expired"> }) {
  const label = notice.status === "DRAFT" ? "Draft" : notice.status === "WITHDRAWN" ? "Withdrawn" : notice.expired ? "Expired" : null;
  if (!label) return null;
  return <span className="inline-flex rounded-sm bg-surface-sunken px-1.5 py-0.5 text-xs font-medium text-muted">{label}</span>;
}

/**
 * Official notice treatment (Design.md §3.3): 3 px primary rule, "Official" label and issuer,
 * no avatar, heading font for the title, audience badge always shown.
 */
export function NoticeItem({ notice, collegeName, timeZone }: { notice: NoticeSummary; collegeName: string; timeZone: string }) {
  const when = notice.published_at ?? notice.created_at;
  return (
    <li className="relative border-b border-border last:border-b-0">
      <span aria-hidden="true" className="absolute inset-y-3 left-0 w-0.75 rounded-sm bg-primary" />
      <Link to={`/notices/${notice.id}`} className="block space-y-2 py-4 pr-4 pl-5 hover:bg-surface-sunken focus-visible:bg-surface-sunken">
        <div className="flex flex-wrap items-center gap-1.5">
          <PriorityBadge priority={notice.priority} />
          <AudienceBadge department={notice.department} />
          <StateBadge notice={notice} />
          <span className="text-xs text-subtle">{CATEGORY_LABEL[notice.category]}</span>
        </div>
        <p className="font-heading text-lg font-semibold text-fg">{notice.title}</p>
        {notice.excerpt && <p className="line-clamp-2 text-sm text-muted">{notice.excerpt}</p>}
        <p className="text-xs text-subtle">
          <span className="font-medium text-muted">Official</span> · {issuer(notice, collegeName)} ·{" "}
          <time dateTime={when}>{formatDateTime(when, timeZone)}</time>
          {notice.edited_at && " · Updated"}
        </p>
      </Link>
    </li>
  );
}
