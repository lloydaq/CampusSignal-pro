import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Mail } from "lucide-react";
import { useId, useState } from "react";
import { useForm } from "react-hook-form";

import { Callout } from "@/components/Callout";
import { DataTable } from "@/components/DataTable";
import { EmptyState } from "@/components/EmptyState";
import { ErrorState } from "@/components/ErrorState";
import { FormField } from "@/components/FormField";
import { SubmitButton } from "@/components/SubmitButton";
import { Select } from "@/components/ui/select";
import { applyServerError } from "@/features/auth/serverErrors";
import { KIND_LABEL } from "@/features/campus/labels";
import { formatDateTime } from "@/lib/datetime";
import { usePageTitle } from "@/lib/usePageTitle";
import { zodResolver } from "@/lib/zodResolver";

import { fetchInvites, sendInvite, type Invite } from "./api";
import { manageKeys } from "./keys";
import { ListLoading } from "./list";
import { inviteSchema, type InviteValues } from "./schemas";
import { useCollegeTimezone } from "./tabs";

const STATE_LABEL: Record<Invite["state"], string> = {
  PENDING: "Waiting",
  ACCEPTED: "Accepted",
  EXPIRED: "Expired",
  REVOKED: "Withdrawn",
};

/** Faculty and staff join by invitation (MEMBER-002); students join through the roster. */
export function InvitesTab() {
  usePageTitle("Invites · Manage");
  const timeZone = useCollegeTimezone();
  const invites = useQuery({ queryKey: manageKeys.invites, queryFn: ({ signal }) => fetchInvites(signal) });

  return (
    <div className="space-y-8">
      <InviteForm />
      <section aria-labelledby="sent-invites" className="space-y-3">
        <h2 id="sent-invites" className="text-lg font-semibold">
          Sent invitations
        </h2>
        {invites.isPending ? (
          <ListLoading label="Loading invitations" />
        ) : invites.isError ? (
          <ErrorState title="Couldn't load the invitations." error={invites.error} onRetry={() => void invites.refetch()} retrying={invites.isFetching} />
        ) : invites.data.items.length === 0 ? (
          <EmptyState Icon={Mail} title="No invitations sent yet." />
        ) : (
          <DataTable
            caption="Sent invitations"
            rows={invites.data.items}
            rowKey={(i) => i.id}
            columns={[
              { header: "Email", cell: (i) => <span className="break-all">{i.email}</span> },
              { header: "As", cell: (i) => KIND_LABEL[i.kind] },
              { header: "State", cell: (i) => STATE_LABEL[i.state] },
              { header: "Sent", cell: (i) => formatDateTime(i.created_at, timeZone) },
              { header: "Expires", cell: (i) => formatDateTime(i.expires_at, timeZone) },
            ]}
          />
        )}
      </section>
    </div>
  );
}

function InviteForm() {
  const queryClient = useQueryClient();
  const kindId = useId();
  const [formError, setFormError] = useState<string | null>(null);
  const [sentTo, setSentTo] = useState<string | null>(null);
  const form = useForm<InviteValues>({ resolver: zodResolver(inviteSchema), defaultValues: { email: "", kind: "FACULTY" } });
  const send = useMutation({
    mutationFn: sendInvite,
    onSuccess: async (invite) => {
      setSentTo(invite.email);
      form.reset({ email: "", kind: form.getValues("kind") });
      await queryClient.invalidateQueries({ queryKey: manageKeys.invites });
    },
    onError: (error) => setFormError(applyServerError(error, form.setError, ["email", "kind"], "You've sent many invitations recently.")),
  });
  const onSubmit = form.handleSubmit((values) => {
    setFormError(null);
    setSentTo(null);
    send.mutate(values);
  });

  return (
    <section aria-labelledby="invite-heading" className="space-y-4">
      <h2 id="invite-heading" className="text-lg font-semibold">
        Invite faculty or staff
      </h2>
      <form noValidate onSubmit={(event) => void onSubmit(event)} className="space-y-4">
        {formError && <Callout tone="danger">{formError}</Callout>}
        {sentTo && <Callout tone="success">Invitation sent to {sentTo}. It's valid for 7 days.</Callout>}
        <div className="grid gap-4 sm:grid-cols-[1fr_auto]">
          <FormField id="invite-email" label="Email" type="email" autoComplete="off" error={form.formState.errors.email?.message} {...form.register("email")} />
          <div className="space-y-1.5">
            <label htmlFor={kindId} className="block text-sm font-medium">
              Joins as
            </label>
            <Select id={kindId} {...form.register("kind")}>
              <option value="FACULTY">Faculty</option>
              <option value="STAFF">Staff</option>
            </Select>
          </div>
        </div>
        <SubmitButton pending={send.isPending} pendingLabel="Sending…">
          Send invitation
        </SubmitButton>
      </form>
    </section>
  );
}
