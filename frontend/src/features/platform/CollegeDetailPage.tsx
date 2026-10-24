import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useId, useState, type ReactNode } from "react";
import { useForm } from "react-hook-form";
import { Link, useParams } from "react-router";

import { Callout } from "@/components/Callout";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import { DataTable } from "@/components/DataTable";
import { ErrorState } from "@/components/ErrorState";
import { FormField } from "@/components/FormField";
import { SubmitButton } from "@/components/SubmitButton";
import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { ListLoading } from "@/features/admin/list";
import { errorText } from "@/features/admin/labels";
import { applyServerError } from "@/features/auth/serverErrors";
import { KIND_LABEL } from "@/features/campus/labels";
import { ApiError } from "@/lib/api";
import { formatDateTime } from "@/lib/datetime";
import { usePageTitle } from "@/lib/usePageTitle";
import { zodResolver } from "@/lib/zodResolver";

import { fetchCollege, inviteCollegeAdmin, updateCollege, type CollegeStatus, type PlatformCollegeDetail } from "./api";
import { collegeKey, collegesKey, STATUS_LABEL } from "./labels";
import { adminInviteSchema, type AdminInviteValues } from "./schemas";

const INVITE_STATE = { PENDING: "Waiting", ACCEPTED: "Accepted", EXPIRED: "Expired", REVOKED: "Withdrawn" } as const;

/** One college: status, and its first (or another) college admin (ADMIN-001, ADMIN-002). */
export function CollegeDetailPage() {
  const { collegeId = "" } = useParams();
  const college = useQuery({ queryKey: collegeKey(collegeId), queryFn: ({ signal }) => fetchCollege(collegeId, signal) });
  usePageTitle(college.data ? `${college.data.name} · Platform` : "College · Platform");

  if (college.isPending) return <ListLoading label="Loading the college" />;
  if (college.isError) {
    if (college.error instanceof ApiError && college.error.status === 404) {
      return (
        <Callout tone="info" title="That college doesn't exist.">
          <Link to="/platform/colleges" className="underline underline-offset-2">
            Back to colleges
          </Link>
        </Callout>
      );
    }
    return <ErrorState title="Couldn't load the college." error={college.error} onRetry={() => void college.refetch()} retrying={college.isFetching} />;
  }
  return <CollegeDetail college={college.data} />;
}

function CollegeDetail({ college }: { college: PlatformCollegeDetail }) {
  return (
    <div className="space-y-8">
      <nav aria-label="Breadcrumb" className="text-sm text-muted">
        <Link to="/platform/colleges" className="underline underline-offset-2">
          Colleges
        </Link>{" "}
        / <span aria-current="page">{college.name}</span>
      </nav>
      <div className="space-y-2">
        <h2 className="text-2xl font-semibold">{college.name}</h2>
        {college.is_demo && <p className="text-sm font-medium text-warning-fg">Demo data: this college is fictional.</p>}
        <dl className="grid gap-4 pt-2 text-sm sm:grid-cols-2">
          <Fact label="Status" value={STATUS_LABEL[college.status]} />
          <Fact label="Active members" value={String(college.active_member_count)} />
          <Fact label="Slug" value={<span className="font-mono">{college.slug}</span>} />
          <Fact label="Time zone" value={college.timezone} />
          <Fact label="Email domains" value={college.email_domains.length ? college.email_domains.join(", ") : "None"} />
          <Fact label="Created" value={formatDateTime(college.created_at, "UTC") + " UTC"} />
        </dl>
      </div>
      <StatusActions college={college} />
      <AdminInvites college={college} />
    </div>
  );
}

function Fact({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div>
      <dt className="text-muted">{label}</dt>
      <dd className="font-medium">{value}</dd>
    </div>
  );
}

const TRANSITIONS: Record<CollegeStatus, { to: CollegeStatus; label: string; reason: boolean; consequence: string }[]> = {
  ONBOARDING: [{ to: "ACTIVE", label: "Activate", reason: false, consequence: "Members can open the college." }],
  ACTIVE: [
    {
      to: "SUSPENDED",
      label: "Suspend",
      reason: true,
      consequence: "Nobody in this college can open it until you reactivate it.",
    },
  ],
  SUSPENDED: [{ to: "ACTIVE", label: "Reactivate", reason: false, consequence: "Members can open the college again." }],
};

function StatusActions({ college }: { college: PlatformCollegeDetail }) {
  const queryClient = useQueryClient();
  const [pending, setPending] = useState<(typeof TRANSITIONS)[CollegeStatus][number] | null>(null);
  const change = useMutation({
    mutationFn: ({ to, reason }: { to: CollegeStatus; reason: string }) => updateCollege(college.id, { status: to, ...(reason ? { reason } : {}) }),
    onSuccess: async (updated) => {
      setPending(null);
      queryClient.setQueryData(collegeKey(college.id), updated);
      await queryClient.invalidateQueries({ queryKey: collegesKey });
    },
  });
  return (
    <section aria-labelledby="status-heading" className="space-y-3">
      <h3 id="status-heading" className="text-lg font-semibold">
        Status
      </h3>
      <div className="flex flex-wrap gap-3">
        {TRANSITIONS[college.status].map((t) => (
          <Button key={t.to} variant={t.to === "SUSPENDED" ? "destructive" : "secondary"} onClick={() => setPending(t)}>
            {t.label}
          </Button>
        ))}
      </div>
      {pending && (
        <ConfirmDialog
          title={`${pending.label} ${college.name}?`}
          description={pending.consequence}
          confirmLabel={pending.label}
          pendingLabel={`${pending.label.replace(/e$/, "")}ing…`}
          destructive={pending.to === "SUSPENDED"}
          {...(pending.reason ? { reasonLabel: "Reason (recorded in the audit log)" } : {})}
          pending={change.isPending}
          error={change.isError ? errorText(change.error) : null}
          onConfirm={(reason) => change.mutate({ to: pending.to, reason })}
          onCancel={() => {
            setPending(null);
            change.reset();
          }}
        />
      )}
    </section>
  );
}

function AdminInvites({ college }: { college: PlatformCollegeDetail }) {
  const queryClient = useQueryClient();
  const kindId = useId();
  const reasonId = useId();
  const [formError, setFormError] = useState<string | null>(null);
  const [sentTo, setSentTo] = useState<string | null>(null);
  const form = useForm<AdminInviteValues>({ resolver: zodResolver(adminInviteSchema), defaultValues: { email: "", kind: "STAFF", reason: "" } });
  const { errors } = form.formState;
  const send = useMutation({
    mutationFn: (values: AdminInviteValues) =>
      inviteCollegeAdmin(college.id, { email: values.email, kind: values.kind, ...(values.reason ? { reason: values.reason } : {}) }),
    onSuccess: async (invite) => {
      setSentTo(invite.email);
      form.reset({ email: "", kind: form.getValues("kind"), reason: "" });
      await queryClient.invalidateQueries({ queryKey: collegeKey(college.id) });
    },
    onError: (error) => setFormError(applyServerError(error, form.setError, ["email", "kind", "reason"], "You've sent many invitations recently.")),
  });
  const onSubmit = form.handleSubmit((values) => {
    setFormError(null);
    setSentTo(null);
    send.mutate(values);
  });
  return (
    <section aria-labelledby="admins-heading" className="space-y-4">
      <h3 id="admins-heading" className="text-lg font-semibold">
        College admin invitations
      </h3>
      <form noValidate onSubmit={(event) => void onSubmit(event)} className="space-y-4">
        {formError && <Callout tone="danger">{formError}</Callout>}
        {sentTo && <Callout tone="success">Invitation sent to {sentTo}. They accept it after signing in with that address.</Callout>}
        <div className="grid gap-4 sm:grid-cols-[1fr_auto]">
          <FormField id="admin-email" label="Email" type="email" autoComplete="off" error={errors.email?.message} {...form.register("email")} />
          <div className="space-y-1.5">
            <label htmlFor={kindId} className="block text-sm font-medium">
              Joins as
            </label>
            <Select id={kindId} {...form.register("kind")}>
              <option value="STAFF">Staff</option>
              <option value="FACULTY">Faculty</option>
            </Select>
          </div>
        </div>
        <div className="space-y-1.5">
          <label htmlFor={reasonId} className="block text-sm font-medium">
            Reason (needed when the college already has an admin)
          </label>
          <Textarea id={reasonId} maxLength={500} aria-invalid={errors.reason ? true : undefined} {...form.register("reason")} />
          {errors.reason && <p className="text-sm text-danger-fg">{errors.reason.message}</p>}
        </div>
        <SubmitButton pending={send.isPending} pendingLabel="Sending…">
          Invite as college admin
        </SubmitButton>
      </form>
      {college.admin_invites.length > 0 && (
        <DataTable
          caption="College admin invitations"
          rows={college.admin_invites}
          rowKey={(i) => i.id}
          columns={[
            { header: "Email", cell: (i) => <span className="break-all">{i.email}</span> },
            { header: "As", cell: (i) => KIND_LABEL[i.kind] },
            { header: "State", cell: (i) => INVITE_STATE[i.state] },
            { header: "Sent", cell: (i) => formatDateTime(i.created_at, "UTC") },
            { header: "Expires", cell: (i) => formatDateTime(i.expires_at, "UTC") },
          ]}
        />
      )}
    </section>
  );
}
