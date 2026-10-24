import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { UserSearch } from "lucide-react";
import { useState } from "react";
import { useForm } from "react-hook-form";

import { Callout } from "@/components/Callout";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import { EmptyState } from "@/components/EmptyState";
import { ErrorState } from "@/components/ErrorState";
import { FormField } from "@/components/FormField";
import { SubmitButton } from "@/components/SubmitButton";
import { Button } from "@/components/ui/button";
import { errorText } from "@/features/admin/labels";
import { ListLoading } from "@/features/admin/list";
import { usePageTitle } from "@/lib/usePageTitle";
import { zodResolver } from "@/lib/zodResolver";

import { findUser, suspendUser, unsuspendUser, type PlatformUser } from "./api";
import { userLookupSchema, type UserLookupValues } from "./schemas";

/** Accounts (ADMIN-004): exact-email lookup only, so there is no browsing of people. */
export function UsersTab() {
  usePageTitle("Users · Platform");
  const [email, setEmail] = useState<string | null>(null);
  const form = useForm<UserLookupValues>({ resolver: zodResolver(userLookupSchema), defaultValues: { email: "" } });
  const onSubmit = form.handleSubmit((values) => setEmail(values.email));
  return (
    <div className="space-y-6">
      <form noValidate role="search" onSubmit={(event) => void onSubmit(event)} className="flex max-w-xl items-start gap-2">
        <div className="flex-1">
          <FormField
            id="user-email"
            label="Find an account by email"
            type="email"
            autoComplete="off"
            helper="The whole address, exactly."
            error={form.formState.errors.email?.message}
            {...form.register("email")}
          />
        </div>
        <SubmitButton pending={false} pendingLabel="Searching…" variant="secondary" className="mt-6">
          Find
        </SubmitButton>
      </form>
      {email && <UserResult email={email} />}
    </div>
  );
}

function UserResult({ email }: { email: string }) {
  const found = useQuery({ queryKey: ["platform", "user", email], queryFn: ({ signal }) => findUser(email, signal) });
  if (found.isPending) return <ListLoading label="Looking up the account" />;
  if (found.isError) return <ErrorState title="Couldn't look up that account." error={found.error} onRetry={() => void found.refetch()} retrying={found.isFetching} />;
  const user = found.data.items[0];
  if (!user) {
    return (
      <EmptyState Icon={UserSearch} title="No account has this email address.">
        Check the spelling: the address has to match exactly.
      </EmptyState>
    );
  }
  return <UserCard user={user} lookup={email} />;
}

function UserCard({ user, lookup }: { user: PlatformUser; lookup: string }) {
  const queryClient = useQueryClient();
  const [confirming, setConfirming] = useState(false);
  const done = (updated: PlatformUser) => {
    setConfirming(false);
    queryClient.setQueryData(["platform", "user", lookup], { items: [updated] });
  };
  const suspend = useMutation({ mutationFn: (reason: string) => suspendUser(user.id, reason), onSuccess: done });
  const reinstate = useMutation({ mutationFn: () => unsuspendUser(user.id), onSuccess: done });
  const suspended = user.status === "SUSPENDED";
  const isPlatformAdmin = user.platform_role !== null;
  return (
    <section aria-label="Account" className="max-w-xl space-y-4 rounded-sm border border-border p-4">
      <dl className="space-y-2 text-sm">
        <div>
          <dt className="text-muted">Name</dt>
          <dd className="font-medium">{user.display_name}</dd>
        </div>
        <div>
          <dt className="text-muted">Email</dt>
          <dd className="font-medium break-all">{user.email}</dd>
        </div>
        <div>
          <dt className="text-muted">Status</dt>
          <dd className="font-medium">{suspended ? "Suspended" : "Active"}</dd>
        </div>
        {isPlatformAdmin && (
          <div>
            <dt className="text-muted">Account type</dt>
            <dd className="font-medium">Platform admin</dd>
          </div>
        )}
      </dl>
      {reinstate.isError && <Callout tone="danger">{errorText(reinstate.error)}</Callout>}
      {suspended ? (
        <Button variant="secondary" onClick={() => reinstate.mutate()} disabled={reinstate.isPending}>
          {reinstate.isPending ? "Reinstating…" : "Reinstate account"}
        </Button>
      ) : (
        <Button variant="destructive" onClick={() => setConfirming(true)}>
          Suspend account
        </Button>
      )}
      {confirming && (
        <ConfirmDialog
          title={`Suspend ${user.display_name}?`}
          description="They're signed out everywhere straight away and can't sign in until you reinstate the account."
          reasonLabel="Reason (recorded in the audit log)"
          confirmLabel="Suspend account"
          pendingLabel="Suspending…"
          pending={suspend.isPending}
          error={suspend.isError ? errorText(suspend.error) : null}
          onConfirm={(reason) => suspend.mutate(reason)}
          onCancel={() => {
            setConfirming(false);
            suspend.reset();
          }}
        />
      )}
    </section>
  );
}
