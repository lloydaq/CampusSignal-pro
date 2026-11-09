import type { UseQueryResult } from "@tanstack/react-query";
import { CalendarDays, ClipboardCheck, ClipboardList, Inbox } from "lucide-react";
import type { ReactNode } from "react";
import { Link } from "react-router";

import { Callout } from "@/components/Callout";
import { EmptyState } from "@/components/EmptyState";
import { ErrorState } from "@/components/ErrorState";
import { formatDay, hhmm, percent } from "@/features/academic/format";
import { ListLoading } from "@/features/admin/list";
import { StatusBadge } from "@/features/issues/StatusBadge";
import { cn } from "@/lib/utils";

import type { Home, QueueKind } from "./homeApi";

const LINK = "text-sm font-medium text-primary underline-offset-2 hover:underline";

const QUEUES: Record<QueueKind, { label: (n: number) => string; to: string }> = {
  membership_requests: { label: (n) => (n === 1 ? "1 request to join" : `${n} requests to join`), to: "/manage/requests" },
  content_reports: { label: (n) => (n === 1 ? "1 open report" : `${n} open reports`), to: "/manage/moderation" },
  unacknowledged_issues: { label: (n) => (n === 1 ? "1 issue not yet acknowledged" : `${n} issues not yet acknowledged`), to: "/issues/queue" },
};

/** The page's section wrapper (Design.md §5 screen 3: an ordered stack of blocks). */
export function Block({ id, title, action, children }: { id: string; title: string; action?: ReactNode; children: ReactNode }) {
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

/** One block's body: loading, the whole request failing, this block failing, or its content. */
function Body({ query, failed, label, children }: { query: UseQueryResult<Home>; failed: boolean; label: string; children: () => ReactNode }) {
  if (query.isPending) return <ListLoading label={`Loading ${label}`} />;
  if (query.isError) return <ErrorState title={`Couldn't load ${label}.`} error={query.error} onRetry={() => void query.refetch()} retrying={query.isFetching} />;
  if (failed) return <Callout tone="danger">Couldn't load {label} just now. The rest of the page is fine; try again later.</Callout>;
  return <>{children()}</>;
}

/** HOME-003: "Needs your attention", only queues the viewer can act on. */
export function QueuesBlock({ query }: { query: UseQueryResult<Home> }) {
  const block = query.data?.queues;
  if (query.isSuccess && !block) return null;
  if (query.isPending) return null; // admins only; don't flash a block others never get
  return (
    <Block id="home-queues" title="Needs your attention">
      <Body query={query} failed={block?.status === "error"} label="your queues">
        {() => {
          const waiting = block!.items.filter((q) => q.count > 0);
          if (waiting.length === 0) return <EmptyState Icon={Inbox} title="Nothing is waiting for you." />;
          return (
            <ul aria-label="Waiting for you" className="divide-y divide-border rounded-sm border border-border">
              {waiting.map((q) => (
                <li key={q.kind}>
                  <Link to={QUEUES[q.kind].to} className="flex min-h-11 items-center justify-between gap-3 px-4 py-3 font-medium text-fg hover:bg-surface-sunken">
                    {QUEUES[q.kind].label(q.count)}
                    <span aria-hidden="true" className="text-primary">
                      →
                    </span>
                  </Link>
                </li>
              ))}
            </ul>
          );
        }}
      </Body>
    </Block>
  );
}

/** HOME-001/002: today's classes; faculty get "Take attendance" on each. */
export function ClassesBlock({ query, teaching }: { query: UseQueryResult<Home>; teaching: boolean }) {
  const block = query.data?.classes;
  if (query.isSuccess && !block) return null;
  const action = (
    <Link to={teaching ? "/teaching" : "/academics/timetable"} className={LINK}>
      {teaching ? "Your sections" : "Timetable"}
    </Link>
  );
  return (
    <Block id="home-classes" title="Today's classes" action={action}>
      <Body query={query} failed={block?.status === "error"} label="today's classes">
        {() => {
          if (!block!.term) return <EmptyState Icon={CalendarDays} title="Your college hasn't set up the current term yet." />;
          if (block!.items.length === 0) return <EmptyState Icon={CalendarDays} title="No classes today." />;
          return (
            <ul aria-label="Today's classes" className="divide-y divide-border rounded-sm border border-border">
              {block!.items.map((c) => (
                <li key={`${c.section.id}-${c.starts_at}`} className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2 px-4 py-3">
                  <span className="flex items-start gap-4">
                    <span className="w-24 shrink-0 font-mono text-sm tabular-nums text-muted">
                      {hhmm(c.starts_at)}–{hhmm(c.ends_at)}
                    </span>
                    <span className="text-sm">
                      <span className="block font-medium">
                        <span className="font-mono">{c.subject.code}</span> {c.subject.name}
                      </span>
                      <span className="block text-muted">
                        {c.room} · Section {c.section.name}
                      </span>
                    </span>
                  </span>
                  {teaching && (
                    <Link to={`/teaching/sections/${c.section.id}/attendance/new`} className={LINK}>
                      Take attendance
                    </Link>
                  )}
                </li>
              ))}
            </ul>
          );
        }}
      </Body>
    </Block>
  );
}

/** HOME-001: attendance at a glance, one line per subject, mono figures. */
export function AttendanceBlock({ query }: { query: UseQueryResult<Home> }) {
  const block = query.data?.attendance;
  if (query.isSuccess && !block) return null;
  return (
    <Block
      id="home-attendance"
      title="Attendance"
      action={
        <Link to="/academics/attendance" className={LINK}>
          Details
        </Link>
      }
    >
      <Body query={query} failed={block?.status === "error"} label="attendance">
        {() => {
          if (!block!.term) return <EmptyState Icon={ClipboardCheck} title="Your college hasn't set up the current term yet." />;
          if (block!.items.every((i) => i.held === 0)) return <EmptyState Icon={ClipboardCheck} title="No attendance has been recorded for this term yet." />;
          return (
            <ul aria-label="Attendance by subject" className="divide-y divide-border rounded-sm border border-border">
              {block!.items.map((i) => (
                <li key={i.section.id} className="flex items-center justify-between gap-3 px-4 py-2.5 text-sm">
                  <span>
                    <span className="font-mono font-medium">{i.subject.code}</span> <span className="text-muted">{i.subject.name}</span>
                  </span>
                  <span className="font-mono font-medium tabular-nums">{percent(i)}</span>
                </li>
              ))}
            </ul>
          );
        }}
      </Body>
    </Block>
  );
}

/** HOME-002: timetabled classes in the last week with no attendance taken. */
export function NeedsAttendanceBlock({ query }: { query: UseQueryResult<Home> }) {
  const block = query.data?.needs_attendance;
  if (query.isSuccess && !block) return null;
  if (query.isPending) return null;
  return (
    <Block id="home-needs-attendance" title="Attendance not taken">
      <Body query={query} failed={block?.status === "error"} label="missing attendance">
        {() =>
          block!.items.length === 0 ? (
            <EmptyState Icon={ClipboardCheck} title="Attendance is up to date for the last 7 days." />
          ) : (
            <ul aria-label="Attendance not taken" className="divide-y divide-border rounded-sm border border-border">
              {block!.items.map((m) => (
                <li key={`${m.section.id}-${m.held_on}`} className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1 px-4 py-3 text-sm">
                  <span>
                    <span className="font-medium">
                      <span className="font-mono">{m.subject.code}</span> Section {m.section.name}
                    </span>
                    <span className="text-muted">
                      {" "}
                      · {formatDay(m.held_on)}, {hhmm(m.starts_at)}
                    </span>
                  </span>
                  <Link to={`/teaching/sections/${m.section.id}/attendance/new?date=${m.held_on}`} className={LINK}>
                    Take attendance
                  </Link>
                </li>
              ))}
            </ul>
          )
        }
      </Body>
    </Block>
  );
}

/** HOME-001: the viewer's own open issues, with status. */
export function MyIssuesBlock({ query }: { query: UseQueryResult<Home> }) {
  const block = query.data?.my_issues;
  return (
    <Block
      id="home-issues"
      title="My open issues"
      action={
        <Link to="/issues" className={LINK}>
          {block && block.open_count > block.items.length ? `All ${block.open_count}` : "My issues"}
        </Link>
      }
    >
      <Body query={query} failed={block?.status === "error"} label="your issues">
        {() =>
          block!.items.length === 0 ? (
            <EmptyState Icon={ClipboardList} title="You have no open issues.">
              <Link to="/issues/new" className={LINK}>
                Report an issue
              </Link>
            </EmptyState>
          ) : (
            <ul aria-label="My open issues" className="divide-y divide-border rounded-sm border border-border">
              {block!.items.map((i) => (
                <li key={i.id}>
                  <Link to={`/issues/${i.id}`} className={cn("flex flex-wrap items-center justify-between gap-x-4 gap-y-1 px-4 py-3 hover:bg-surface-sunken")}>
                    <span className="font-medium text-fg">{i.title}</span>
                    <StatusBadge status={i.status} />
                  </Link>
                </li>
              ))}
            </ul>
          )
        }
      </Body>
    </Block>
  );
}
