import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Building2 } from "lucide-react";
import { useState } from "react";
import { useForm } from "react-hook-form";

import { Callout } from "@/components/Callout";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import { DataTable } from "@/components/DataTable";
import { EmptyState } from "@/components/EmptyState";
import { ErrorState } from "@/components/ErrorState";
import { FormField } from "@/components/FormField";
import { SubmitButton } from "@/components/SubmitButton";
import { Button } from "@/components/ui/button";
import { applyServerError } from "@/features/auth/serverErrors";
import { usePageTitle } from "@/lib/usePageTitle";
import { zodResolver } from "@/lib/zodResolver";

import { createDepartment, fetchDepartments, updateDepartment, type Department } from "./api";
import { manageKeys } from "./keys";
import { errorText } from "./labels";
import { ListLoading } from "./list";
import { departmentEditSchema, departmentSchema, type DepartmentEditValues, type DepartmentValues } from "./schemas";

/** Departments (DEPT-001/002). Codes are permanent because roster files refer to them. */
export function DepartmentsTab() {
  usePageTitle("Departments · Manage");
  const [showArchived, setShowArchived] = useState(false);
  const [editing, setEditing] = useState<string | null>(null);
  const [archiving, setArchiving] = useState<Department | null>(null);
  const queryClient = useQueryClient();
  const departments = useQuery({ queryKey: [...manageKeys.departments, showArchived], queryFn: ({ signal }) => fetchDepartments(showArchived, signal) });
  const changed = () => queryClient.invalidateQueries({ queryKey: manageKeys.departments });
  const archive = useMutation({
    mutationFn: ({ id, archived }: { id: string; archived: boolean }) => updateDepartment(id, { archived }),
    onSuccess: async () => {
      setArchiving(null);
      await changed();
    },
  });

  return (
    <div className="space-y-8">
      <NewDepartment onCreated={changed} />
      <section aria-labelledby="departments-heading" className="space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h2 id="departments-heading" className="text-lg font-semibold">
            Departments
          </h2>
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={showArchived} onChange={(e) => setShowArchived(e.target.checked)} className="size-4 accent-primary" />
            Show archived
          </label>
        </div>
        {archive.isError && !archiving && <Callout tone="danger">{errorText(archive.error)}</Callout>}
        {departments.isPending ? (
          <ListLoading label="Loading departments" />
        ) : departments.isError ? (
          <ErrorState title="Couldn't load the departments." error={departments.error} onRetry={() => void departments.refetch()} retrying={departments.isFetching} />
        ) : departments.data.items.length === 0 ? (
          <EmptyState Icon={Building2} title="No departments yet.">
            Add one above. The roster refers to departments by their code.
          </EmptyState>
        ) : (
          <DataTable
            caption="Departments"
            rows={departments.data.items}
            rowKey={(d) => d.id}
            columns={[
              { header: "Code", cell: (d) => <span className="font-mono">{d.code}</span> },
              {
                header: "Name",
                cell: (d) => (
                  <div className="space-y-0.5">
                    <p className="font-medium">{d.name}</p>
                    {d.description && <p className="text-muted">{d.description}</p>}
                  </div>
                ),
              },
              { header: "Status", cell: (d) => (d.archived ? "Archived" : "Active") },
              {
                header: "Actions",
                cell: (d) => (
                  <div className="-ml-3 flex flex-wrap gap-2 md:-my-1.5 md:ml-0">
                    <Button size="sm" variant="ghost" aria-expanded={editing === d.id} aria-label={`${editing === d.id ? "Close" : "Edit"} ${d.code}`} onClick={() => setEditing(editing === d.id ? null : d.id)}>
                      {editing === d.id ? "Close" : "Edit"}
                    </Button>
                    {d.archived ? (
                      <Button size="sm" variant="ghost" aria-label={`Restore ${d.code}`} disabled={archive.isPending} onClick={() => archive.mutate({ id: d.id, archived: false })}>
                        Restore
                      </Button>
                    ) : (
                      <Button size="sm" variant="ghost" aria-label={`Archive ${d.code}`} onClick={() => setArchiving(d)}>
                        Archive
                      </Button>
                    )}
                  </div>
                ),
              },
            ]}
            detail={(d) =>
              editing === d.id ? (
                <EditDepartment
                  department={d}
                  onDone={async () => {
                    setEditing(null);
                    await changed();
                  }}
                />
              ) : null
            }
          />
        )}
      </section>
      {archiving && (
        <ConfirmDialog
          title={`Archive ${archiving.code}?`}
          description="It can't be chosen for new members or roles any more. Its members keep it, and you can restore it later."
          confirmLabel="Archive"
          pendingLabel="Archiving…"
          pending={archive.isPending}
          error={archive.isError ? errorText(archive.error) : null}
          onConfirm={() => archive.mutate({ id: archiving.id, archived: true })}
          onCancel={() => {
            setArchiving(null);
            archive.reset();
          }}
        />
      )}
    </div>
  );
}

function NewDepartment({ onCreated }: { onCreated: () => Promise<unknown> }) {
  const [formError, setFormError] = useState<string | null>(null);
  const form = useForm<DepartmentValues>({ resolver: zodResolver(departmentSchema), defaultValues: { code: "", name: "", description: "" } });
  const { errors } = form.formState;
  const create = useMutation({
    mutationFn: createDepartment,
    onSuccess: async () => {
      form.reset();
      await onCreated();
    },
    onError: (error) => setFormError(applyServerError(error, form.setError, ["code", "name", "description"])),
  });
  const onSubmit = form.handleSubmit((values) => {
    setFormError(null);
    create.mutate(values);
  });
  return (
    <section aria-labelledby="new-department" className="space-y-4">
      <h2 id="new-department" className="text-lg font-semibold">
        Add a department
      </h2>
      <form noValidate onSubmit={(event) => void onSubmit(event)} className="space-y-4">
        {formError && <Callout tone="danger">{formError}</Callout>}
        <div className="grid gap-4 sm:grid-cols-[10rem_1fr]">
          <FormField id="department-code" label="Code" autoComplete="off" spellCheck={false} className="font-mono uppercase" helper="Permanent, e.g. CSE." error={errors.code?.message} {...form.register("code")} />
          <FormField id="department-name" label="Name" autoComplete="off" error={errors.name?.message} {...form.register("name")} />
        </div>
        <FormField id="department-description" label="Description (optional)" autoComplete="off" error={errors.description?.message} {...form.register("description")} />
        <SubmitButton pending={create.isPending} pendingLabel="Adding…">
          Add department
        </SubmitButton>
      </form>
    </section>
  );
}

function EditDepartment({ department, onDone }: { department: Department; onDone: () => Promise<void> }) {
  const [formError, setFormError] = useState<string | null>(null);
  const form = useForm<DepartmentEditValues>({
    resolver: zodResolver(departmentEditSchema),
    defaultValues: { name: department.name, description: department.description },
  });
  const { errors } = form.formState;
  const save = useMutation({
    mutationFn: (values: DepartmentEditValues) => updateDepartment(department.id, values),
    onSuccess: onDone,
    onError: (error) => setFormError(applyServerError(error, form.setError, ["name", "description"])),
  });
  const onSubmit = form.handleSubmit((values) => {
    setFormError(null);
    save.mutate(values);
  });
  return (
    <form noValidate aria-label={`Edit ${department.code}`} onSubmit={(event) => void onSubmit(event)} className="space-y-4">
      {formError && <Callout tone="danger">{formError}</Callout>}
      <FormField id={`name-${department.id}`} label="Name" autoComplete="off" error={errors.name?.message} {...form.register("name")} />
      <FormField id={`description-${department.id}`} label="Description" autoComplete="off" error={errors.description?.message} {...form.register("description")} />
      <SubmitButton size="sm" pending={save.isPending} pendingLabel="Saving…">
        Save changes
      </SubmitButton>
    </form>
  );
}
