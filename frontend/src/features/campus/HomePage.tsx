import { useQuery } from "@tanstack/react-query";
import { Bell, Megaphone } from "lucide-react";
import { useId, type ReactNode } from "react";
import { Link, Navigate } from "react-router";

import { EmptyState } from "@/components/EmptyState";
import { ErrorState } from "@/components/ErrorState";
import { ListLoading } from "@/features/admin/list";
import { AuthHeading } from "@/features/auth/AuthHeading";
import { landingPath } from "@/features/auth/landing";
import { useMe } from "@/features/auth/session";
import { fetchNotices, type NoticeFilters, type NoticeSummary } from "@/features/notices/api";
import { noticeKeys } from "@/features/notices/labels";
import { NoticeItem } from "@/features/notices/NoticeItem";
import { useUnreadCount } from "@/features/notifications/api";

import { KIND_LABEL, roleLabel } from "./labels";

const LATEST = 5;
const CURRENT: NoticeFilters = { status: "PUBLISHED", past: false, category: "", departmentId: "" };

/**
 * The college home (Design.md §5 screen 3): "What do I need to know today?" An ordered stack, no
 * hero. The notice blocks of HOME-001 were brought forward from Phase 8 (owner, 2026-10-25);
 * classes, attendance and issues arrive with their phases, and nothing that can't be used yet is
 * shown (Design.md §8).
 */
export function HomePage() {
  const me = useMe();
  const membership = me.membership;
  if (!membership || !me.capabilities.includes("campus")) return <Navigate to={landingPath(me)} replace />;
  const { college } = membership;
  return (
    <div className="space-y-10">
      <div className="space-y-4">
        <AuthHeading title={college.name} />
        {college.is_demo && (
          <p className="inline-flex rounded-sm border border-warning bg-warning-subtle px-2 py-1 text-sm font-medium text-warning-fg">
            Demo data: this college and everything in it is fictional.
          </p>
        )}
        <UnreadLink />
      </div>
      <NoticeBlocks collegeName={college.name} timeZone={college.timezone} />
      <Block title="Your membership">
        <dl className="grid gap-4 text-sm sm:grid-cols-2">
          <div>
            <dt className="text-muted">Role</dt>
            <dd className="font-medium">{KIND_LABEL[membership.kind]}</dd>
          </div>
          <div>
            <dt className="text-muted">Department</dt>
            <dd className="font-medium">
              {membership.department ? (
                <Link to={`/departments/${membership.department.id}`} className="text-primary underline underline-offset-2">
                  {membership.department.name} ({membership.department.code})
                </Link>
              ) : (
                "Not set"
              )}
            </dd>
          </div>
          {me.roles.length > 0 && (
            <div className="sm:col-span-2">
              <dt className="text-muted">Responsibilities</dt>
              <dd className="font-medium">{me.roles.map(roleLabel).join(", ")}</dd>
            </div>
          )}
        </dl>
      </Block>
    </div>
  );
}

/** Only when something is unread; the bell already says "nothing new" by having no count. */
function UnreadLink() {
  const unread = useUnreadCount();
  if (unread === 0) return null;
  return (
    <p>
      <Link to="/notifications" className="inline-flex items-center gap-2 text-sm font-medium text-primary underline-offset-2 hover:underline">
        <Bell aria-hidden="true" strokeWidth={1.5} className="size-4" />
        {unread === 1 ? "1 unread notification" : `${unread} unread notifications`}
      </Link>
    </p>
  );
}

/**
 * Urgent notices (only if any) and the latest few, from one request: the list already puts
 * unexpired urgent notices first (NOTICE-005), with the same visibility as the Notices screen.
 */
function NoticeBlocks({ collegeName, timeZone }: { collegeName: string; timeZone: string }) {
  const query = useQuery({ queryKey: [...noticeKeys.all, "list", "home"], queryFn: ({ signal }) => fetchNotices(CURRENT, null, signal) });
  const allLink = (
    <Link to="/notices" className="text-sm font-medium text-primary underline-offset-2 hover:underline">
      All notices
    </Link>
  );
  if (query.isPending) {
    return (
      <Block title="Latest notices" action={allLink}>
        <ListLoading label="Loading notices" />
      </Block>
    );
  }
  if (query.isError) {
    return (
      <Block title="Latest notices" action={allLink}>
        <ErrorState title="Couldn't load notices." error={query.error} onRetry={() => void query.refetch()} retrying={query.isFetching} />
      </Block>
    );
  }
  const urgent = query.data.items.filter((n) => n.pinned);
  const latest = query.data.items.filter((n) => !n.pinned).slice(0, LATEST);
  return (
    <>
      {urgent.length > 0 && (
        <Block title="Urgent now">
          <NoticeList notices={urgent} collegeName={collegeName} timeZone={timeZone} />
        </Block>
      )}
      <Block title="Latest notices" action={allLink}>
        {latest.length === 0 ? (
          <EmptyState Icon={Megaphone} title={urgent.length > 0 ? "No other current notices." : "No current notices."} />
        ) : (
          <NoticeList notices={latest} collegeName={collegeName} timeZone={timeZone} />
        )}
      </Block>
    </>
  );
}

function NoticeList({ notices, collegeName, timeZone }: { notices: NoticeSummary[]; collegeName: string; timeZone: string }) {
  return (
    <ul className="overflow-hidden rounded-sm border border-border bg-surface">
      {notices.map((n) => (
        <NoticeItem key={n.id} notice={n} collegeName={collegeName} timeZone={timeZone} />
      ))}
    </ul>
  );
}

function Block({ title, action, children }: { title: string; action?: ReactNode; children: ReactNode }) {
  const id = useId();
  return (
    <section aria-labelledby={id} className="space-y-3">
      <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
        <h2 id={id} className="text-lg font-semibold">
          {title}
        </h2>
        {action}
      </div>
      {children}
    </section>
  );
}
