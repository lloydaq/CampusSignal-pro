import { useQuery } from "@tanstack/react-query";
import { ChevronLeft, CircleCheck, CircleMinus, CircleX, ClipboardCheck, type LucideIcon } from "lucide-react";
import { Link, useParams } from "react-router";

import { EmptyState } from "@/components/EmptyState";
import { ErrorState } from "@/components/ErrorState";
import { ListLoading } from "@/features/admin/list";
import { usePageTitle } from "@/lib/usePageTitle";
import { cn } from "@/lib/utils";

import { NoTerm, TermLine } from "./AcademicsLayout";
import { academicKeys, fetchMyAttendance, fetchMySectionAttendance, type AttendanceStatus } from "./api";
import { formatDay, percent } from "./format";

/** Design.md §5 screen 5: "Am I attending enough?" One row per subject; a row opens its sessions. */
export function AttendanceTab() {
  usePageTitle("Attendance · Academics");
  const query = useQuery({ queryKey: academicKeys.attendance, queryFn: ({ signal }) => fetchMyAttendance(signal) });

  if (query.isPending) return <ListLoading label="Loading your attendance" />;
  if (query.isError) return <ErrorState title="Couldn't load your attendance." error={query.error} onRetry={() => void query.refetch()} retrying={query.isFetching} />;
  const { term, is_demo, items } = query.data;
  if (!term) return <NoTerm />;
  const nothing = items.every((i) => i.held === 0);

  return (
    <div className="space-y-4">
      <TermLine term={term} isDemo={is_demo} />
      {nothing ? (
        <EmptyState Icon={ClipboardCheck} title="No attendance has been recorded for this term yet." />
      ) : (
        <div className="overflow-x-auto rounded-sm border border-border">
          <table className="w-full text-left text-sm tabular-nums">
            <caption className="sr-only">Attendance by subject</caption>
            <thead className="bg-surface-sunken">
              <tr>
                <th scope="col" className="px-4 py-2 font-medium text-muted">
                  Subject
                </th>
                <th scope="col" className="px-3 py-2 text-right font-medium text-muted">
                  Held
                </th>
                <th scope="col" className="px-3 py-2 text-right font-medium text-muted">
                  Attended
                </th>
                <th scope="col" className="px-4 py-2 text-right font-medium text-muted">
                  %
                </th>
              </tr>
            </thead>
            <tbody>
              {items.map((item) => (
                <tr key={item.section.id} className="border-t border-border">
                  <th scope="row" className="px-4 py-3 text-left font-normal">
                    <Link to={item.section.id} className="group inline-flex flex-col rounded-sm hover:underline">
                      <span className="font-mono font-medium text-fg">{item.subject.code}</span>
                      <span className="text-muted">{item.subject.name}</span>
                    </Link>
                  </th>
                  <td className="px-3 py-3 text-right font-mono">{item.held}</td>
                  <td className="px-3 py-3 text-right font-mono">{item.attended}</td>
                  <td className="px-4 py-3 text-right font-mono font-medium">{percent(item)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <p className="text-xs text-muted">Excused sessions don't count towards the percentage.</p>
    </div>
  );
}

const STATUS: Record<AttendanceStatus, { label: string; Icon: LucideIcon; tone: string }> = {
  PRESENT: { label: "Present", Icon: CircleCheck, tone: "text-success-fg" },
  ABSENT: { label: "Absent", Icon: CircleX, tone: "text-danger-fg" },
  EXCUSED: { label: "Excused", Icon: CircleMinus, tone: "text-muted" },
};

/** One subject's sessions: date, period, status with icon + text (never colour alone). */
export function SubjectAttendancePage() {
  const { sectionId = "" } = useParams();
  const query = useQuery({ queryKey: academicKeys.section(sectionId), queryFn: ({ signal }) => fetchMySectionAttendance(sectionId, signal) });
  usePageTitle(query.data ? `${query.data.subject.code} attendance · Academics` : "Attendance · Academics");
  const back = (
    <Link to=".." relative="path" className="inline-flex min-h-8 items-center gap-1 text-sm font-medium text-primary hover:underline pointer-coarse:min-h-11">
      <ChevronLeft aria-hidden="true" strokeWidth={1.5} className="size-4" />
      All subjects
    </Link>
  );

  if (query.isPending) return <ListLoading label="Loading attendance" />;
  if (query.isError) {
    return (
      <div className="space-y-4">
        {back}
        <ErrorState title="Couldn't load this subject's attendance." error={query.error} onRetry={() => void query.refetch()} retrying={query.isFetching} />
      </div>
    );
  }
  const detail = query.data;
  return (
    <div className="space-y-4">
      {back}
      <TermLine term={detail.term} isDemo={detail.is_demo} />
      <div className="space-y-1">
        <h2 className="text-lg font-semibold">
          <span className="font-mono">{detail.subject.code}</span> {detail.subject.name}
        </h2>
        <p className="text-sm text-muted tabular-nums">
          Attended <span className="font-mono text-fg">{detail.attended}</span> of <span className="font-mono text-fg">{detail.held - detail.excused}</span> counted
          {detail.excused > 0 && ` (${detail.excused} excused)`} · <span className="font-mono font-medium text-fg">{percent(detail)}</span>
        </p>
      </div>
      {detail.sessions.length === 0 ? (
        <EmptyState Icon={ClipboardCheck} title="No attendance has been recorded for this subject yet." />
      ) : (
        <ul aria-label="Sessions" className="divide-y divide-border rounded-sm border border-border">
          {detail.sessions.map((s) => {
            const { label, Icon, tone } = STATUS[s.status];
            return (
              <li key={`${s.held_on}-${s.slot}`} className="flex items-center justify-between gap-3 px-4 py-3 text-sm">
                <span>
                  {formatDay(s.held_on)} <span className="text-muted">· Period {s.slot}</span>
                </span>
                <span className={cn("inline-flex items-center gap-1.5 font-medium", tone)}>
                  <Icon aria-hidden="true" strokeWidth={1.5} className="size-4" />
                  {label}
                </span>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
