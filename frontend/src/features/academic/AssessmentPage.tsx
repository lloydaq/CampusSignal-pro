import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ChevronLeft } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Link, useBlocker, useParams } from "react-router";

import { Callout } from "@/components/Callout";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import { ErrorState } from "@/components/ErrorState";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ListLoading } from "@/features/admin/list";
import { errorText } from "@/features/admin/labels";
import { formatDateTime } from "@/lib/datetime";
import { useCollegeTimezone } from "@/features/admin/tabs";
import { ApiError, fieldErrors } from "@/lib/api";
import { usePageTitle } from "@/lib/usePageTitle";
import { cn } from "@/lib/utils";

import { formatDay, formatScore } from "./format";
import { fetchResults, KIND_LABEL, publishAssessment, saveResults, teachingKeys, type AssessmentResults, type ResultRow, type ScoreEntry } from "./teachingApi";

interface Cell {
  score: string;
  absent: boolean;
}

const cellOf = (row: ResultRow): Cell => ({ score: row.score === null ? "" : formatScore(row.score), absent: row.absent });
const SCORE = /^\d{1,4}(\.\d{1,2})?$/;

/** Why a cell can't be saved, or null. */
function cellProblem(cell: Cell, max: number): string | null {
  if (cell.absent || cell.score.trim() === "") return null;
  if (!SCORE.test(cell.score.trim())) return "Use a number with at most two decimals.";
  if (Number(cell.score) > max) return `The most is ${formatScore(max)}.`;
  return null;
}

/**
 * Design.md §5 screen 16, an assessment: the score grid (score or Absent per student), then
 * Publish, which tells every enrolled student (ACADEMIC-008, 009). Once published, changes need
 * a reason and mark the result "Revised". Readers (department and college admins) see it read-only;
 * department admins may publish.
 */
export function AssessmentPage() {
  const { assessmentId = "" } = useParams();
  const query = useQuery({ queryKey: teachingKeys.results(assessmentId), queryFn: ({ signal }) => fetchResults(assessmentId, signal) });
  const [notice, setNotice] = useState<string | null>(null);
  usePageTitle(query.data ? `${query.data.assessment.name} · Assessment` : "Assessment");
  if (query.isPending) return <ListLoading label="Loading the scores" />;
  if (query.isError) return <ErrorState title="Couldn't load this assessment." error={query.error} onRetry={() => void query.refetch()} retrying={query.isFetching} />;
  return <Grid key={query.data.assessment.version} data={query.data} notice={notice} onNotice={setNotice} />;
}

function Grid({ data, notice, onNotice }: { data: AssessmentResults; notice: string | null; onNotice: (text: string | null) => void }) {
  const queryClient = useQueryClient();
  const timeZone = useCollegeTimezone();
  const { assessment, rows } = data;
  const initial = useMemo(() => Object.fromEntries(rows.map((r) => [r.enrollment_id, cellOf(r)])) as Record<string, Cell>, [rows]);
  const [cells, setCells] = useState(initial);
  const [confirming, setConfirming] = useState<"publish" | "revise" | null>(null);
  const editable = assessment.actions.enter_scores;
  const published = assessment.published_at !== null;
  const changed = rows.filter((r) => cells[r.enrollment_id]!.score.trim() !== initial[r.enrollment_id]!.score || cells[r.enrollment_id]!.absent !== initial[r.enrollment_id]!.absent);
  const problems = Object.fromEntries(rows.map((r) => [r.enrollment_id, cellProblem(cells[r.enrollment_id]!, assessment.max_score)]));
  const invalid = Object.values(problems).some(Boolean);
  const clearedAfterPublish = published && changed.some((r) => !cells[r.enrollment_id]!.absent && cells[r.enrollment_id]!.score.trim() === "");
  const entered = rows.filter((r) => initial[r.enrollment_id]!.absent || initial[r.enrollment_id]!.score !== "").length;

  const refresh = (next: AssessmentResults) => {
    queryClient.setQueryData(teachingKeys.results(next.assessment.id), next);
    void queryClient.invalidateQueries({ queryKey: teachingKeys.assessments(next.assessment.section_id) });
  };
  const save = useMutation({
    mutationFn: (reason?: string) =>
      saveResults(assessment.id, {
        version: assessment.version,
        results: changed.map((r): ScoreEntry => {
          const cell = cells[r.enrollment_id]!;
          return { enrollment_id: r.enrollment_id, score: cell.absent || cell.score.trim() === "" ? null : cell.score.trim(), absent: cell.absent };
        }),
        ...(reason ? { reason } : {}),
      }),
    onSuccess: (next, reason) => {
      setConfirming(null);
      onNotice(reason ? "Changes saved. The students have been told their results were revised." : "Scores saved.");
      refresh(next);
    },
  });
  const publish = useMutation({
    mutationFn: () => publishAssessment(assessment.id, assessment.version),
    onSuccess: async () => {
      setConfirming(null);
      onNotice(`Published. ${assessment.counts.enrolled === 1 ? "The student has" : `All ${assessment.counts.enrolled} students have`} been told.`);
      await queryClient.invalidateQueries({ queryKey: teachingKeys.results(assessment.id) });
      await queryClient.invalidateQueries({ queryKey: teachingKeys.assessments(assessment.section_id) });
    },
  });
  const dirty = editable && changed.length > 0;
  const blocker = useBlocker(({ currentLocation, nextLocation }) => dirty && !save.isPending && currentLocation.pathname !== nextLocation.pathname);
  useEffect(() => {
    if (!dirty) return;
    const warn = (event: BeforeUnloadEvent) => event.preventDefault();
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);

  const serverFields = save.error ? fieldErrors(save.error) : {};
  const conflict = save.error instanceof ApiError && save.error.code === "version_conflict";
  const onSave = () => (published ? setConfirming("revise") : save.mutate(undefined));

  return (
    <div className="space-y-6">
      <Link to={`/teaching/sections/${assessment.section_id}?tab=assessments`} className="inline-flex min-h-8 items-center gap-1 text-sm font-medium text-primary hover:underline pointer-coarse:min-h-11">
        <ChevronLeft aria-hidden="true" strokeWidth={1.5} className="size-4" />
        Assessments
      </Link>
      <div className="space-y-1">
        <div className="flex flex-wrap items-center gap-3">
          <h1 className="text-2xl font-semibold text-fg sm:text-3xl">{assessment.name}</h1>
          <span className={cn("rounded-sm px-1.5 py-0.5 text-xs font-medium", published ? "bg-success-subtle text-success-fg" : "border border-border-strong text-muted")}>{published ? "Published" : "Draft"}</span>
        </div>
        <p className="text-sm text-muted">
          {KIND_LABEL[assessment.kind]} · {formatDay(assessment.held_on)} · out of <span className="font-mono">{formatScore(assessment.max_score)}</span>
          {published && assessment.published_by && ` · published ${formatDateTime(assessment.published_at!, timeZone)} by ${assessment.published_by.display_name}`}
        </p>
      </div>
      {notice && <Callout tone="success">{notice}</Callout>}
      {!published && <Callout tone="info">Students can't see these scores until you publish them.</Callout>}
      {published && editable && <Callout tone="info">Changing a published score needs a reason. The student is told their result was revised.</Callout>}
      {!editable && <Callout tone="info">Only the section's faculty enter scores. {assessment.actions.publish ? "You can publish them once every student has one." : "You can view them here."}</Callout>}

      {rows.length === 0 ? (
        <Callout tone="info">No students are enrolled in this section yet.</Callout>
      ) : (
        <div className="overflow-x-auto rounded-sm border border-border">
          <table className="w-full text-left text-sm">
            <caption className="sr-only">Scores</caption>
            <thead className="bg-surface-sunken">
              <tr>
                <th scope="col" className="px-4 py-2 font-medium text-muted">
                  Student
                </th>
                <th scope="col" className="px-3 py-2 font-medium text-muted">
                  Score (out of {formatScore(assessment.max_score)})
                </th>
                <th scope="col" className="px-4 py-2 font-medium text-muted">
                  Absent
                </th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r, i) => {
                const cell = cells[r.enrollment_id]!;
                const problem = problems[r.enrollment_id] ?? serverFields[`results.${changed.indexOf(r)}.score`];
                const set = (next: Partial<Cell>) => setCells((c) => ({ ...c, [r.enrollment_id]: { ...cell, ...next } }));
                return (
                  <tr key={r.enrollment_id} className="border-t border-border">
                    <th scope="row" className="px-4 py-2 text-left font-medium text-fg">
                      <span className="flex flex-wrap items-center gap-2">
                        {r.display_name}
                        {r.revised && <span className="rounded-sm border border-border-strong px-1.5 py-0.5 text-xs font-medium text-muted">Revised</span>}
                      </span>
                    </th>
                    <td className="px-3 py-2">
                      {editable ? (
                        <>
                          <Input
                            aria-label={`Score for ${r.display_name}`}
                            inputMode="decimal"
                            autoComplete="off"
                            value={cell.absent ? "" : cell.score}
                            disabled={cell.absent}
                            onChange={(e) => {
                              onNotice(null);
                              set({ score: e.target.value });
                            }}
                            aria-invalid={Boolean(problem) || undefined}
                            aria-describedby={problem ? `score-error-${i}` : undefined}
                            className="w-28 font-mono"
                          />
                          {problem && (
                            <p id={`score-error-${i}`} className="mt-1 text-xs text-danger-fg">
                              {problem}
                            </p>
                          )}
                        </>
                      ) : (
                        <span className="font-mono">{r.absent ? <span className="font-sans text-muted">Absent</span> : r.score === null ? <span className="text-muted">—</span> : formatScore(r.score)}</span>
                      )}
                    </td>
                    <td className="px-4 py-2">
                      {editable ? (
                        <input type="checkbox" aria-label={`${r.display_name} was absent`} checked={cell.absent} onChange={(e) => set({ absent: e.target.checked })} className="size-5 accent-primary" />
                      ) : (
                        <span className="text-muted">{r.absent ? "Yes" : ""}</span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {clearedAfterPublish && <Callout tone="danger">A published result needs a score or Absent; it can't be left empty.</Callout>}
      {save.isError && !serverFields.reason && (
        <Callout tone="danger">
          {errorText(save.error)}
          {conflict && (
            <Button size="sm" variant="secondary" className="mt-2" onClick={() => void queryClient.invalidateQueries({ queryKey: teachingKeys.results(assessment.id) })}>
              Reload
            </Button>
          )}
        </Callout>
      )}
      {publish.isError && <Callout tone="danger">{errorText(publish.error)}</Callout>}

      {(editable || assessment.actions.publish) && rows.length > 0 && (
        <div className="sticky bottom-18 z-10 -mx-4 flex flex-wrap items-center justify-between gap-3 border-t border-border bg-surface px-4 py-3 sm:mx-0 sm:rounded-sm sm:border lg:bottom-0">
          <p className="text-sm text-muted tabular-nums" aria-live="polite">
            <span className="font-mono font-medium text-fg">{entered}</span> of <span className="font-mono">{rows.length}</span> entered
            {changed.length > 0 && ` · ${changed.length === 1 ? "1 unsaved change" : `${changed.length} unsaved changes`}`}
          </p>
          <div className="flex flex-wrap gap-3">
            {editable && (
              <Button variant={published || !assessment.actions.publish ? "primary" : "secondary"} onClick={onSave} disabled={changed.length === 0 || invalid || clearedAfterPublish || save.isPending}>
                {save.isPending && confirming === null ? "Saving…" : "Save scores"}
              </Button>
            )}
            {assessment.actions.publish && (
              <Button onClick={() => setConfirming("publish")} disabled={changed.length > 0 || entered < rows.length || publish.isPending}>
                Publish
              </Button>
            )}
          </div>
        </div>
      )}
      {assessment.actions.publish && entered < rows.length && <p className="text-xs text-muted">Publishing needs a score or Absent for every student.</p>}

      {confirming === "publish" && (
        <ConfirmDialog
          title="Publish these results?"
          description={`${rows.length === 1 ? "The student" : `All ${rows.length} students`} will see their scores and be notified. After this, a score changes only with a reason.`}
          confirmLabel="Publish results"
          pendingLabel="Publishing…"
          destructive={false}
          pending={publish.isPending}
          error={publish.isError ? errorText(publish.error) : null}
          onConfirm={() => publish.mutate()}
          onCancel={() => {
            setConfirming(null);
            publish.reset();
          }}
        />
      )}
      {confirming === "revise" && (
        <ConfirmDialog
          title={`Change ${changed.length === 1 ? "1 published result" : `${changed.length} published results`}?`}
          description="Each student is told their result was revised. Your reason goes in the audit log."
          reasonLabel="Reason"
          confirmLabel="Save changes"
          pendingLabel="Saving…"
          destructive={false}
          pending={save.isPending}
          error={save.isError ? errorText(save.error) : null}
          onConfirm={(reason) => save.mutate(reason)}
          onCancel={() => {
            setConfirming(null);
            save.reset();
          }}
        />
      )}
      {blocker.state === "blocked" && (
        <ConfirmDialog
          title="Leave without saving?"
          description="The scores you've changed here will be lost."
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
