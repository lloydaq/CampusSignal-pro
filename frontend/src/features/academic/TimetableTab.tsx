import { useQuery } from "@tanstack/react-query";
import { CalendarDays } from "lucide-react";
import { useState } from "react";

import { EmptyState } from "@/components/EmptyState";
import { ErrorState } from "@/components/ErrorState";
import { ListLoading } from "@/features/admin/list";
import { useCollegeTimezone } from "@/features/admin/tabs";
import { usePageTitle } from "@/lib/usePageTitle";
import { cn } from "@/lib/utils";

import { NoTerm, TermLine } from "./AcademicsLayout";
import { academicKeys, fetchMyTimetable, type MyClass } from "./api";
import { collegeWeekday, hhmm, SHORT } from "./format";

const DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];

/**
 * Design.md §5 screen 7: "Where am I supposed to be?" Phones: a day picker (Mon–Sat, Sunday
 * only when it has classes) and that day's list. Desktop: the week as a grid, rows = times.
 * Today is highlighted.
 */
export function TimetableTab() {
  usePageTitle("Timetable · Academics");
  const timeZone = useCollegeTimezone();
  const today = collegeWeekday(timeZone);
  const query = useQuery({ queryKey: academicKeys.timetable, queryFn: ({ signal }) => fetchMyTimetable(signal) });
  const [picked, setPicked] = useState<number | null>(null);

  if (query.isPending) return <ListLoading label="Loading your timetable" />;
  if (query.isError) return <ErrorState title="Couldn't load your timetable." error={query.error} onRetry={() => void query.refetch()} retrying={query.isFetching} />;
  const { term, is_demo, classes } = query.data;
  if (!term) return <NoTerm />;

  const days = classes.some((c) => c.weekday === 7) ? [1, 2, 3, 4, 5, 6, 7] : [1, 2, 3, 4, 5, 6];
  const day = picked ?? (days.includes(today) ? today : 1);
  const byDay = (weekday: number) => classes.filter((c) => c.weekday === weekday).sort((a, b) => a.starts_at.localeCompare(b.starts_at));

  return (
    <div className="space-y-4">
      <TermLine term={term} isDemo={is_demo} />
      {classes.length === 0 ? (
        <EmptyState Icon={CalendarDays} title="No classes in your timetable yet.">
          Your classes appear here once your department enrolls you in sections.
        </EmptyState>
      ) : (
        <>
          <div className="lg:hidden">
            <div role="group" aria-label="Day" className="-mx-4 flex gap-1 overflow-x-auto px-4 pb-1">
              {days.map((d) => (
                <button
                  key={d}
                  type="button"
                  aria-pressed={d === day}
                  onClick={() => setPicked(d)}
                  className={cn(
                    "min-h-11 min-w-12 rounded-sm border px-3 text-sm font-medium",
                    d === day ? "border-primary bg-primary text-on-primary" : "border-border bg-surface text-fg hover:bg-surface-sunken",
                  )}
                >
                  <abbr title={DAY_NAMES[d - 1]} className="no-underline">
                    {SHORT[d - 1]}
                  </abbr>
                  {d === today && <span className="sr-only"> (today)</span>}
                </button>
              ))}
            </div>
            <h2 className="mt-4 mb-2 text-base font-semibold">
              {DAY_NAMES[day - 1]}
              {day === today && <span className="ml-2 text-sm font-normal text-muted">Today</span>}
            </h2>
            <DayList classes={byDay(day)} />
          </div>
          <WeekGrid classes={classes} days={days} today={today} />
        </>
      )}
    </div>
  );
}

function DayList({ classes }: { classes: MyClass[] }) {
  if (classes.length === 0) return <p className="rounded-sm border border-border px-4 py-6 text-center text-sm text-muted">No classes</p>;
  return (
    <ul aria-label="Classes" className="divide-y divide-border rounded-sm border border-border">
      {classes.map((c) => (
        <li key={`${c.section.id}-${c.weekday}-${c.starts_at}`} className="flex items-start gap-4 px-4 py-3">
          <span className="w-24 shrink-0 font-mono text-sm tabular-nums text-muted">
            {hhmm(c.starts_at)}–{hhmm(c.ends_at)}
          </span>
          <span className="min-w-0 space-y-0.5">
            <span className="block text-sm font-medium">
              <span className="font-mono">{c.subject.code}</span> {c.subject.name}
            </span>
            <span className="block text-sm text-muted">
              {c.room} · Section {c.section.name}
            </span>
          </span>
        </li>
      ))}
    </ul>
  );
}

function WeekGrid({ classes, days, today }: { classes: MyClass[]; days: number[]; today: number }) {
  const slots = [...new Set(classes.map((c) => `${c.starts_at}|${c.ends_at}`))].sort();
  return (
    <div className="hidden overflow-x-auto rounded-sm border border-border lg:block">
      <table className="w-full table-fixed text-left text-sm">
        <caption className="sr-only">Your week</caption>
        <thead className="bg-surface-sunken">
          <tr>
            <th scope="col" className="w-32 px-3 py-2 font-medium text-muted">
              Time
            </th>
            {days.map((d) => (
              <th key={d} scope="col" className={cn("px-3 py-2 font-medium", d === today ? "bg-primary-subtle text-primary" : "text-muted")}>
                {DAY_NAMES[d - 1]}
                {d === today && <span className="sr-only"> (today)</span>}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {slots.map((slot) => {
            const [start, end] = slot.split("|") as [string, string];
            return (
              <tr key={slot} className="border-t border-border">
                <th scope="row" className="px-3 py-3 align-top font-mono font-normal tabular-nums text-muted">
                  {hhmm(start)}–{hhmm(end)}
                </th>
                {days.map((d) => {
                  const here = classes.filter((c) => c.weekday === d && c.starts_at === start && c.ends_at === end);
                  return (
                    <td key={d} className={cn("px-3 py-3 align-top", d === today && "bg-primary-subtle/60")}>
                      {here.map((c) => (
                        <span key={c.section.id} className="block">
                          <span className="block font-mono font-medium text-fg">{c.subject.code}</span>
                          <span className="block text-xs text-muted">{c.room}</span>
                        </span>
                      ))}
                    </td>
                  );
                })}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
