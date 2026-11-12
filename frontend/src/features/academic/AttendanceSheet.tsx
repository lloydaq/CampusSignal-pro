import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ChevronLeft } from "lucide-react";
import { useEffect, useId, useMemo, useRef, useState, type KeyboardEvent } from "react";
import { Link, useBlocker, useLocation, useNavigate, useParams, useSearchParams } from "react-router";

import { Callout } from "@/components/Callout";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import { ErrorState } from "@/components/ErrorState";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { ListLoading } from "@/features/admin/list";
import { errorText } from "@/features/admin/labels";
import { useCollegeTimezone } from "@/features/admin/tabs";
import { ApiError, fieldErrors } from "@/lib/api";
import { usePageTitle } from "@/lib/usePageTitle";
import { cn } from "@/lib/utils";

import type { AttendanceStatus } from "./api";
import { collegeToday, formatDay } from "./format";
import {
  editSession,
  fetchAllEnrollments,
  fetchSection,
  fetchSession,
  recordSession,
  teachingKeys,
  type AttendanceSessionDetail,
  type EditMode,
  type Section,
} from "./teachingApi";

const STATUSES: { value: AttendanceStatus; label: string; key: string }[] = [
  { value: "PRESENT", label: "Present", key: "p" },
  { value: "ABSENT", label: "Absent", key: "a" },
  { value: "EXCUSED", label: "Excused", key: "e" },
];
const TONE: Record<AttendanceStatus, string> = {
  PRESENT: "peer-checked:border-success peer-checked:bg-success-subtle peer-checked:text-success-fg",
  ABSENT: "peer-checked:border-danger peer-checked:bg-danger-subtle peer-checked:text-danger-fg",
  EXCUSED: "peer-checked:border-border-strong peer-checked:bg-surface-sunken peer-checked:text-fg",
};
const SLOTS = Array.from({ length: 12 }, (_, i) => i + 1);

interface Student {
  enrollment_id: string;
  display_name: string;
}

/** Take attendance for a section (ACADEMIC-005): everyone starts Present. */
export function NewAttendancePage() {
  const { sectionId = "" } = useParams();
  const section = useQuery({ queryKey: teachingKeys.section(sectionId), queryFn: ({ signal }) => fetchSection(sectionId, signal) });
  const students = useQuery({ queryKey: teachingKeys.enrollments(sectionId), queryFn: ({ signal }) => fetchAllEnrollments(sectionId, signal) });
  usePageTitle("Take attendance");
  if (section.isPending || students.isPending) return <ListLoading label="Loading the class list" />;
  if (section.isError) return <ErrorState title="Couldn't load this section." error={section.error} onRetry={() => void section.refetch()} retrying={section.isFetching} />;
  if (students.isError) return <ErrorState title="Couldn't load the class list." error={students.error} onRetry={() => void students.refetch()} retrying={students.isFetching} />;
  return <Sheet section={section.data} students={students.data.map((e) => ({ enrollment_id: e.id, display_name: e.display_name }))} />;
}

/** A recorded session: editable by its faculty inside the window, by a department admin with a reason, else read-only (ACADEMIC-006). */
export function AttendanceSessionPage() {
  const { sessionId = "" } = useParams();
  const session = useQuery({ queryKey: teachingKeys.session(sessionId), queryFn: ({ signal }) => fetchSession(sessionId, signal) });
  const sectionId = session.data?.section_id ?? "";
  const section = useQuery({ queryKey: teachingKeys.section(sectionId), queryFn: ({ signal }) => fetchSection(sectionId, signal), enabled: Boolean(sectionId) });
  usePageTitle("Attendance");
  if (session.isError) return <ErrorState title="Couldn't load this attendance." error={session.error} onRetry={() => void session.refetch()} retrying={session.isFetching} />;
  if (section.isError) return <ErrorState title="Couldn't load this section." error={section.error} onRetry={() => void section.refetch()} retrying={section.isFetching} />;
  if (session.isPending || section.isPending) return <ListLoading label="Loading attendance" />;
  const students = session.data.records.map((r) => ({ enrollment_id: r.enrollment_id, display_name: r.display_name }));
  return <Sheet key={`${session.data.id}-${session.data.version}`} section={section.data} students={students} session={session.data} />;
}

function Sheet({ section, students, session }: { section: Section; students: Student[]; session?: AttendanceSessionDetail }) {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const location = useLocation();
  const timeZone = useCollegeTimezone();
  const dateId = useId();
  const slotId = useId();
  const reasonId = useId();
  const mode: EditMode | "new" = session ? session.edit : "new";
  const editable = mode === "new" || mode === "faculty" || mode === "correction";
  const initial = useMemo(
    () => Object.fromEntries(session ? session.records.map((r) => [r.enrollment_id, r.status]) : students.map((s) => [s.enrollment_id, "PRESENT"])) as Record<string, AttendanceStatus>,
    [session, students],
  );
  const [marks, setMarks] = useState(initial);
  const [params] = useSearchParams();
  // From the home's "Attendance not taken": the class's date, if it's a real past date.
  const [heldOn, setHeldOn] = useState(() => {
    const asked = params.get("date");
    return asked && /^\d{4}-\d{2}-\d{2}$/.test(asked) && asked <= collegeToday(timeZone) ? asked : collegeToday(timeZone);
  });
  const [slot, setSlot] = useState(1);
  const [reason, setReason] = useState("");
  const [reasonMissing, setReasonMissing] = useState(false);
  const rows = useRef<(HTMLDivElement | null)[]>([]);
  const leaving = useRef(false); // set once saved, so the guard lets the redirect through
  const dirty = mode === "new" || students.some((s) => marks[s.enrollment_id] !== initial[s.enrollment_id]);
  const changes = students.filter((s) => marks[s.enrollment_id] !== initial[s.enrollment_id]);

  const save = useMutation({
    mutationFn: () => {
      if (!session) return recordSession(section.id, { held_on: heldOn, slot, records: students.map((s) => ({ enrollment_id: s.enrollment_id, status: marks[s.enrollment_id]! })) });
      const records = changes.map((s) => ({ enrollment_id: s.enrollment_id, status: marks[s.enrollment_id]! }));
      return editSession(session.id, { version: session.version, records, ...(reason.trim() ? { reason: reason.trim() } : {}) });
    },
    onSuccess: async (saved) => {
      leaving.current = true;
      queryClient.setQueryData(teachingKeys.session(saved.id), saved);
      await queryClient.invalidateQueries({ queryKey: teachingKeys.sessions(section.id) });
      void navigate(`/teaching/sessions/${saved.id}`, { replace: true, state: { saved: true } });
    },
  });
  const blocker = useBlocker(({ currentLocation, nextLocation }) => editable && dirty && !leaving.current && currentLocation.pathname !== nextLocation.pathname);
  useEffect(() => {
    if (!(editable && dirty)) return;
    const warn = (event: BeforeUnloadEvent) => event.preventDefault();
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [editable, dirty]);

  const counts = STATUSES.map((s) => ({ ...s, n: students.filter((st) => marks[st.enrollment_id] === s.value).length }));
  const set = (id: string, status: AttendanceStatus) => setMarks((m) => ({ ...m, [id]: status }));
  const focusRow = (i: number) => rows.current[i]?.querySelector<HTMLInputElement>("input:checked")?.focus();
  const onRowKey = (event: KeyboardEvent<HTMLDivElement>, i: number, id: string) => {
    const status = STATUSES.find((s) => s.key === event.key.toLowerCase());
    if (status && editable) {
      event.preventDefault();
      set(id, status.value);
      requestAnimationFrame(() => focusRow(i));
    } else if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      focusRow(Math.min(Math.max(i + (event.key === "ArrowDown" ? 1 : -1), 0), students.length - 1));
    }
  };
  const submit = () => {
    if (mode === "correction" && !reason.trim()) {
      setReasonMissing(true);
      return;
    }
    save.mutate();
  };
  const problems = save.error ? fieldErrors(save.error) : {};
  const conflict = save.error instanceof ApiError && save.error.code === "version_conflict";

  return (
    <div className="space-y-6">
      <Link to={`/teaching/sections/${section.id}`} className="inline-flex min-h-8 items-center gap-1 text-sm font-medium text-primary hover:underline pointer-coarse:min-h-11">
        <ChevronLeft aria-hidden="true" strokeWidth={1.5} className="size-4" />
        <span className="font-mono">{section.subject.code}</span> Section {section.name}
      </Link>
      <div className="space-y-1">
        <h1 className="text-2xl font-semibold text-fg sm:text-3xl">{session ? "Attendance" : "Take attendance"}</h1>
        <p className="text-sm text-muted">
          <span className="font-mono">{section.subject.code}</span> {section.subject.name} · Section {section.name}
          {session && ` · ${formatDay(session.held_on)}, period ${session.slot} · recorded by ${session.recorded_by.display_name}`}
        </p>
      </div>
      {(location.state as { saved?: boolean } | null)?.saved && !dirty && <Callout tone="success">Attendance saved.</Callout>}
      {mode === "window_closed" && (
        <Callout tone="info" title="Edit window closed — ask your department admin">
          Faculty can change a session for {hoursText(session!)} after recording it. Your department admin can still correct it, with a reason.
        </Callout>
      )}
      {mode === null && <Callout tone="info">You can view this attendance but not change it.</Callout>}
      {mode === "correction" && <Callout tone="warning">You're correcting attendance as department admin. Give a reason; it goes in the audit log with each change.</Callout>}

      {!session && (
        <div className="grid max-w-md gap-4 sm:grid-cols-2">
          <div className="space-y-1.5">
            <label htmlFor={dateId} className="block text-sm font-medium">
              Date
            </label>
            <Input id={dateId} type="date" value={heldOn} max={collegeToday(timeZone)} onChange={(e) => setHeldOn(e.target.value)} aria-invalid={Boolean(problems.held_on) || undefined} aria-describedby={problems.held_on ? `${dateId}-error` : undefined} />
            {problems.held_on && (
              <p id={`${dateId}-error`} className="text-sm text-danger-fg">
                {problems.held_on}
              </p>
            )}
          </div>
          <div className="space-y-1.5">
            <label htmlFor={slotId} className="block text-sm font-medium">
              Period
            </label>
            <Select id={slotId} value={slot} onChange={(e) => setSlot(Number(e.target.value))}>
              {SLOTS.map((n) => (
                <option key={n} value={n}>
                  Period {n}
                </option>
              ))}
            </Select>
          </div>
        </div>
      )}

      {students.length === 0 ? (
        <Callout tone="info">No students are enrolled in this section yet.</Callout>
      ) : (
        <div className="space-y-2">
          {editable && <p className="text-xs text-muted">Keys: ↑/↓ move between students, P, A or E sets Present, Absent or Excused.</p>}
          <div role="list" aria-label="Class list" className="divide-y divide-border rounded-sm border border-border">
            {students.map((s, i) => (
              <div
                key={s.enrollment_id}
                role="listitem"
                ref={(el) => {
                  rows.current[i] = el;
                }}
                onKeyDown={(e) => onRowKey(e, i, s.enrollment_id)}
                className="flex flex-wrap items-center justify-between gap-3 px-4 py-2"
              >
                <span id={`student-${s.enrollment_id}`} className="text-sm font-medium text-fg">
                  {s.display_name}
                </span>
                <div role="radiogroup" aria-labelledby={`student-${s.enrollment_id}`} className="flex gap-1">
                  {STATUSES.map((st) => (
                    <label key={st.value} className="relative">
                      <input
                        type="radio"
                        name={`mark-${s.enrollment_id}`}
                        value={st.value}
                        checked={marks[s.enrollment_id] === st.value}
                        disabled={!editable}
                        onChange={() => set(s.enrollment_id, st.value)}
                        className="peer sr-only"
                      />
                      <span
                        className={cn(
                          "flex min-h-9 min-w-20 cursor-pointer items-center justify-center rounded-sm border border-border px-2 text-sm text-muted peer-focus-visible:outline-2 peer-focus-visible:outline-offset-2 peer-focus-visible:outline-primary peer-disabled:cursor-default pointer-coarse:min-h-11",
                          TONE[st.value],
                        )}
                      >
                        {st.label}
                      </span>
                    </label>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {mode === "correction" && (
        <div className="max-w-xl space-y-1.5">
          <label htmlFor={reasonId} className="block text-sm font-medium">
            Reason for the correction
          </label>
          <Textarea
            id={reasonId}
            value={reason}
            maxLength={500}
            onChange={(e) => {
              setReason(e.target.value);
              setReasonMissing(false);
            }}
            aria-invalid={reasonMissing || Boolean(problems.reason) || undefined}
            aria-describedby={reasonMissing || problems.reason ? `${reasonId}-error` : undefined}
          />
          {(reasonMissing || problems.reason) && (
            <p id={`${reasonId}-error`} className="text-sm text-danger-fg">
              {problems.reason ?? "Give a reason for the correction."}
            </p>
          )}
        </div>
      )}

      {save.isError && !problems.held_on && !problems.reason && (
        <Callout tone="danger">
          {errorText(save.error)}
          {conflict && (
            <Button size="sm" variant="secondary" className="mt-2" onClick={() => void queryClient.invalidateQueries({ queryKey: teachingKeys.session(session!.id) })}>
              Reload
            </Button>
          )}
        </Callout>
      )}

      {editable && students.length > 0 && (
        <div className="sticky bottom-18 z-10 typing:bottom-0 -mx-4 flex flex-wrap items-center justify-between gap-3 border-t border-border bg-surface px-4 py-3 sm:mx-0 sm:rounded-sm sm:border lg:bottom-0">
          <p className="text-sm tabular-nums" aria-live="polite">
            {counts.map((c, i) => (
              <span key={c.value}>
                {i > 0 && <span className="text-muted"> · </span>}
                <span className="font-mono font-medium">{c.n}</span> {c.label.toLowerCase()}
              </span>
            ))}
          </p>
          <Button onClick={submit} disabled={save.isPending || (Boolean(session) && changes.length === 0)}>
            {save.isPending ? "Saving…" : session ? `Save ${changes.length === 1 ? "1 change" : `${changes.length} changes`}` : "Save attendance"}
          </Button>
        </div>
      )}

      {blocker.state === "blocked" && (
        <ConfirmDialog
          title="Leave without saving?"
          description="The attendance you've marked here will be lost."
          confirmLabel="Leave"
          pendingLabel="Leaving…"
          pending={false}
          error={null}
          onConfirm={() => blocker.proceed()}
          onCancel={() => blocker.reset()}
        />
      )}
    </div>
  );
}

function hoursText(session: AttendanceSessionDetail): string {
  const hours = Math.round((new Date(session.edit_window_closes_at).getTime() - new Date(session.created_at).getTime()) / 3_600_000);
  return hours === 1 ? "1 hour" : `${hours} hours`;
}
