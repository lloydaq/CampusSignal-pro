import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useId, useState } from "react";
import { useForm, useWatch } from "react-hook-form";
import { Link, Navigate, useNavigate, useParams } from "react-router";

import { Callout } from "@/components/Callout";
import { ErrorState } from "@/components/ErrorState";
import { FormField } from "@/components/FormField";
import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { fetchDepartments, type Department } from "@/features/admin/api";
import { ListLoading } from "@/features/admin/list";
import { useCollegeTimezone } from "@/features/admin/tabs";
import { applyServerError } from "@/features/auth/serverErrors";
import { useMe } from "@/features/auth/session";
import { ApiError } from "@/lib/api";
import { isoToZonedInput, zonedInputToIso } from "@/lib/datetime";
import { usePageTitle } from "@/lib/usePageTitle";
import { cn } from "@/lib/utils";
import { zodResolver } from "@/lib/zodResolver";

import { createNotice, fetchNotice, updateNotice, type Category, type Notice, type NoticeInput } from "./api";
import { CATEGORY_LABEL, PRIORITY_LABEL, canPublish, noticeKeys, publishing } from "./labels";
import { LazyNoticeBody as NoticeBody } from "./LazyNoticeBody";
import type { NoticeFlash } from "./NoticePage";
import { BODY_MAX, TITLE_MAX, noticeSchema, type NoticeFormValues } from "./schemas";

const FIELDS = ["title", "body", "category", "priority", "department_id", "expires"] as const;

/** New notice. Only college and department admins compose (NOTICE-002). */
export function NewNoticePage() {
  usePageTitle("New notice");
  const me = useMe();
  if (!canPublish(me)) return <Navigate to="/notices" replace />;
  return <NoticeForm notice={null} />;
}

export function EditNoticePage() {
  const { noticeId = "" } = useParams();
  const notice = useQuery({ queryKey: noticeKeys.one(noticeId), queryFn: ({ signal }) => fetchNotice(noticeId, signal) });
  usePageTitle("Edit notice");
  if (notice.isPending) return <ListLoading label="Loading the notice" />;
  if (notice.isError) {
    return notice.error instanceof ApiError && notice.error.status === 404 ? (
      <Callout tone="info" title="This notice isn't available" />
    ) : (
      <ErrorState title="Couldn't load the notice." error={notice.error} onRetry={() => void notice.refetch()} retrying={notice.isFetching} />
    );
  }
  if (!notice.data.can_manage || notice.data.status === "WITHDRAWN") {
    return (
      <Callout tone="info" title="You can't edit this notice">
        <Link to={`/notices/${notice.data.id}`} className="underline underline-offset-2">
          Back to the notice
        </Link>
      </Callout>
    );
  }
  return <NoticeForm notice={notice.data} />;
}

function NoticeForm({ notice }: { notice: Notice | null }) {
  const me = useMe();
  const timeZone = useCollegeTimezone();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const rights = publishing(me);
  const [formError, setFormError] = useState<string | null>(null);
  const [conflict, setConflict] = useState(false);
  const [tab, setTab] = useState<"write" | "preview">("write");
  const ids = { category: useId(), priority: useId(), department: useId(), body: useId(), expires: useId() };
  const departments = useQuery({ queryKey: ["departments", "list"], queryFn: ({ signal }) => fetchDepartments(false, signal), enabled: notice === null });
  const choosable: Department[] = (departments.data?.items ?? []).filter((d) => rights.college || rights.departmentIds.includes(d.id));

  const form = useForm<NoticeFormValues>({
    resolver: zodResolver(noticeSchema),
    defaultValues: {
      title: notice?.title ?? "",
      body: notice?.body ?? "",
      category: notice?.category ?? "GENERAL",
      priority: notice?.priority ?? "NORMAL",
      scope: notice?.scope ?? (rights.college ? "COLLEGE" : "DEPARTMENT"),
      department_id: notice?.department?.id ?? (rights.college ? "" : (rights.departmentIds[0] ?? "")),
      expires: notice?.expires_at ? isoToZonedInput(notice.expires_at, timeZone) : "",
    },
  });
  const { errors } = form.formState;
  const [scope, body, title, priority] = useWatch({ control: form.control, name: ["scope", "body", "title", "priority"] });

  const finish = async (saved: Notice, flash: string) => {
    queryClient.setQueryData(noticeKeys.one(saved.id), saved);
    await queryClient.invalidateQueries({ queryKey: [...noticeKeys.all, "list"] });
    await navigate(`/notices/${saved.id}`, { state: { flash } satisfies NoticeFlash });
  };
  const onError = (error: unknown) => {
    if (error instanceof ApiError && error.code === "version_conflict") {
      setConflict(true);
      return;
    }
    // The API names the expiry `expires_at`; the form field is `expires`.
    const renamed =
      error instanceof ApiError && Array.isArray(error.details)
        ? new ApiError(
            error.status,
            error.code,
            error.message,
            (error.details as { field?: string }[]).map((d) => (d.field === "expires_at" ? { ...d, field: "expires" } : d)),
            error.requestId,
            error.retryAfterSeconds,
          )
        : error;
    setFormError(applyServerError(renamed, form.setError, FIELDS));
  };

  const input = (values: NoticeFormValues): NoticeInput => ({
    title: values.title,
    body: values.body,
    category: values.category,
    priority: values.priority,
    expires_at: values.expires ? zonedInputToIso(values.expires, timeZone) : null,
  });

  const create = useMutation({
    mutationFn: ({ values, publish }: { values: NoticeFormValues; publish: boolean }) =>
      createNotice({ ...input(values), scope: values.scope, ...(values.scope === "DEPARTMENT" ? { department_id: values.department_id } : {}), publish }),
    onSuccess: (saved, { publish }) => finish(saved, publish ? "Notice published." : "Draft saved."),
    onError,
  });
  const save = useMutation({
    mutationFn: (values: NoticeFormValues) => {
      if (!notice) throw new Error("No notice to update");
      const next = input(values);
      const changes: Partial<NoticeInput> = {};
      if (next.title !== notice.title) changes.title = next.title;
      if (next.body !== notice.body) changes.body = next.body;
      if (next.category !== notice.category) changes.category = next.category;
      if (next.priority !== notice.priority) changes.priority = next.priority;
      if (next.expires_at !== (notice.expires_at ? new Date(notice.expires_at).toISOString() : null)) changes.expires_at = next.expires_at;
      if (Object.keys(changes).length === 0) return Promise.resolve(notice);
      return updateNotice(notice.id, { ...changes, version: notice.version });
    },
    onSuccess: (saved) => finish(saved, "Changes saved."),
    onError,
  });
  const pending = create.isPending || save.isPending;

  const submit = (publish: boolean) =>
    form.handleSubmit((values) => {
      setFormError(null);
      if (notice) save.mutate(values);
      else create.mutate({ values, publish });
    });

  return (
    <div className="mx-auto max-w-reading space-y-6">
      <h1 className="text-2xl font-semibold text-fg sm:text-3xl">{notice ? "Edit notice" : "New notice"}</h1>
      {conflict && (
        <Callout tone="danger" title="Someone else changed this notice">
          <p>Reload it to see their changes, then make yours again.</p>
          <Button size="sm" variant="secondary" onClick={() => window.location.reload()}>
            Reload
          </Button>
        </Callout>
      )}
      {formError && <Callout tone="danger">{formError}</Callout>}
      {notice?.status === "PUBLISHED" && (
        <Callout tone="info">
          <p>This notice is published. Readers will see that it was updated; nobody is notified again.</p>
        </Callout>
      )}
      <form noValidate onSubmit={(event) => void submit(false)(event)} className="space-y-5">
        <FormField id="notice-title" label="Title" autoComplete="off" maxLength={TITLE_MAX} helper={`${title.length} / ${TITLE_MAX}`} error={errors.title?.message} {...form.register("title")} />

        <div className="space-y-1.5">
          <div className="flex flex-wrap items-end justify-between gap-2">
            <label htmlFor={ids.body} className="block text-sm font-medium text-fg">
              Notice text
            </label>
            <div role="group" aria-label="Editor view" className="flex rounded-sm border border-border">
              {(["write", "preview"] as const).map((t) => (
                <button
                  key={t}
                  type="button"
                  aria-pressed={tab === t}
                  onClick={() => setTab(t)}
                  className={cn("h-8 px-3 text-sm font-medium first:rounded-l-sm last:rounded-r-sm pointer-coarse:min-h-11", tab === t ? "bg-primary-subtle text-primary" : "text-muted hover:text-fg")}
                >
                  {t === "write" ? "Write" : "Preview"}
                </button>
              ))}
            </div>
          </div>
          <div className={tab === "write" ? "" : "hidden"}>
            <Textarea
              id={ids.body}
              rows={12}
              maxLength={BODY_MAX}
              aria-invalid={errors.body ? true : undefined}
              aria-describedby={`${ids.body}-help`}
              {...form.register("body")}
            />
          </div>
          {tab === "preview" && (
            <div aria-label="Preview" className="min-h-48 rounded-sm border border-border bg-surface p-4">
              {body.trim() ? <NoticeBody markdown={body} /> : <p className="text-sm text-muted">Nothing to preview yet.</p>}
            </div>
          )}
          <p id={`${ids.body}-help`} className={cn("text-sm", errors.body ? "text-danger-fg" : "text-muted")}>
            {errors.body?.message ?? `**bold**, *italic*, lists with - or 1., and [links](https://…). ${body.length.toLocaleString("en-IN")} / 10,000`}
          </p>
        </div>

        <div className="grid gap-4 sm:grid-cols-2">
          <div className="space-y-1.5">
            <label htmlFor={ids.category} className="block text-sm font-medium">
              Category
            </label>
            <Select id={ids.category} {...form.register("category")}>
              {(Object.keys(CATEGORY_LABEL) as Category[]).map((c) => (
                <option key={c} value={c}>
                  {CATEGORY_LABEL[c]}
                </option>
              ))}
            </Select>
          </div>
          <div className="space-y-1.5">
            <label htmlFor={ids.priority} className="block text-sm font-medium">
              Priority
            </label>
            <Select id={ids.priority} aria-describedby={`${ids.priority}-help`} {...form.register("priority")}>
              {(["NORMAL", "HIGH", "URGENT"] as const).map((p) => (
                <option key={p} value={p}>
                  {PRIORITY_LABEL[p]}
                </option>
              ))}
            </Select>
            <p id={`${ids.priority}-help`} className="text-sm text-muted">
              {priority === "NORMAL" ? "No notifications." : priority === "URGENT" ? "Pinned at the top, and everyone in the audience is notified." : "Everyone in the audience is notified."}
            </p>
          </div>
        </div>

        {notice ? (
          <p className="text-sm text-muted">
            Audience: <span className="font-medium text-fg">{notice.department ? notice.department.name : "Whole college"}</span> (fixed once a notice exists)
          </p>
        ) : (
          <fieldset className="space-y-3">
            <legend className="text-sm font-medium text-fg">Audience</legend>
            <div className="flex flex-wrap gap-4">
              {rights.college && (
                <label className="flex min-h-11 items-center gap-2 text-sm">
                  <input type="radio" value="COLLEGE" className="size-4 accent-primary" {...form.register("scope")} />
                  Whole college
                </label>
              )}
              <label className="flex min-h-11 items-center gap-2 text-sm">
                <input type="radio" value="DEPARTMENT" className="size-4 accent-primary" {...form.register("scope")} />
                One department
              </label>
            </div>
            {scope === "DEPARTMENT" && (
              <div className="space-y-1.5">
                <label htmlFor={ids.department} className="block text-sm font-medium">
                  Department
                </label>
                <Select id={ids.department} aria-invalid={errors.department_id ? true : undefined} {...form.register("department_id")}>
                  {rights.college && <option value="">Choose a department</option>}
                  {choosable.map((d) => (
                    <option key={d.id} value={d.id}>
                      {d.name}
                    </option>
                  ))}
                </Select>
                {errors.department_id && <p className="text-sm text-danger-fg">{errors.department_id.message}</p>}
              </div>
            )}
          </fieldset>
        )}

        <div className="space-y-1.5">
          <label htmlFor={ids.expires} className="block text-sm font-medium">
            Expires (optional)
          </label>
          <input
            id={ids.expires}
            type="datetime-local"
            aria-invalid={errors.expires ? true : undefined}
            aria-describedby={`${ids.expires}-help`}
            className="h-10 w-full max-w-64 rounded-sm border border-border-strong bg-surface px-3 text-base text-fg aria-invalid:border-danger pointer-coarse:min-h-11"
            {...form.register("expires")}
          />
          <p id={`${ids.expires}-help`} className={cn("text-sm", errors.expires ? "text-danger-fg" : "text-muted")}>
            {errors.expires?.message ?? `In ${timeZone} time. After it, the notice moves to Past notices.`}
          </p>
        </div>

        <div className="flex flex-wrap gap-3 border-t border-border pt-5">
          {notice ? (
            <Button type="submit" disabled={pending}>
              {save.isPending ? "Saving…" : "Save changes"}
            </Button>
          ) : (
            <>
              <Button type="button" onClick={() => void submit(true)()} disabled={pending}>
                {create.isPending && create.variables?.publish ? "Publishing…" : "Publish"}
              </Button>
              <Button type="submit" variant="secondary" disabled={pending}>
                {create.isPending && !create.variables?.publish ? "Saving…" : "Save draft"}
              </Button>
            </>
          )}
          <Link to={notice ? `/notices/${notice.id}` : "/notices"} className="inline-flex h-10 items-center px-3 text-sm font-medium text-muted hover:text-fg pointer-coarse:min-h-11">
            Cancel
          </Link>
        </div>
      </form>
    </div>
  );
}
