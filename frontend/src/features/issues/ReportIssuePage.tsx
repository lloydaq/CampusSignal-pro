import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, CircleAlert } from "lucide-react";
import { useId, useState } from "react";
import { useForm, useWatch } from "react-hook-form";
import { Link, useNavigate } from "react-router";

import { Callout } from "@/components/Callout";
import { FormField } from "@/components/FormField";
import { SubmitButton } from "@/components/SubmitButton";
import { Textarea } from "@/components/ui/textarea";
import { applyServerError } from "@/features/auth/serverErrors";
import { usePageTitle } from "@/lib/usePageTitle";
import { cn } from "@/lib/utils";
import { zodResolver } from "@/lib/zodResolver";

import { createIssue, type Issue } from "./api";
import type { IssueFlash } from "./IssuePage";
import { CATEGORIES, issueKeys } from "./labels";
import { LOCATION_MAX, ROOM_MAX, TEXT_MAX, TITLE_MAX, reportSchema, type ReportFormValues } from "./schemas";

const FIELDS = ["category", "title", "location", "room", "description"] as const;

/** Design.md §5 screen 13: report a problem quickly (ISSUE-001). */
export function ReportIssuePage() {
  usePageTitle("Report an issue");
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [formError, setFormError] = useState<string | null>(null);
  const ids = { category: useId(), description: useId() };
  const form = useForm<ReportFormValues>({
    resolver: zodResolver(reportSchema),
    defaultValues: { title: "", location: "", room: "", description: "" },
  });
  const { errors } = form.formState;
  const [title, description] = useWatch({ control: form.control, name: ["title", "description"] });

  const report = useMutation({
    mutationFn: (values: ReportFormValues) =>
      createIssue({ ...values, room: values.room || null }),
    onSuccess: async (issue: Issue) => {
      queryClient.setQueryData(issueKeys.one(issue.id), issue);
      await queryClient.invalidateQueries({ queryKey: [...issueKeys.all, "list"] });
      await navigate(`/issues/${issue.id}`, { state: { flash: "Issue reported. You'll be notified each time its status changes." } satisfies IssueFlash });
    },
    onError: (error) => setFormError(applyServerError(error, form.setError, FIELDS, "You've reported 5 issues in the last 24 hours.")),
  });

  const submit = form.handleSubmit((values) => {
    setFormError(null);
    report.mutate(values);
  });

  return (
    <div className="mx-auto max-w-reading space-y-6">
      <Link to="/issues" className="inline-flex items-center gap-1.5 text-sm text-muted hover:text-fg">
        <ArrowLeft aria-hidden="true" strokeWidth={1.5} className="size-4" />
        My issues
      </Link>
      <div className="space-y-2">
        <h1 className="text-2xl font-semibold text-fg sm:text-3xl">Report an issue</h1>
        <p className="text-sm text-muted">
          Issue coordinators see new reports first and may assign them to a member of staff. Only you, the coordinators and whoever handles it can see your report. You'll get a
          notification each time its status changes.
        </p>
      </div>
      {formError && <Callout tone="danger">{formError}</Callout>}
      <form noValidate onSubmit={(event) => void submit(event)} className="space-y-5">
        <fieldset aria-describedby={errors.category ? `${ids.category}-error` : undefined} className="space-y-2">
          <legend className="text-sm font-medium text-fg">Category</legend>
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
            {CATEGORIES.map(({ value, label, Icon }) => (
              <label
                key={value}
                className="flex min-h-11 cursor-pointer items-center gap-3 rounded-sm border border-border bg-surface px-3 py-2 text-sm text-fg hover:bg-surface-sunken has-checked:border-primary has-checked:bg-primary-subtle"
              >
                <input type="radio" value={value} className="size-4 shrink-0 accent-primary" {...form.register("category")} />
                <Icon aria-hidden="true" strokeWidth={1.5} className="size-4 shrink-0 text-muted" />
                {label}
              </label>
            ))}
          </div>
          {errors.category && (
            <p id={`${ids.category}-error`} className="flex items-start gap-1.5 text-sm text-danger-fg">
              <CircleAlert aria-hidden="true" strokeWidth={1.5} className="mt-0.5 size-4 shrink-0" />
              {errors.category.message}
            </p>
          )}
        </fieldset>

        <FormField
          id="issue-title"
          label="What's wrong?"
          autoComplete="off"
          maxLength={TITLE_MAX}
          placeholder="Projector doesn't turn on"
          helper={`${title.length} / ${TITLE_MAX}`}
          error={errors.title?.message}
          {...form.register("title")}
        />
        <div className="grid gap-4 sm:grid-cols-[2fr_1fr]">
          <FormField
            id="issue-location"
            label="Where is it?"
            autoComplete="off"
            maxLength={LOCATION_MAX}
            placeholder="Main block, second floor"
            error={errors.location?.message}
            {...form.register("location")}
          />
          <FormField
            id="issue-room"
            label="Room (optional)"
            autoComplete="off"
            maxLength={ROOM_MAX}
            placeholder="204"
            error={errors.room?.message}
            {...form.register("room")}
          />
        </div>
        <div className="space-y-1.5">
          <label htmlFor={ids.description} className="block text-sm font-medium text-fg">
            Description
          </label>
          <Textarea
            id={ids.description}
            rows={6}
            maxLength={TEXT_MAX}
            aria-invalid={errors.description ? true : undefined}
            aria-describedby={`${ids.description}-help`}
            {...form.register("description")}
          />
          <p id={`${ids.description}-help`} className={cn("flex items-start gap-1.5 text-sm", errors.description ? "text-danger-fg" : "text-muted")}>
            {errors.description && <CircleAlert aria-hidden="true" strokeWidth={1.5} className="mt-0.5 size-4 shrink-0" />}
            {errors.description?.message ?? `What happens, since when, and anything that helps find it. ${description.length.toLocaleString("en-IN")} / 3,000`}
          </p>
        </div>
        <SubmitButton pending={report.isPending} pendingLabel="Reporting…">
          Report issue
        </SubmitButton>
      </form>
    </div>
  );
}
