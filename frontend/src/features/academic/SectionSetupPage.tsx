import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ChevronLeft } from "lucide-react";
import { useId, useState } from "react";
import { Link, useParams } from "react-router";

import { Callout } from "@/components/Callout";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import { DataTable } from "@/components/DataTable";
import { ErrorState } from "@/components/ErrorState";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { fetchMembers } from "@/features/admin/api";
import { errorText } from "@/features/admin/labels";
import { ListLoading } from "@/features/admin/list";
import { ApiError, fieldErrors } from "@/lib/api";
import { usePageTitle } from "@/lib/usePageTitle";

import { hhmm } from "./format";
import { addTimetableEntry, deleteTimetableEntry, fetchTimetable, importEnrollments, removeEnrollment, rollNumbersCsv, setInstructors, setupKeys } from "./setupApi";
import { fetchAllEnrollments, fetchSection, teachingKeys, type Enrollment, type Section } from "./teachingApi";

const DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];

/**
 * A section's setup (ACADEMIC-002, 003): its faculty, its students (roll numbers pasted, as the
 * CSV import) and its timetable. Attendance and results are read on the section page.
 */
export function SectionSetupPage() {
  const { sectionId = "" } = useParams();
  const section = useQuery({ queryKey: teachingKeys.section(sectionId), queryFn: ({ signal }) => fetchSection(sectionId, signal) });
  usePageTitle(section.data ? `${section.data.subject.code} ${section.data.name} · Academics` : "Section · Academics");
  const back = (
    <Link to="/manage/academics" className="inline-flex min-h-8 items-center gap-1 text-sm font-medium text-primary hover:underline pointer-coarse:min-h-11">
      <ChevronLeft aria-hidden="true" strokeWidth={1.5} className="size-4" />
      Sections
    </Link>
  );
  if (section.isPending) return <ListLoading label="Loading the section" />;
  if (section.isError) {
    return (
      <div className="space-y-4">
        {back}
        <ErrorState title="Couldn't load this section." error={section.error} onRetry={() => void section.refetch()} retrying={section.isFetching} />
      </div>
    );
  }
  const s = section.data;
  return (
    <div className="space-y-8">
      <div className="space-y-2">
        {back}
        <h2 className="text-xl font-semibold">
          <span className="font-mono">{s.subject.code}</span> {s.subject.name} · Section {s.name}
        </h2>
        <p className="text-sm text-muted">
          {s.term.name} · {s.department.code} ·{" "}
          <Link to={`/teaching/sections/${s.id}`} className="font-medium text-primary hover:underline">
            Attendance and results
          </Link>
        </p>
      </div>
      <Faculty section={s} />
      <Students section={s} />
      <Timetable section={s} />
    </div>
  );
}

function Faculty({ section }: { section: Section }) {
  const queryClient = useQueryClient();
  const searchId = useId();
  const [search, setSearch] = useState("");
  const faculty = useQuery({
    queryKey: ["setup", "faculty", search],
    queryFn: ({ signal }) => fetchMembers({ query: search, kind: "FACULTY", status: "ACTIVE" }, null, signal),
    enabled: search.trim().length >= 2,
  });
  const save = useMutation({
    mutationFn: (ids: string[]) => setInstructors(section.id, ids),
    onSuccess: (updated) => {
      setSearch("");
      queryClient.setQueryData(teachingKeys.section(section.id), updated);
      void queryClient.invalidateQueries({ queryKey: ["setup", "sections"] });
    },
  });
  const current = section.instructors.map((i) => i.membership_id);
  const candidates = (faculty.data?.items ?? []).filter((m) => !current.includes(m.id));
  return (
    <section aria-labelledby="faculty-heading" className="space-y-3">
      <h3 id="faculty-heading" className="text-base font-semibold">
        Faculty
      </h3>
      {section.instructors.length === 0 ? (
        <p className="text-sm text-warning-fg">No faculty assigned yet. Nobody can take attendance or enter scores.</p>
      ) : (
        <ul aria-label="Assigned faculty" className="divide-y divide-border rounded-sm border border-border">
          {section.instructors.map((i) => (
            <li key={i.membership_id} className="flex items-center justify-between gap-3 px-4 py-2 text-sm">
              <span className="font-medium">{i.display_name}</span>
              <Button size="sm" variant="ghost" disabled={save.isPending} onClick={() => save.mutate(current.filter((id) => id !== i.membership_id))}>
                Remove
              </Button>
            </li>
          ))}
        </ul>
      )}
      <div className="max-w-md space-y-1.5">
        <label htmlFor={searchId} className="block text-sm font-medium">
          Find faculty to assign
        </label>
        <Input id={searchId} value={search} placeholder="Type at least 2 letters of a name" onChange={(e) => setSearch(e.target.value)} />
      </div>
      {search.trim().length >= 2 && !faculty.isPending && (
        <ul aria-label="Faculty found" className="max-w-md divide-y divide-border rounded-sm border border-border">
          {candidates.length === 0 && <li className="px-4 py-3 text-sm text-muted">No active faculty match.</li>}
          {candidates.map((m) => (
            <li key={m.id} className="flex items-center justify-between gap-3 px-4 py-2 text-sm">
              <span>
                {m.display_name}
                {m.department && <span className="text-muted"> · {m.department.code}</span>}
              </span>
              <Button size="sm" variant="secondary" aria-label={`Assign ${m.display_name}`} disabled={save.isPending} onClick={() => save.mutate([...current, m.id])}>
                Assign
              </Button>
            </li>
          ))}
        </ul>
      )}
      {save.isError && <Callout tone="danger">{errorText(save.error)}</Callout>}
    </section>
  );
}

interface RowProblem {
  row: number;
  column: string | null;
  message: string;
}

function Students({ section }: { section: Section }) {
  const queryClient = useQueryClient();
  const pasteId = useId();
  const [text, setText] = useState("");
  const [added, setAdded] = useState<string | null>(null);
  const [removing, setRemoving] = useState<Enrollment | null>(null);
  const students = useQuery({ queryKey: teachingKeys.enrollments(section.id), queryFn: ({ signal }) => fetchAllEnrollments(section.id, signal) });
  const refresh = async () => {
    await queryClient.invalidateQueries({ queryKey: teachingKeys.enrollments(section.id) });
    await queryClient.invalidateQueries({ queryKey: teachingKeys.section(section.id) });
  };
  const enroll = useMutation({
    mutationFn: () => importEnrollments(section.id, rollNumbersCsv(text)),
    onSuccess: async (result) => {
      setText("");
      setAdded(`${result.enrolled === 1 ? "1 student" : `${result.enrolled} students`} enrolled${result.already_enrolled ? `; ${result.already_enrolled} already were` : ""}.`);
      await refresh();
    },
  });
  const remove = useMutation({
    mutationFn: (id: string) => removeEnrollment(id),
    onSuccess: async () => {
      setRemoving(null);
      await refresh();
    },
  });
  const problems = enroll.error instanceof ApiError && Array.isArray(enroll.error.details) ? (enroll.error.details as RowProblem[]).filter((p) => typeof p.row === "number") : [];
  return (
    <section aria-labelledby="students-heading" className="space-y-3">
      <h3 id="students-heading" className="text-base font-semibold">
        Students
      </h3>
      {students.isPending ? (
        <ListLoading label="Loading students" />
      ) : students.isError ? (
        <ErrorState title="Couldn't load the students." error={students.error} onRetry={() => void students.refetch()} retrying={students.isFetching} />
      ) : students.data.length === 0 ? (
        <p className="text-sm text-muted">No students are enrolled yet.</p>
      ) : (
        <DataTable
          caption="Enrolled students"
          rows={students.data}
          rowKey={(e) => e.id}
          columns={[
            { header: "Name", cell: (e) => e.display_name },
            { header: "Roll number", cell: (e) => <span className="font-mono">{e.roll_number ?? "—"}</span> },
            { header: "Department", cell: (e) => e.department?.code ?? "—" },
            {
              header: "Remove",
              cell: (e) => (
                <Button size="sm" variant="ghost" aria-label={`Remove ${e.display_name}`} onClick={() => setRemoving(e)}>
                  Remove
                </Button>
              ),
            },
          ]}
        />
      )}
      <form
        aria-label="Enroll students"
        noValidate
        onSubmit={(e) => {
          e.preventDefault();
          setAdded(null);
          enroll.mutate();
        }}
        className="max-w-md space-y-2"
      >
        <label htmlFor={pasteId} className="block text-sm font-medium">
          Enroll by roll number
        </label>
        <Textarea id={pasteId} value={text} rows={4} className="font-mono" placeholder={"N-001\nN-002"} onChange={(e) => setText(e.target.value)} />
        <p className="text-xs text-muted">One per line (or a CSV with a roll_number column). Only active students of the college are enrolled; if any line is wrong, nobody is.</p>
        <Button type="submit" size="sm" disabled={!text.trim() || enroll.isPending}>
          {enroll.isPending ? "Enrolling…" : "Enroll"}
        </Button>
      </form>
      {added && <Callout tone="success">{added}</Callout>}
      {enroll.isError && (
        <div className="space-y-2">
          <Callout tone="danger">{errorText(enroll.error)}</Callout>
          {problems.length > 0 && (
            <DataTable
              caption="Problems in the list"
              rows={problems}
              rowKey={(p) => `${p.row}-${p.message}`}
              columns={[
                { header: "Line", cell: (p) => p.row },
                { header: "Problem", cell: (p) => p.message },
              ]}
            />
          )}
        </div>
      )}
      {removing && (
        <ConfirmDialog
          title={`Remove ${removing.display_name} from this section?`}
          description="Students with attendance or results in this section can't be removed."
          confirmLabel="Remove student"
          pendingLabel="Removing…"
          pending={remove.isPending}
          error={remove.isError ? errorText(remove.error) : null}
          onConfirm={() => remove.mutate(removing.id)}
          onCancel={() => {
            setRemoving(null);
            remove.reset();
          }}
        />
      )}
    </section>
  );
}

function Timetable({ section }: { section: Section }) {
  const queryClient = useQueryClient();
  const ids = { day: useId(), start: useId(), end: useId(), room: useId() };
  const [form, setForm] = useState({ weekday: 1, starts_at: "09:00", ends_at: "10:00", room: "" });
  const entries = useQuery({ queryKey: setupKeys.timetable(section.id), queryFn: ({ signal }) => fetchTimetable(section.id, signal) });
  const refresh = () => queryClient.invalidateQueries({ queryKey: setupKeys.timetable(section.id) });
  const add = useMutation({
    mutationFn: () => addTimetableEntry(section.id, { ...form, room: form.room.trim() }),
    onSuccess: async () => {
      setForm((f) => ({ ...f, room: "" }));
      await refresh();
    },
  });
  const remove = useMutation({ mutationFn: deleteTimetableEntry, onSuccess: refresh });
  const errors = fieldErrors(add.error);
  const sorted = [...(entries.data?.items ?? [])].sort((a, b) => a.weekday - b.weekday || a.starts_at.localeCompare(b.starts_at));
  return (
    <section aria-labelledby="timetable-heading" className="space-y-3">
      <h3 id="timetable-heading" className="text-base font-semibold">
        Timetable
      </h3>
      {entries.isPending ? (
        <ListLoading label="Loading the timetable" />
      ) : entries.isError ? (
        <ErrorState title="Couldn't load the timetable." error={entries.error} onRetry={() => void entries.refetch()} retrying={entries.isFetching} />
      ) : sorted.length === 0 ? (
        <p className="text-sm text-muted">No classes scheduled yet.</p>
      ) : (
        <ul aria-label="Scheduled classes" className="max-w-xl divide-y divide-border rounded-sm border border-border">
          {sorted.map((e) => (
            <li key={e.id} className="flex items-center justify-between gap-3 px-4 py-2 text-sm">
              <span>
                <span className="font-medium">{DAYS[e.weekday - 1]}</span>{" "}
                <span className="font-mono text-muted">
                  {hhmm(e.starts_at)}–{hhmm(e.ends_at)}
                </span>{" "}
                · {e.room}
              </span>
              <Button size="sm" variant="ghost" aria-label={`Remove ${DAYS[e.weekday - 1]} ${hhmm(e.starts_at)}`} disabled={remove.isPending} onClick={() => remove.mutate(e.id)}>
                Remove
              </Button>
            </li>
          ))}
        </ul>
      )}
      <form
        aria-label="Add a class"
        noValidate
        onSubmit={(e) => {
          e.preventDefault();
          add.mutate();
        }}
        className="grid max-w-xl gap-3 rounded-sm border border-border p-4 sm:grid-cols-4"
      >
        <div className="space-y-1.5">
          <label htmlFor={ids.day} className="block text-sm font-medium">
            Day
          </label>
          <Select id={ids.day} value={form.weekday} onChange={(e) => setForm({ ...form, weekday: Number(e.target.value) })}>
            {DAYS.map((d, i) => (
              <option key={d} value={i + 1}>
                {d}
              </option>
            ))}
          </Select>
        </div>
        <div className="space-y-1.5">
          <label htmlFor={ids.start} className="block text-sm font-medium">
            Starts
          </label>
          <Input id={ids.start} type="time" value={form.starts_at} onChange={(e) => setForm({ ...form, starts_at: e.target.value })} />
        </div>
        <div className="space-y-1.5">
          <label htmlFor={ids.end} className="block text-sm font-medium">
            Ends
          </label>
          <Input id={ids.end} type="time" value={form.ends_at} onChange={(e) => setForm({ ...form, ends_at: e.target.value })} />
        </div>
        <div className="space-y-1.5">
          <label htmlFor={ids.room} className="block text-sm font-medium">
            Room
          </label>
          <Input id={ids.room} value={form.room} maxLength={60} onChange={(e) => setForm({ ...form, room: e.target.value })} aria-invalid={Boolean(errors.room) || undefined} />
        </div>
        <div className="sm:col-span-4">
          <Button type="submit" size="sm" disabled={add.isPending || !form.room.trim()}>
            {add.isPending ? "Adding…" : "Add class"}
          </Button>
        </div>
        {add.isError && (
          <div className="sm:col-span-4">
            <Callout tone="danger">{Object.values(errors)[0] ?? errorText(add.error)}</Callout>
          </div>
        )}
      </form>
      {remove.isError && <Callout tone="danger">{errorText(remove.error)}</Callout>}
    </section>
  );
}
