import { zodResolver } from "@/lib/zodResolver";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ChevronLeft, ClipboardCheck, FileSpreadsheet, Users } from "lucide-react";
import { useId, useState } from "react";
import { useForm } from "react-hook-form";
import { Link, useNavigate, useParams, useSearchParams } from "react-router";
import { z } from "zod";

import { Callout } from "@/components/Callout";
import { EmptyState } from "@/components/EmptyState";
import { ErrorState } from "@/components/ErrorState";
import { FormField } from "@/components/FormField";
import { SubmitButton } from "@/components/SubmitButton";
import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/select";
import { ListLoading, LoadMore } from "@/features/admin/list";
import { useCursorList } from "@/features/admin/useCursorList";
import { applyServerError } from "@/features/auth/serverErrors";
import { usePageTitle } from "@/lib/usePageTitle";
import { cn } from "@/lib/utils";

import { formatDay, formatScore } from "./format";
import { useTeaches } from "./useTeaches";
import {
  createAssessment,
  fetchAllEnrollments,
  fetchAssessments,
  fetchSection,
  fetchSessions,
  KIND_LABEL,
  teachingKeys,
  type AssessmentKind,
  type Section,
} from "./teachingApi";

/** A link styled as the primary button (Design.md §6 Button). */
const PRIMARY_LINK =
  "inline-flex h-10 items-center justify-center gap-2 rounded-sm bg-primary px-4 text-sm font-medium text-on-primary hover:bg-primary-hover pointer-coarse:min-h-11";

const TABS = [
  { id: "attendance", label: "Attendance" },
  { id: "assessments", label: "Assessments" },
  { id: "students", label: "Students" },
] as const;
type Tab = (typeof TABS)[number]["id"];

/**
 * Design.md §5 screen 16, the section page: tabs Attendance (sessions + Take attendance),
 * Assessments (list, create) and Students (roster). Department and college admins see the same
 * read-only views (ACADEMIC-010); `back` says where the section list is.
 */
export function SectionPage({ back = { to: "/teaching", label: "Your sections" } }: { back?: { to: string; label: string } }) {
  const { sectionId = "" } = useParams();
  const [params] = useSearchParams();
  const tab: Tab = TABS.find((t) => t.id === params.get("tab"))?.id ?? "attendance";
  const query = useQuery({ queryKey: teachingKeys.section(sectionId), queryFn: ({ signal }) => fetchSection(sectionId, signal) });
  const teaches = useTeaches(query.data);
  usePageTitle(query.data ? `${query.data.subject.code} ${query.data.name}` : "Section");

  const backLink = (
    <Link to={back.to} className="inline-flex min-h-8 items-center gap-1 text-sm font-medium text-primary hover:underline pointer-coarse:min-h-11">
      <ChevronLeft aria-hidden="true" strokeWidth={1.5} className="size-4" />
      {back.label}
    </Link>
  );
  if (query.isPending) return <ListLoading label="Loading the section" />;
  if (query.isError) {
    return (
      <div className="space-y-4">
        {backLink}
        <ErrorState title="Couldn't load this section." error={query.error} onRetry={() => void query.refetch()} retrying={query.isFetching} />
      </div>
    );
  }
  const section = query.data;
  return (
    <div className="space-y-6">
      {backLink}
      <div className="space-y-1">
        <h1 className="text-2xl font-semibold text-fg sm:text-3xl">
          <span className="font-mono">{section.subject.code}</span> {section.subject.name}
        </h1>
        <p className="text-sm text-muted">
          Section {section.name} · {section.term.name} · {section.department.code}
          {section.instructors.length > 0 && ` · ${section.instructors.map((i) => i.display_name).join(", ")}`}
        </p>
      </div>
      <nav aria-label="Section" className="-mx-4 overflow-x-auto border-b border-border px-4 sm:mx-0 sm:px-0">
        <ul className="flex gap-1">
          {TABS.map((t) => (
            <li key={t.id}>
              <Link
                to={t.id === "attendance" ? "?" : `?tab=${t.id}`}
                replace
                aria-current={tab === t.id ? "page" : undefined}
                className={cn(
                  "relative flex h-10 items-center px-3 text-sm font-medium whitespace-nowrap pointer-coarse:min-h-11",
                  tab === t.id ? "text-primary after:absolute after:inset-x-2 after:bottom-0 after:h-0.75 after:rounded-sm after:bg-accent" : "text-muted hover:text-fg",
                )}
              >
                {t.label}
              </Link>
            </li>
          ))}
        </ul>
      </nav>
      {tab === "attendance" && <SessionsTab section={section} teaches={teaches} />}
      {tab === "assessments" && <AssessmentsTab section={section} teaches={teaches} />}
      {tab === "students" && <StudentsTab section={section} />}
    </div>
  );
}

function SessionsTab({ section, teaches }: { section: Section; teaches: boolean }) {
  const { query, items } = useCursorList(teachingKeys.sessions(section.id), (cursor, signal) => fetchSessions(section.id, cursor, signal));
  return (
    <div className="space-y-4">
      {teaches && (
        <Link to={`/teaching/sections/${section.id}/attendance/new`} className={PRIMARY_LINK}>
          Take attendance
        </Link>
      )}
      {query.isPending ? (
        <ListLoading label="Loading attendance sessions" />
      ) : query.isError ? (
        <ErrorState title="Couldn't load the attendance sessions." error={query.error} onRetry={() => void query.refetch()} retrying={query.isFetching} />
      ) : items.length === 0 ? (
        <EmptyState Icon={ClipboardCheck} title="No attendance recorded yet." />
      ) : (
        <>
          <ul aria-label="Attendance sessions" className="divide-y divide-border rounded-sm border border-border">
            {items.map((s) => (
              <li key={s.id}>
                <Link to={`/teaching/sessions/${s.id}`} className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1 px-4 py-3 hover:bg-surface-sunken">
                  <span className="font-medium text-fg">
                    {formatDay(s.held_on)} <span className="font-normal text-muted">· Period {s.slot}</span>
                  </span>
                  <span className="text-sm text-muted tabular-nums">
                    {s.counts.present} present · {s.counts.absent} absent · {s.counts.excused} excused
                  </span>
                </Link>
              </li>
            ))}
          </ul>
          <LoadMore shown={items.length} hasMore={query.hasNextPage} loading={query.isFetchingNextPage} onLoad={() => void query.fetchNextPage()} />
        </>
      )}
    </div>
  );
}

const assessmentSchema = z.object({
  name: z.string().trim().min(1, "Give it a name.").max(80, "Use 80 characters or fewer."),
  kind: z.enum(["QUIZ", "ASSIGNMENT", "LAB", "MIDTERM", "ENDTERM", "OTHER"]),
  max_score: z
    .string()
    .trim()
    .regex(/^\d{1,4}(\.\d{1,2})?$/, "A number up to 9999.99, two decimals at most.")
    .refine((v) => Number(v) > 0, "The maximum must be more than 0."),
  held_on: z.string().min(1, "Pick the date."),
});
type AssessmentForm = z.infer<typeof assessmentSchema>;

function NewAssessment({ section, onCancel }: { section: Section; onCancel: () => void }) {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const kindId = useId();
  const form = useForm<AssessmentForm>({ resolver: zodResolver(assessmentSchema), defaultValues: { name: "", kind: "QUIZ", max_score: "", held_on: "" } });
  const create = useMutation({
    mutationFn: (values: AssessmentForm) => createAssessment(section.id, values),
    onSuccess: async (created) => {
      await queryClient.invalidateQueries({ queryKey: teachingKeys.assessments(section.id) });
      void navigate(`/teaching/assessments/${created.id}`);
    },
    onError: (error) => applyServerError(error, form.setError, ["name", "kind", "max_score", "held_on"]),
  });
  const { errors } = form.formState;
  return (
    <form aria-label="New assessment" noValidate onSubmit={(event) => void form.handleSubmit((v) => create.mutate(v))(event)} className="space-y-4 rounded-sm border border-border p-4">
      <div className="grid gap-4 sm:grid-cols-2">
        <FormField id="assessment-name" label="Name" error={errors.name?.message} {...form.register("name")} />
        <div className="space-y-1.5">
          <label htmlFor={kindId} className="block text-sm font-medium">
            Kind
          </label>
          <Select id={kindId} {...form.register("kind")}>
            {(Object.keys(KIND_LABEL) as AssessmentKind[]).map((k) => (
              <option key={k} value={k}>
                {KIND_LABEL[k]}
              </option>
            ))}
          </Select>
        </div>
        <FormField id="assessment-max" label="Maximum score" inputMode="decimal" className="font-mono" error={errors.max_score?.message} {...form.register("max_score")} />
        <FormField id="assessment-date" label="Date" type="date" error={errors.held_on?.message} {...form.register("held_on")} />
      </div>
      {errors.root && <Callout tone="danger">{errors.root.message}</Callout>}
      <div className="flex gap-3">
        <SubmitButton pending={create.isPending} pendingLabel="Creating…">
          Create assessment
        </SubmitButton>
        <Button type="button" variant="ghost" onClick={onCancel}>
          Cancel
        </Button>
      </div>
    </form>
  );
}

function AssessmentsTab({ section, teaches }: { section: Section; teaches: boolean }) {
  const [creating, setCreating] = useState(false);
  const { query, items } = useCursorList(teachingKeys.assessments(section.id), (cursor, signal) => fetchAssessments(section.id, cursor, signal));
  return (
    <div className="space-y-4">
      {teaches && (creating ? <NewAssessment section={section} onCancel={() => setCreating(false)} /> : <Button onClick={() => setCreating(true)}>New assessment</Button>)}
      {query.isPending ? (
        <ListLoading label="Loading assessments" />
      ) : query.isError ? (
        <ErrorState title="Couldn't load the assessments." error={query.error} onRetry={() => void query.refetch()} retrying={query.isFetching} />
      ) : items.length === 0 ? (
        <EmptyState Icon={FileSpreadsheet} title="No assessments yet." />
      ) : (
        <>
          <ul aria-label="Assessments" className="divide-y divide-border rounded-sm border border-border">
            {items.map((a) => (
              <li key={a.id}>
                <Link to={`/teaching/assessments/${a.id}`} className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1 px-4 py-3 hover:bg-surface-sunken">
                  <span className="min-w-0">
                    <span className="flex flex-wrap items-center gap-2 font-medium text-fg">
                      {a.name}
                      <span
                        className={cn(
                          "rounded-sm px-1.5 py-0.5 text-xs font-medium",
                          a.published_at ? "bg-success-subtle text-success-fg" : "border border-border-strong text-muted",
                        )}
                      >
                        {a.published_at ? "Published" : "Draft"}
                      </span>
                    </span>
                    <span className="block text-sm text-muted">
                      {KIND_LABEL[a.kind]} · {formatDay(a.held_on)} · out of <span className="font-mono">{formatScore(a.max_score)}</span>
                    </span>
                  </span>
                  <span className="text-sm text-muted tabular-nums">
                    {a.counts.entered} of {a.counts.enrolled} entered
                  </span>
                </Link>
              </li>
            ))}
          </ul>
          <LoadMore shown={items.length} hasMore={query.hasNextPage} loading={query.isFetchingNextPage} onLoad={() => void query.fetchNextPage()} />
        </>
      )}
    </div>
  );
}

function StudentsTab({ section }: { section: Section }) {
  const query = useQuery({ queryKey: teachingKeys.enrollments(section.id), queryFn: ({ signal }) => fetchAllEnrollments(section.id, signal) });
  if (query.isPending) return <ListLoading label="Loading students" />;
  if (query.isError) return <ErrorState title="Couldn't load the students." error={query.error} onRetry={() => void query.refetch()} retrying={query.isFetching} />;
  if (query.data.length === 0) return <EmptyState Icon={Users} title="No students are enrolled yet." />;
  const rolls = query.data.some((e) => e.roll_number);
  return (
    <div className="space-y-2">
      <p className="text-sm text-muted tabular-nums">{query.data.length === 1 ? "1 student" : `${query.data.length} students`}</p>
      <ul aria-label="Students" className="divide-y divide-border rounded-sm border border-border">
        {query.data.map((e) => (
          <li key={e.id} className="flex items-center justify-between gap-4 px-4 py-3 text-sm">
            <span className="font-medium text-fg">{e.display_name}</span>
            <span className="text-muted">
              {rolls && <span className="font-mono">{e.roll_number ?? "—"}</span>}
              {e.department && <span className="ml-3">{e.department.code}</span>}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}
