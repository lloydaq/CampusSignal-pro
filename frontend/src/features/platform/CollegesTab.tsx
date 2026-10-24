import { useMutation, useQueryClient } from "@tanstack/react-query";
import { School } from "lucide-react";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { Link } from "react-router";

import { DataTable } from "@/components/DataTable";
import { Callout } from "@/components/Callout";
import { EmptyState } from "@/components/EmptyState";
import { ErrorState } from "@/components/ErrorState";
import { FormField } from "@/components/FormField";
import { SubmitButton } from "@/components/SubmitButton";
import { ListLoading, LoadMore } from "@/features/admin/list";
import { useCursorList } from "@/features/admin/useCursorList";
import { applyServerError } from "@/features/auth/serverErrors";
import { formatDateTime } from "@/lib/datetime";
import { usePageTitle } from "@/lib/usePageTitle";
import { zodResolver } from "@/lib/zodResolver";

import { createCollege, fetchColleges } from "./api";
import { collegesKey, STATUS_LABEL } from "./labels";
import { collegeSchema, domainsOf, type CollegeValues } from "./schemas";

/** Colleges as tenants: name, slug, status, member count (ADMIN-001). No college content. */
export function CollegesTab() {
  usePageTitle("Colleges · Platform");
  const { query, items } = useCursorList(collegesKey, fetchColleges);
  return (
    <div className="space-y-8">
      <NewCollege />
      <section aria-labelledby="colleges-heading" className="space-y-3">
        <h2 id="colleges-heading" className="text-lg font-semibold">
          Colleges
        </h2>
        {query.isPending ? (
          <ListLoading label="Loading colleges" />
        ) : query.isError ? (
          <ErrorState title="Couldn't load the colleges." error={query.error} onRetry={() => void query.refetch()} retrying={query.isFetching} />
        ) : items.length === 0 ? (
          <EmptyState Icon={School} title="No colleges yet.">
            Create one above, then invite its first admin.
          </EmptyState>
        ) : (
          <>
            <DataTable
              caption="Colleges"
              rows={items}
              rowKey={(c) => c.id}
              columns={[
                {
                  header: "Name",
                  cell: (c) => (
                    <div className="space-y-0.5">
                      <Link to={c.id} className="font-medium text-primary underline underline-offset-2">
                        {c.name}
                      </Link>
                      {c.is_demo && <p className="text-xs font-medium text-warning-fg">Demo data</p>}
                    </div>
                  ),
                },
                { header: "Slug", cell: (c) => <span className="font-mono">{c.slug}</span> },
                { header: "Status", cell: (c) => STATUS_LABEL[c.status] },
                { header: "Active members", cell: (c) => c.active_member_count },
                { header: "Created (UTC)", cell: (c) => formatDateTime(c.created_at, "UTC") },
              ]}
            />
            <LoadMore shown={items.length} hasMore={query.hasNextPage} loading={query.isFetchingNextPage} onLoad={() => void query.fetchNextPage()} />
          </>
        )}
      </section>
    </div>
  );
}

function NewCollege() {
  const queryClient = useQueryClient();
  const [formError, setFormError] = useState<string | null>(null);
  const [created, setCreated] = useState<{ id: string; name: string } | null>(null);
  const form = useForm<CollegeValues>({
    resolver: zodResolver(collegeSchema),
    defaultValues: { name: "", slug: "", timezone: "Asia/Kolkata", email_domains: "", is_demo: false },
  });
  const { errors } = form.formState;
  const create = useMutation({
    mutationFn: (values: CollegeValues) => createCollege({ ...values, email_domains: domainsOf(values.email_domains) }),
    onSuccess: async (college) => {
      setCreated({ id: college.id, name: college.name });
      form.reset();
      await queryClient.invalidateQueries({ queryKey: collegesKey });
    },
    onError: (error) => setFormError(applyServerError(error, form.setError, ["name", "slug", "timezone", "email_domains"])),
  });
  const onSubmit = form.handleSubmit((values) => {
    setFormError(null);
    setCreated(null);
    create.mutate(values);
  });
  return (
    <section aria-labelledby="new-college" className="space-y-4">
      <h2 id="new-college" className="text-lg font-semibold">
        Create a college
      </h2>
      <form noValidate onSubmit={(event) => void onSubmit(event)} className="space-y-4">
        {formError && <Callout tone="danger">{formError}</Callout>}
        {created && (
          <Callout tone="success">
            {created.name} was created. <Link to={created.id} className="underline underline-offset-2">Invite its first admin</Link>.
          </Callout>
        )}
        <div className="grid gap-4 sm:grid-cols-2">
          <FormField id="college-name" label="Name" autoComplete="off" error={errors.name?.message} {...form.register("name")} />
          <FormField id="college-slug" label="Slug" autoComplete="off" spellCheck={false} className="font-mono" helper="Permanent. Lower-case letters, digits and hyphens." error={errors.slug?.message} {...form.register("slug")} />
          <FormField id="college-timezone" label="Time zone" autoComplete="off" spellCheck={false} helper="An IANA name such as Asia/Kolkata." error={errors.timezone?.message} {...form.register("timezone")} />
          <FormField id="college-domains" label="Email domains (optional)" autoComplete="off" spellCheck={false} helper="Separated by commas." error={errors.email_domains?.message} {...form.register("email_domains")} />
        </div>
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" className="size-4 accent-primary" {...form.register("is_demo")} />
          This is a demo college (every screen is labelled "Demo data")
        </label>
        <SubmitButton pending={create.isPending} pendingLabel="Creating…">
          Create college
        </SubmitButton>
      </form>
    </section>
  );
}
