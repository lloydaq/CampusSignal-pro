import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { RotateCw, Search } from "lucide-react";
import { useId, useState } from "react";
import { useForm, useWatch } from "react-hook-form";
import { Navigate, useNavigate } from "react-router";

import { Callout } from "@/components/Callout";
import { FormField } from "@/components/FormField";
import { SubmitButton } from "@/components/SubmitButton";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { fetchColleges, fetchMyRequests, requestMembership, type CollegeListing } from "@/features/auth/api";
import { AuthHeading } from "@/features/auth/AuthHeading";
import { ResendVerification } from "@/features/auth/ResendVerification";
import { joinSchema, type JoinValues } from "@/features/auth/schemas";
import { applyServerError } from "@/features/auth/serverErrors";
import { refreshSession, useMe } from "@/features/auth/session";
import { ApiError } from "@/lib/api";
import { useDelayedFlag } from "@/lib/useDelayedFlag";
import { zodResolver } from "@/lib/zodResolver";

const myRequestsKey = ["me", "membership-requests"] as const;

const CONFLICTS: Record<string, string> = {
  already_member: "You're already a member of a college.",
  request_pending: "You already have a request waiting for review.",
  membership_open: "Your membership at this college is suspended. Contact your college office.",
};

/** Design.md §5 screen 2: choose the college, enter the roll number, see where things stand. */
export function JoinPage() {
  const me = useMe();
  if (me.capabilities.includes("campus")) return <Navigate to="/home" replace />;
  if (me.capabilities.includes("platform")) {
    return (
      <AuthHeading title="Platform admins don't join colleges">
        <p>Platform admin accounts are kept separate from colleges. Use a different account to join one.</p>
      </AuthHeading>
    );
  }
  const membership = me.membership;
  if (membership?.status === "PENDING") {
    return (
      <AuthHeading title={`Waiting for approval by ${membership.college.name}`}>
        <p>Your college will review your request. You'll get access to {membership.college.name} once they approve it.</p>
      </AuthHeading>
    );
  }
  if (membership && membership.status !== "ACTIVE") {
    return (
      <AuthHeading title={`Your membership at ${membership.college.name} is suspended`}>
        <p>Contact your college office to have it restored.</p>
      </AuthHeading>
    );
  }
  if (!me.user.email_verified) {
    return (
      <div className="space-y-6">
        <AuthHeading title="Verify your email first">
          <p>Your college needs to know this email address is yours before you can join. Open the link we emailed you, or ask for a new one.</p>
        </AuthHeading>
        <ResendVerification />
      </div>
    );
  }
  return <JoinForm />;
}

function LastRejection() {
  const requests = useQuery({ queryKey: myRequestsKey, queryFn: ({ signal }) => fetchMyRequests(signal) });
  const latest = requests.data?.items[0];
  if (!latest || latest.status !== "REJECTED") return null;
  return (
    <Callout tone="warning" title={`${latest.college.name} turned down your last request`}>
      {latest.decision_reason && <p>“{latest.decision_reason}”</p>}
      <p>Contact your college office if you think this is a mistake, or try again below.</p>
    </Callout>
  );
}

function CollegePicker({
  value,
  onChange,
  error,
}: {
  value: string;
  onChange: (slug: string) => void;
  error: string | undefined;
}) {
  const colleges = useQuery({ queryKey: ["colleges"], queryFn: ({ signal }) => fetchColleges(signal) });
  const [filter, setFilter] = useState("");
  const searchId = useId();
  const showSkeleton = useDelayedFlag(colleges.isPending);
  const matches: CollegeListing[] = (colleges.data?.items ?? []).filter((c) =>
    c.name.toLowerCase().includes(filter.trim().toLowerCase()),
  );

  return (
    <fieldset className="space-y-3" aria-describedby={error ? "college-error" : undefined}>
      <legend className="text-sm font-medium text-fg">Your college</legend>
      {colleges.isPending && (
        <p role="status" className={showSkeleton ? "text-sm text-muted" : "sr-only"}>
          Loading colleges…
        </p>
      )}
      {colleges.isError && (
        <div role="alert" className="space-y-2">
          <p className="text-sm text-danger-fg">Couldn't load the list of colleges.</p>
          <Button variant="secondary" size="sm" onClick={() => void colleges.refetch()}>
            <RotateCw aria-hidden="true" strokeWidth={1.5} />
            Try again
          </Button>
        </div>
      )}
      {colleges.isSuccess && colleges.data.items.length === 0 && (
        <p className="text-sm text-muted">No colleges are open for joining yet.</p>
      )}
      {colleges.isSuccess && colleges.data.items.length > 0 && (
        <>
          {colleges.data.items.length > 7 && (
            <div className="relative">
              <label htmlFor={searchId} className="sr-only">
                Search colleges
              </label>
              <Search aria-hidden="true" strokeWidth={1.5} className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-subtle" />
              <Input id={searchId} type="search" placeholder="Search by name" value={filter} onChange={(e) => setFilter(e.target.value)} className="pl-9" />
            </div>
          )}
          <div className="divide-y divide-border rounded-sm border border-border-strong bg-surface">
            {matches.slice(0, 8).map((college) => (
              <label key={college.slug} className="flex min-h-11 cursor-pointer items-center gap-3 px-3 py-2 text-sm has-checked:bg-primary-subtle">
                <input type="radio" name="college" value={college.slug} checked={value === college.slug} onChange={() => onChange(college.slug)} className="size-4 accent-primary" />
                {college.name}
              </label>
            ))}
            {matches.length === 0 && <p className="px-3 py-2 text-sm text-muted">No college matches “{filter}”.</p>}
          </div>
        </>
      )}
      {error && (
        <p id="college-error" className="text-sm text-danger-fg">
          {error}
        </p>
      )}
    </fieldset>
  );
}

function JoinForm() {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [formError, setFormError] = useState<string | null>(null);
  const form = useForm<JoinValues>({
    resolver: zodResolver(joinSchema),
    mode: "onSubmit",
    defaultValues: { college_slug: "", roll_number: "" },
  });
  const { errors } = form.formState;
  const slug = useWatch({ control: form.control, name: "college_slug" });

  const mutation = useMutation({
    mutationFn: requestMembership,
    onSuccess: async (result) => {
      await refreshSession(queryClient);
      await queryClient.invalidateQueries({ queryKey: myRequestsKey });
      if (result.status === "ACTIVE") await navigate("/home", { replace: true });
      // PENDING: /me now shows the request, and this page turns into its status screen.
    },
    onError: (error) => {
      if (error instanceof ApiError && error.code in CONFLICTS) return setFormError(CONFLICTS[error.code] ?? error.message);
      if (error instanceof ApiError && error.status === 404) return setFormError("This college isn't open for joining right now.");
      setFormError(applyServerError(error, form.setError, ["roll_number"], "You've made several requests today."));
    },
  });

  const onSubmit = form.handleSubmit((values) => {
    setFormError(null);
    mutation.mutate(values);
  });

  return (
    <div className="space-y-8">
      <AuthHeading title="Join your college">
        <p>Choose your college and enter your roll number. We check it against the student list your college gave us: if the email on that list is yours, you're in straight away. Otherwise your college reviews your request.</p>
      </AuthHeading>
      <LastRejection />
      <form noValidate onSubmit={(event) => void onSubmit(event)} className="space-y-6">
        {formError && <Callout tone="danger">{formError}</Callout>}
        <CollegePicker value={slug} onChange={(next) => form.setValue("college_slug", next, { shouldValidate: form.formState.isSubmitted })} error={errors.college_slug?.message} />
        <FormField id="roll_number" label="Roll number" autoComplete="off" spellCheck={false} className="font-mono uppercase" helper="As printed on your college ID card." error={errors.roll_number?.message} {...form.register("roll_number")} />
        <SubmitButton pending={mutation.isPending} pendingLabel="Sending…">
          Send request
        </SubmitButton>
      </form>
    </div>
  );
}
