import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { BookOpen, CalendarRange, Layers } from "lucide-react";
import { useId, useState, type FormEvent, type ReactNode } from "react";
import { Link, useSearchParams } from "react-router";

import { Callout } from "@/components/Callout";
import { DataTable } from "@/components/DataTable";
import { EmptyState } from "@/components/EmptyState";
import { ErrorState } from "@/components/ErrorState";
import { SubmitButton } from "@/components/SubmitButton";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { fetchDepartments } from "@/features/admin/api";
import { errorText } from "@/features/admin/labels";
import { ListLoading, LoadMore } from "@/features/admin/list";
import { useCursorList } from "@/features/admin/useCursorList";
import type { DepartmentRef } from "@/features/auth/api";
import { useMe } from "@/features/auth/session";
import { fieldErrors } from "@/lib/api";
import { usePageTitle } from "@/lib/usePageTitle";

import { formatDay } from "./format";
import {
  createSection,
  createSubject,
  createTerm,
  fetchSections,
  fetchSettings,
  fetchSubjects,
  fetchTerms,
  makeTermCurrent,
  setupKeys,
  updateSettings,
  type Term,
} from "./setupApi";

const VIEWS = [
  { id: "sections", label: "Sections" },
  { id: "subjects", label: "Subjects" },
  { id: "terms", label: "Terms" },
] as const;
type View = (typeof VIEWS)[number]["id"];

/**
 * Manage → Academics (Design.md §5 screen 17, "Academic setup"): sections of a term, subjects and
 * terms. College admins set up every department and the terms; department admins their own
 * departments' subjects and sections (ACADEMIC-001…003). Section rows open the section's setup.
 */
export function AcademicsAdminTab() {
  usePageTitle("Academics · Manage");
  const [params, setParams] = useSearchParams();
  const view: View = VIEWS.find((v) => v.id === params.get("view"))?.id ?? "sections";
  const viewId = useId();
  return (
    <div className="space-y-4">
      <div className="max-w-xs space-y-1.5">
        <label htmlFor={viewId} className="block text-sm font-medium">
          Show
        </label>
        <Select id={viewId} value={view} onChange={(e) => setParams(e.target.value === "sections" ? {} : { view: e.target.value }, { replace: true })}>
          {VIEWS.map((v) => (
            <option key={v.id} value={v.id}>
              {v.label}
            </option>
          ))}
        </Select>
      </div>
      {view === "sections" && <SectionsView />}
      {view === "subjects" && <SubjectsView />}
      {view === "terms" && <TermsView />}
    </div>
  );
}

/** Departments whose subjects the account manages: every active one for college admins. */
function useManagedDepartments(): { departments: DepartmentRef[]; loading: boolean } {
  const me = useMe();
  const collegeAdmin = me.capabilities.includes("manage_college");
  const all = useQuery({ queryKey: ["setup", "departments"], queryFn: ({ signal }) => fetchDepartments(false, signal), enabled: collegeAdmin });
  if (collegeAdmin) return { departments: all.data?.items ?? [], loading: all.isPending };
  return { departments: me.roles.filter((r) => r.role === "DEPARTMENT_ADMIN" && r.department).map((r) => r.department!), loading: false };
}

function AddForm({ label, onSubmit, pending, error, children }: { label: string; onSubmit: () => void; pending: boolean; error: unknown; children: ReactNode }) {
  const general = error && Object.keys(fieldErrors(error)).length === 0 ? errorText(error) : null;
  return (
    <form
      aria-label={label}
      noValidate
      onSubmit={(e: FormEvent) => {
        e.preventDefault();
        onSubmit();
      }}
      className="space-y-3 rounded-sm border border-border p-4"
    >
      <div className="grid gap-3 sm:grid-cols-[repeat(auto-fit,minmax(10rem,1fr))]">{children}</div>
      {general && <Callout tone="danger">{general}</Callout>}
      <SubmitButton size="sm" pending={pending} pendingLabel="Adding…">
        {label}
      </SubmitButton>
    </form>
  );
}

function Field({ label, error, children }: { label: string; error?: string | undefined; children: (id: string, describedBy: string | undefined) => ReactNode }) {
  const id = useId();
  return (
    <div className="space-y-1.5">
      <label htmlFor={id} className="block text-sm font-medium">
        {label}
      </label>
      {children(id, error ? `${id}-error` : undefined)}
      {error && (
        <p id={`${id}-error`} className="text-sm text-danger-fg">
          {error}
        </p>
      )}
    </div>
  );
}

// --- sections ------------------------------------------------------------------------------

function SectionsView() {
  const terms = useQuery({ queryKey: setupKeys.terms, queryFn: ({ signal }) => fetchTerms(signal) });
  const [picked, setPicked] = useState<string | null>(null);
  const termId = useId();
  if (terms.isPending) return <ListLoading label="Loading terms" />;
  if (terms.isError) return <ErrorState title="Couldn't load the terms." error={terms.error} onRetry={() => void terms.refetch()} retrying={terms.isFetching} />;
  if (terms.data.items.length === 0) {
    return (
      <EmptyState Icon={CalendarRange} title="No terms yet.">
        A college admin adds the first term under Terms.
      </EmptyState>
    );
  }
  const term = terms.data.items.find((t) => t.id === picked) ?? terms.data.items.find((t) => t.is_current) ?? terms.data.items[0]!;
  return (
    <div className="space-y-4">
      <div className="max-w-xs space-y-1.5">
        <label htmlFor={termId} className="block text-sm font-medium">
          Term
        </label>
        <Select id={termId} value={term.id} onChange={(e) => setPicked(e.target.value)}>
          {terms.data.items.map((t) => (
            <option key={t.id} value={t.id}>
              {t.name}
              {t.is_current ? " (current)" : ""}
            </option>
          ))}
        </Select>
      </div>
      <NewSection term={term} />
      <SectionList term={term} />
    </div>
  );
}

function NewSection({ term }: { term: Term }) {
  const queryClient = useQueryClient();
  const subjects = useCursorList(setupKeys.subjects, fetchSubjects);
  const [subjectId, setSubjectId] = useState("");
  const [name, setName] = useState("");
  const create = useMutation({
    mutationFn: () => createSection({ term_id: term.id, subject_id: subjectId, name: name.trim() }),
    onSuccess: async () => {
      setName("");
      await queryClient.invalidateQueries({ queryKey: setupKeys.sections(term.id) });
    },
  });
  const errors = fieldErrors(create.error);
  if (subjects.items.length === 0) return null;
  return (
    <AddForm label="Add section" pending={create.isPending} error={create.error} onSubmit={() => create.mutate()}>
      <Field label="Subject" error={errors.subject_id}>
        {(id, d) => (
          <Select id={id} value={subjectId} onChange={(e) => setSubjectId(e.target.value)} aria-describedby={d}>
            <option value="">Choose a subject</option>
            {subjects.items.map((s) => (
              <option key={s.id} value={s.id}>
                {s.code} {s.name}
              </option>
            ))}
          </Select>
        )}
      </Field>
      <Field label="Section name" error={errors.name}>
        {(id, d) => <Input id={id} value={name} maxLength={40} placeholder="A" onChange={(e) => setName(e.target.value)} aria-describedby={d} aria-invalid={Boolean(errors.name) || undefined} />}
      </Field>
    </AddForm>
  );
}

function SectionList({ term }: { term: Term }) {
  const { query, items } = useCursorList(setupKeys.sections(term.id), (cursor, signal) => fetchSections(term.id, cursor, signal));
  if (query.isPending) return <ListLoading label="Loading sections" />;
  if (query.isError) return <ErrorState title="Couldn't load the sections." error={query.error} onRetry={() => void query.refetch()} retrying={query.isFetching} />;
  if (items.length === 0) return <EmptyState Icon={Layers} title="No sections in this term yet." />;
  return (
    <>
      <DataTable
        caption="Sections"
        rows={items}
        rowKey={(s) => s.id}
        columns={[
          {
            header: "Section",
            cell: (s) => (
              <Link to={`/manage/academics/sections/${s.id}`} className="font-medium text-primary hover:underline">
                <span className="font-mono">{s.subject.code}</span> {s.subject.name} · {s.name}
              </Link>
            ),
          },
          { header: "Department", cell: (s) => s.department.code },
          { header: "Faculty", cell: (s) => (s.instructors.length ? s.instructors.map((i) => i.display_name).join(", ") : <span className="text-warning-fg">None assigned</span>) },
          { header: "Students", cell: (s) => <span className="font-mono">{s.enrollment_count}</span> },
        ]}
      />
      <LoadMore shown={items.length} hasMore={query.hasNextPage} loading={query.isFetchingNextPage} onLoad={() => void query.fetchNextPage()} />
    </>
  );
}

// --- subjects ------------------------------------------------------------------------------

function SubjectsView() {
  const queryClient = useQueryClient();
  const { departments } = useManagedDepartments();
  const { query, items } = useCursorList(setupKeys.subjects, fetchSubjects);
  const [departmentId, setDepartmentId] = useState("");
  const [code, setCode] = useState("");
  const [name, setName] = useState("");
  const create = useMutation({
    mutationFn: () => createSubject({ department_id: departmentId || departments[0]?.id || "", code: code.trim(), name: name.trim() }),
    onSuccess: async () => {
      setCode("");
      setName("");
      await queryClient.invalidateQueries({ queryKey: setupKeys.subjects });
    },
  });
  const errors = fieldErrors(create.error);
  return (
    <div className="space-y-4">
      {departments.length > 0 && (
        <AddForm label="Add subject" pending={create.isPending} error={create.error} onSubmit={() => create.mutate()}>
          <Field label="Department" error={errors.department_id}>
            {(id, d) => (
              <Select id={id} value={departmentId || departments[0]!.id} onChange={(e) => setDepartmentId(e.target.value)} aria-describedby={d}>
                {departments.map((dep) => (
                  <option key={dep.id} value={dep.id}>
                    {dep.code} {dep.name}
                  </option>
                ))}
              </Select>
            )}
          </Field>
          <Field label="Code" error={errors.code}>
            {(id, d) => <Input id={id} value={code} className="font-mono" placeholder="CS301" onChange={(e) => setCode(e.target.value)} aria-describedby={d} aria-invalid={Boolean(errors.code) || undefined} />}
          </Field>
          <Field label="Name" error={errors.name}>
            {(id, d) => <Input id={id} value={name} placeholder="Compilers" onChange={(e) => setName(e.target.value)} aria-describedby={d} aria-invalid={Boolean(errors.name) || undefined} />}
          </Field>
        </AddForm>
      )}
      {query.isPending ? (
        <ListLoading label="Loading subjects" />
      ) : query.isError ? (
        <ErrorState title="Couldn't load the subjects." error={query.error} onRetry={() => void query.refetch()} retrying={query.isFetching} />
      ) : items.length === 0 ? (
        <EmptyState Icon={BookOpen} title="No subjects yet." />
      ) : (
        <>
          <DataTable
            caption="Subjects"
            rows={items}
            rowKey={(s) => s.id}
            columns={[
              { header: "Code", cell: (s) => <span className="font-mono">{s.code}</span> },
              { header: "Name", cell: (s) => s.name },
              { header: "Department", cell: (s) => s.department.code },
            ]}
          />
          <LoadMore shown={items.length} hasMore={query.hasNextPage} loading={query.isFetchingNextPage} onLoad={() => void query.fetchNextPage()} />
        </>
      )}
    </div>
  );
}

// --- terms ---------------------------------------------------------------------------------

function TermsView() {
  const me = useMe();
  const queryClient = useQueryClient();
  const collegeAdmin = me.capabilities.includes("manage_college");
  const terms = useQuery({ queryKey: setupKeys.terms, queryFn: ({ signal }) => fetchTerms(signal) });
  const [form, setForm] = useState({ name: "", starts_on: "", ends_on: "", is_current: false });
  const done = () => queryClient.invalidateQueries({ queryKey: ["setup"] });
  const create = useMutation({
    mutationFn: () => createTerm({ ...form, name: form.name.trim() }),
    onSuccess: async () => {
      setForm({ name: "", starts_on: "", ends_on: "", is_current: false });
      await done();
    },
  });
  const current = useMutation({ mutationFn: makeTermCurrent, onSuccess: done });
  const errors = fieldErrors(create.error);
  return (
    <div className="space-y-4">
      {collegeAdmin && <EditWindowSetting />}
      {collegeAdmin ? (
        <AddForm label="Add term" pending={create.isPending} error={create.error} onSubmit={() => create.mutate()}>
          <Field label="Name" error={errors.name}>
            {(id, d) => <Input id={id} value={form.name} placeholder="2026-27 Odd semester" onChange={(e) => setForm({ ...form, name: e.target.value })} aria-describedby={d} aria-invalid={Boolean(errors.name) || undefined} />}
          </Field>
          <Field label="Starts" error={errors.starts_on}>
            {(id, d) => <Input id={id} type="date" value={form.starts_on} onChange={(e) => setForm({ ...form, starts_on: e.target.value })} aria-describedby={d} />}
          </Field>
          <Field label="Ends" error={errors.ends_on ?? errors[""]}>
            {(id, d) => <Input id={id} type="date" value={form.ends_on} onChange={(e) => setForm({ ...form, ends_on: e.target.value })} aria-describedby={d} />}
          </Field>
          <label className="flex min-h-11 items-center gap-2 self-end text-sm">
            <input type="checkbox" checked={form.is_current} onChange={(e) => setForm({ ...form, is_current: e.target.checked })} className="size-4 accent-primary" />
            Current term
          </label>
        </AddForm>
      ) : (
        <Callout tone="info">College admins add terms and choose the current one.</Callout>
      )}
      {current.isError && <Callout tone="danger">{errorText(current.error)}</Callout>}
      {terms.isPending ? (
        <ListLoading label="Loading terms" />
      ) : terms.isError ? (
        <ErrorState title="Couldn't load the terms." error={terms.error} onRetry={() => void terms.refetch()} retrying={terms.isFetching} />
      ) : terms.data.items.length === 0 ? (
        <EmptyState Icon={CalendarRange} title="No terms yet." />
      ) : (
        <DataTable
          caption="Terms"
          rows={terms.data.items}
          rowKey={(t) => t.id}
          columns={[
            { header: "Term", cell: (t) => <span className="font-medium">{t.name}</span> },
            { header: "Dates", cell: (t) => `${formatDay(t.starts_on)} – ${formatDay(t.ends_on)}` },
            {
              header: "Status",
              cell: (t) =>
                t.is_current ? (
                  <span className="rounded-sm bg-primary-subtle px-1.5 py-0.5 text-xs font-medium text-primary">Current</span>
                ) : collegeAdmin ? (
                  <Button size="sm" variant="secondary" disabled={current.isPending} onClick={() => current.mutate(t.id)}>
                    Make current
                  </Button>
                ) : null,
            },
          ]}
        />
      )}
    </div>
  );
}

/** ACADEMIC-006, P-5: the college's attendance edit window (1 hour to 30 days). */
function EditWindowSetting() {
  const queryClient = useQueryClient();
  const id = useId();
  const settings = useQuery({ queryKey: setupKeys.settings, queryFn: ({ signal }) => fetchSettings(signal) });
  const [hours, setHours] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const save = useMutation({
    mutationFn: (value: number) => updateSettings(value),
    onSuccess: (next) => {
      queryClient.setQueryData(setupKeys.settings, next);
      setHours(null);
      setSaved(true);
    },
  });
  if (settings.isPending) return <ListLoading label="Loading settings" />;
  if (settings.isError) return <ErrorState title="Couldn't load the college settings." error={settings.error} onRetry={() => void settings.refetch()} retrying={settings.isFetching} />;
  const value = hours ?? String(settings.data.attendance_edit_window_hours);
  const number = Number(value);
  const valid = /^\d+$/.test(value) && number >= 1 && number <= 720;
  return (
    <form
      aria-label="Attendance edit window"
      noValidate
      onSubmit={(e: FormEvent) => {
        e.preventDefault();
        if (valid) save.mutate(number);
      }}
      className="space-y-3 rounded-sm border border-border p-4"
    >
      <div className="max-w-xs space-y-1.5">
        <label htmlFor={id} className="block text-sm font-medium">
          Attendance edit window (hours)
        </label>
        <Input
          id={id}
          inputMode="numeric"
          className="font-mono"
          value={value}
          onChange={(e) => {
            setSaved(false);
            setHours(e.target.value);
          }}
          aria-invalid={!valid || undefined}
          aria-describedby={`${id}-help`}
        />
        <p id={`${id}-help`} className={valid ? "text-sm text-muted" : "text-sm text-danger-fg"}>
          {valid ? "How long faculty can change a session after recording it. After that, a department admin corrects it with a reason." : "Use a whole number from 1 to 720 (30 days)."}
        </p>
      </div>
      {save.isError && <Callout tone="danger">{errorText(save.error)}</Callout>}
      <div className="flex items-center gap-3">
        <SubmitButton size="sm" pending={save.isPending} pendingLabel="Saving…" disabled={!valid || hours === null}>
          Save
        </SubmitButton>
        {saved && <span className="text-sm text-success-fg">Saved. It applies to every session, including ones already recorded.</span>}
      </div>
    </form>
  );
}
