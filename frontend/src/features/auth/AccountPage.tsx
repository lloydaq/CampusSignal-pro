import { useMutation } from "@tanstack/react-query";
import { CircleCheck, TriangleAlert } from "lucide-react";
import { useState, type ReactNode } from "react";
import { useForm } from "react-hook-form";
import { useNavigate } from "react-router";

import { Callout } from "@/components/Callout";
import { FormField } from "@/components/FormField";
import { SubmitButton } from "@/components/SubmitButton";
import { TextLink } from "@/components/TextLink";
import { ThemeSwitcher } from "@/components/ThemeSwitcher";
import { Button } from "@/components/ui/button";
import { KIND_LABEL, roleLabel } from "@/features/campus/labels";
import { zodResolver } from "@/lib/zodResolver";

import { changePassword, signOut, signOutEverywhere, type Me, type User } from "./api";
import { AuthHeading } from "./AuthHeading";
import { PASSWORD_RULES } from "./RegisterPage";
import { ResendVerification } from "./ResendVerification";
import { changePasswordSchema, type ChangePasswordValues } from "./schemas";
import { applyServerError } from "./serverErrors";
import { SIGN_OUT_FAILED, useMe, useSignOut } from "./session";
import type { SignInNotice } from "./SignInPage";

function Section({ id, title, children }: { id: string; title: string; children: ReactNode }) {
  return (
    <section aria-labelledby={id} className="space-y-4 border-t border-border pt-6">
      <h2 id={id} className="text-lg font-semibold text-fg">
        {title}
      </h2>
      {children}
    </section>
  );
}

function Profile({ user }: { user: User }) {
  return (
    <Section id="profile-heading" title="Profile">
      <dl className="space-y-3 text-sm">
        <div>
          <dt className="text-muted">Name</dt>
          <dd className="font-medium text-fg">{user.display_name}</dd>
        </div>
        <div>
          <dt className="text-muted">Email</dt>
          <dd className="flex flex-wrap items-center gap-x-3 gap-y-1 font-medium break-all text-fg">
            {user.email}
            {user.email_verified ? (
              <span className="inline-flex items-center gap-1 text-success-fg">
                <CircleCheck aria-hidden="true" strokeWidth={1.5} className="size-4" />
                Verified
              </span>
            ) : (
              <span className="inline-flex items-center gap-1 text-warning-fg">
                <TriangleAlert aria-hidden="true" strokeWidth={1.5} className="size-4" />
                Not verified
              </span>
            )}
          </dd>
        </div>
      </dl>
      {!user.email_verified && (
        <div className="space-y-3">
          <p className="text-sm text-muted">Verify your email to join your college. Open the link we emailed you, or ask for a new one.</p>
          <ResendVerification />
        </div>
      )}
    </Section>
  );
}

function ChangePassword() {
  const [formError, setFormError] = useState<string | null>(null);
  const form = useForm<ChangePasswordValues>({
    resolver: zodResolver(changePasswordSchema),
    mode: "onBlur",
    defaultValues: { current_password: "", new_password: "", confirm_password: "" },
  });
  const { errors } = form.formState;
  const mutation = useMutation({
    mutationFn: changePassword,
    onSuccess: () => form.reset(),
    onError: (error) =>
      setFormError(applyServerError(error, form.setError, ["current_password", "new_password"], "Too many incorrect attempts.")),
  });

  const onSubmit = form.handleSubmit(({ current_password, new_password }) => {
    setFormError(null);
    mutation.mutate({ current_password, new_password });
  });

  return (
    <Section id="password-heading" title="Change password">
      <form noValidate onSubmit={(event) => void onSubmit(event)} className="space-y-5">
        {formError && <Callout tone="danger">{formError}</Callout>}
        {mutation.isSuccess && <Callout tone="success">Your password was changed. Other devices were signed out; you're still signed in here.</Callout>}
        <FormField id="current_password" label="Current password" type="password" autoComplete="current-password" error={errors.current_password?.message} {...form.register("current_password")} />
        <FormField id="new_password" label="New password" type="password" autoComplete="new-password" helper={PASSWORD_RULES} error={errors.new_password?.message} {...form.register("new_password")} />
        <FormField id="confirm_password" label="Repeat new password" type="password" autoComplete="new-password" error={errors.confirm_password?.message} {...form.register("confirm_password")} />
        <SubmitButton pending={mutation.isPending} pendingLabel="Changing password…">
          Change password
        </SubmitButton>
      </form>
    </Section>
  );
}

function SignOut() {
  const navigate = useNavigate();
  const [confirming, setConfirming] = useState(false);

  const toSignIn = (notice: string) => {
    const state: SignInNotice = { notice };
    void navigate("/sign-in", { replace: true, state });
  };
  const here = useSignOut(signOut, () => toSignIn("You've signed out."));
  const everywhere = useSignOut(signOutEverywhere, () => toSignIn("You've signed out on all devices."));
  const pending = here.isPending || everywhere.isPending;

  return (
    <Section id="sign-out-heading" title="Sign out">
      {(here.failed || everywhere.failed) && <Callout tone="danger">{SIGN_OUT_FAILED}</Callout>}
      <div className="flex flex-wrap gap-3">
        <Button variant="secondary" onClick={() => here.mutate()} disabled={pending}>
          {here.isPending ? "Signing out…" : "Sign out"}
        </Button>
        {!confirming && (
          <Button variant="ghost" onClick={() => setConfirming(true)} disabled={pending}>
            Sign out of all devices
          </Button>
        )}
      </div>
      {confirming && (
        <div role="group" aria-labelledby="sign-out-all-question" className="space-y-3 rounded-sm border border-border-strong p-4">
          <p id="sign-out-all-question" className="text-sm text-fg">
            Sign out on every phone and computer where you're signed in, including this one?
          </p>
          <div className="flex flex-wrap gap-3">
            <Button variant="destructive" onClick={() => everywhere.mutate()} disabled={pending}>
              {everywhere.isPending ? "Signing out…" : "Sign out everywhere"}
            </Button>
            <Button variant="ghost" onClick={() => setConfirming(false)} disabled={pending}>
              Cancel
            </Button>
          </div>
        </div>
      )}
    </Section>
  );
}

function MembershipSection({ me }: { me: Me }) {
  const membership = me.membership;
  return (
    <Section id="membership-heading" title="College">
      {membership ? (
        <dl className="space-y-3 text-sm">
          <div>
            <dt className="text-muted">College</dt>
            <dd className="font-medium text-fg">{membership.college.name}</dd>
          </div>
          <div>
            <dt className="text-muted">{membership.status === "ACTIVE" ? "Role" : "Status"}</dt>
            <dd className="font-medium text-fg">
              {membership.status === "ACTIVE" ? KIND_LABEL[membership.kind] : membership.status === "PENDING" ? "Waiting for approval" : "Suspended"}
            </dd>
          </div>
          {membership.department && (
            <div>
              <dt className="text-muted">Department</dt>
              <dd className="font-medium text-fg">
                {membership.department.name} ({membership.department.code})
              </dd>
            </div>
          )}
          {me.roles.length > 0 && (
            <div>
              <dt className="text-muted">Responsibilities</dt>
              <dd className="font-medium text-fg">{me.roles.map(roleLabel).join(", ")}</dd>
            </div>
          )}
        </dl>
      ) : me.capabilities.includes("platform") ? (
        <p className="text-sm text-muted">Platform admin accounts aren't members of a college.</p>
      ) : (
        <p className="text-sm text-muted">
          You haven't joined a college yet. <TextLink to="/join">Join your college</TextLink>
        </p>
      )}
    </Section>
  );
}

/** Account settings (AUTH-005, AUTH-010; Design.md §5 screen 15). */
export function AccountPage() {
  const me = useMe();
  return (
    <div className="space-y-8">
      <AuthHeading title="Account" />
      <Profile user={me.user} />
      <MembershipSection me={me} />
      <ChangePassword />
      <Section id="appearance-heading" title="Appearance">
        <ThemeSwitcher />
      </Section>
      <SignOut />
    </div>
  );
}
