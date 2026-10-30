import { useMutation, useQuery } from "@tanstack/react-query";
import { ArrowLeft, Check } from "lucide-react";
import { useId, useState, type ReactNode } from "react";
import { useForm } from "react-hook-form";
import { Link, useLocation, useParams } from "react-router";

import { Callout } from "@/components/Callout";
import { ErrorState } from "@/components/ErrorState";
import { SubmitButton } from "@/components/SubmitButton";
import { Textarea } from "@/components/ui/textarea";
import { ListLoading } from "@/features/admin/list";
import { useCollegeTimezone } from "@/features/admin/tabs";
import { applyServerError } from "@/features/auth/serverErrors";
import { ApiError } from "@/lib/api";
import { formatDateTime } from "@/lib/datetime";
import { usePageTitle } from "@/lib/usePageTitle";
import { cn } from "@/lib/utils";
import { zodResolver } from "@/lib/zodResolver";

import { commentOnIssue, fetchIssue, type Issue, type IssueStatus, type IssueUpdate } from "./api";
import { CATEGORY_LABEL, REOPEN_DAYS, STATUS_LABEL, issueKeys } from "./labels";
import { TEXT_MAX, commentSchema, type CommentFormValues } from "./schemas";
import { useIssueSaved } from "./cache";
import { AssignControl, StatusActions } from "./IssueActions";
import { StatusBadge } from "./StatusBadge";

export interface IssueFlash {
  flash?: string;
}

const STEPS: IssueStatus[] = ["SUBMITTED", "ACKNOWLEDGED", "IN_PROGRESS", "RESOLVED"];

/** Design.md §5 screen 14, detail: "Is it being fixed?" (ISSUE-002, 005, 006). */
export function IssuePage() {
  const { issueId = "" } = useParams();
  const issue = useQuery({ queryKey: issueKeys.one(issueId), queryFn: ({ signal }) => fetchIssue(issueId, signal) });
  usePageTitle(issue.data?.title ?? "Issue");

  return (
    <article className="mx-auto max-w-reading space-y-6">
      <Link to="/issues" className="inline-flex items-center gap-1.5 text-sm text-muted hover:text-fg">
        <ArrowLeft aria-hidden="true" strokeWidth={1.5} className="size-4" />
        All issues
      </Link>
      {issue.isPending ? (
        <ListLoading label="Loading the issue" />
      ) : issue.isError ? (
        issue.error instanceof ApiError && issue.error.status === 404 ? (
          <Callout tone="info" title="This issue isn't available">
            <p>Only its reporter, the issue coordinators and whoever handles it can see an issue.</p>
          </Callout>
        ) : (
          <ErrorState title="Couldn't load the issue." error={issue.error} onRetry={() => void issue.refetch()} retrying={issue.isFetching} />
        )
      ) : (
        <IssueView issue={issue.data} />
      )}
    </article>
  );
}

function IssueView({ issue }: { issue: Issue }) {
  const timeZone = useCollegeTimezone();
  const location = useLocation();
  const flash = (location.state as IssueFlash | null)?.flash;
  const reopen = issue.status === "RESOLVED" || issue.status === "REJECTED" ? issue.actions.transitions.find((t) => t.to_status === "ACKNOWLEDGED") : undefined;

  return (
    <>
      {flash && <Callout tone="success">{flash}</Callout>}
      <header className="space-y-3">
        <div className="flex flex-wrap items-center gap-1.5">
          <StatusBadge status={issue.status} />
          <span className="text-xs text-subtle">{CATEGORY_LABEL[issue.category]}</span>
        </div>
        <h1 className="text-2xl font-semibold text-fg sm:text-3xl">{issue.title}</h1>
        <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-sm sm:gap-x-6">
          <Fact label="Where">
            {issue.location}
            {issue.room && <> · Room {issue.room}</>}
          </Fact>
          <Fact label="Reported">
            {issue.reporter_name} · <time dateTime={issue.created_at}>{formatDateTime(issue.created_at, timeZone)}</time>
          </Fact>
          <Fact label="Handled by">{issue.assignee_name ?? <span className="text-muted">Not assigned yet</span>}</Fact>
        </dl>
      </header>

      <Progress issue={issue} />

      {issue.duplicate_of && (
        <Callout tone="info" title="Closed as a duplicate">
          <p>Someone reported the same problem earlier, and that report is the one being handled.</p>
          <p className="flex flex-wrap items-center gap-1.5">
            Its status: <StatusBadge status={issue.duplicate_of.status} />
            {issue.duplicate_of.resolved_at && (
              <>
                {" "}
                resolved <time dateTime={issue.duplicate_of.resolved_at}>{formatDateTime(issue.duplicate_of.resolved_at, timeZone)}</time>
              </>
            )}
          </p>
          {issue.duplicate_of.id && (
            <Link to={`/issues/${issue.duplicate_of.id}`} className="underline underline-offset-2">
              Open the original
            </Link>
          )}
        </Callout>
      )}
      {issue.status === "RESOLVED" && issue.resolved_at && (
        <Callout tone="success" title={`Resolved ${formatDateTime(issue.resolved_at, timeZone)}`}>
          {reopen && <p>Still not fixed? You can reopen it within {REOPEN_DAYS} days of being resolved.</p>}
        </Callout>
      )}

      <section aria-label="Description" className="text-base whitespace-pre-line text-fg">
        {issue.description}
      </section>

      <StatusActions issue={issue} />
      <AssignControl issue={issue} />
      <Timeline updates={issue.updates} timeZone={timeZone} />
      {issue.actions.comment && <CommentForm issue={issue} />}
    </>
  );
}

function Fact({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="contents">
      <dt className="text-muted">{label}</dt>
      <dd className="text-fg">{children}</dd>
    </div>
  );
}

/** Design.md §5 screen 14: Submitted → Acknowledged → In progress → Resolved; Rejected ends the line where it happened. */
function Progress({ issue }: { issue: Issue }) {
  const rejected = issue.status === "REJECTED";
  const rejectedFrom = rejected ? ([...issue.updates].reverse().find((u) => u.to_status === "REJECTED")?.from_status ?? "SUBMITTED") : null;
  const reached = STEPS.indexOf(rejectedFrom ?? issue.status);
  const steps = rejected ? [...STEPS.slice(0, reached + 1), "REJECTED" as const] : STEPS;

  return (
    <nav aria-label="Progress">
      <ol className="flex flex-col gap-1 text-sm sm:flex-row sm:flex-wrap sm:items-center sm:gap-x-1 sm:gap-y-2">
        {steps.map((step, index) => {
          const current = step === issue.status;
          const done = !current && index <= reached;
          return (
            <li key={step} aria-current={current ? "step" : undefined} className="flex items-center gap-1">
              {index > 0 && <span aria-hidden="true" className={cn("mx-1 hidden h-px w-6 sm:block", done || current ? "bg-border-strong" : "bg-border")} />}
              <span
                className={cn(
                  "inline-flex items-center gap-1 rounded-sm px-1.5 py-0.5",
                  current ? (step === "REJECTED" ? "bg-danger-subtle font-semibold text-danger-fg" : "bg-primary-subtle font-semibold text-primary") : done ? "text-fg" : "text-subtle",
                )}
              >
                {done && <Check aria-hidden="true" strokeWidth={2} className="size-3.5" />}
                {STATUS_LABEL[step]}
                {done && <span className="sr-only"> (done)</span>}
              </span>
            </li>
          );
        })}
      </ol>
    </nav>
  );
}

function describe(update: IssueUpdate): string {
  switch (update.kind) {
    case "CREATED":
      return "Reported the issue";
    case "ASSIGNMENT":
      return update.assignee_name ? `Assigned it to ${update.assignee_name}` : "Removed the assignee";
    case "COMMENT":
      return "Commented";
    case "STATUS": {
      const from = update.from_status;
      // The new status follows as a badge.
      if (update.to_status === "ACKNOWLEDGED" && (from === "RESOLVED" || from === "REJECTED")) return "Reopened it:";
      return "Moved it to";
    }
  }
}

/** ISSUE-005: every change, in order. Internal entries reach only the handling side and say so. */
function Timeline({ updates, timeZone }: { updates: IssueUpdate[]; timeZone: string }) {
  const id = useId();
  return (
    <section aria-labelledby={id} className="space-y-3 border-t border-border pt-6">
      <h2 id={id} className="text-lg font-semibold text-fg">
        Updates
      </h2>
      <ol className="space-y-4">
        {updates.map((u) => (
          <li key={u.id} className={cn("space-y-1 border-l-2 pl-3", u.is_internal ? "border-warning" : "border-border")}>
            <p className="flex flex-wrap items-center gap-x-1.5 text-sm">
              <span className="font-medium text-fg">{u.actor_name ?? "CampusSignal"}</span>
              <span className="text-muted">{describe(u)}</span>
              {u.kind === "STATUS" && u.to_status && <StatusBadge status={u.to_status} />}
              {u.is_internal && <span className="inline-flex rounded-sm bg-warning-subtle px-1.5 py-0.5 text-xs font-semibold text-warning-fg">Internal</span>}
            </p>
            <p className="text-xs text-subtle">
              <time dateTime={u.created_at}>{formatDateTime(u.created_at, timeZone)}</time>
            </p>
            {u.body && <p className="text-sm whitespace-pre-line text-fg">{u.body}</p>}
          </li>
        ))}
      </ol>
    </section>
  );
}

/** ISSUE-005: the reporter comments publicly; the handling side may mark a comment internal. */
function CommentForm({ issue }: { issue: Issue }) {
  const saved = useIssueSaved(issue.id);
  const [formError, setFormError] = useState<string | null>(null);
  const [internal, setInternal] = useState(false);
  const ids = { body: useId(), internal: useId() };
  const form = useForm<CommentFormValues>({ resolver: zodResolver(commentSchema), defaultValues: { body: "" } });
  const { errors } = form.formState;
  const comment = useMutation({
    mutationFn: (values: CommentFormValues) => commentOnIssue(issue.id, { body: values.body, is_internal: internal }),
    onSuccess: async (updated) => {
      form.reset();
      setInternal(false);
      await saved(updated);
    },
    onError: (error) => setFormError(applyServerError(error, form.setError, ["body"])),
  });
  const submit = form.handleSubmit((values) => {
    setFormError(null);
    comment.mutate(values);
  });

  return (
    <form noValidate onSubmit={(event) => void submit(event)} aria-label="Add a comment" className="space-y-3">
      {formError && <Callout tone="danger">{formError}</Callout>}
      <div className="space-y-1.5">
        <label htmlFor={ids.body} className="block text-sm font-medium text-fg">
          Comment
        </label>
        <Textarea
          id={ids.body}
          rows={3}
          maxLength={TEXT_MAX}
          aria-invalid={errors.body ? true : undefined}
          aria-describedby={errors.body ? `${ids.body}-error` : undefined}
          {...form.register("body")}
        />
        {errors.body && (
          <p id={`${ids.body}-error`} className="text-sm text-danger-fg">
            {errors.body.message}
          </p>
        )}
      </div>
      {issue.actions.comment_internal && (
        <label htmlFor={ids.internal} className="flex min-h-11 items-center gap-2 text-sm text-fg">
          <input id={ids.internal} type="checkbox" checked={internal} onChange={(e) => setInternal(e.target.checked)} className="size-4 accent-primary" />
          Internal: hidden from the reporter
        </label>
      )}
      <SubmitButton pending={comment.isPending} pendingLabel="Posting…" variant="secondary">
        Post comment
      </SubmitButton>
    </form>
  );
}
