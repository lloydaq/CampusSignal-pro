import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { useNavigate } from "react-router";

import { Callout } from "@/components/Callout";
import { FormField } from "@/components/FormField";
import { SubmitButton } from "@/components/SubmitButton";
import { TextLink } from "@/components/TextLink";
import { ApiError } from "@/lib/api";
import { zodResolver } from "@/lib/zodResolver";

import { confirmPasswordReset } from "./api";
import { AuthHeading } from "./AuthHeading";
import { PASSWORD_RULES } from "./RegisterPage";
import { resetPasswordSchema, type ResetPasswordValues } from "./schemas";
import { applyServerError } from "./serverErrors";
import { sessionQueryKey } from "./session";
import type { SignInNotice } from "./SignInPage";
import { useFragmentToken } from "./useFragmentToken";

const LINK_PROBLEMS: Record<string, { title: string; body: string }> = {
  token_used: { title: "This link was already used", body: "Each reset link works once. Ask for a new one if you still need it." },
  token_expired: { title: "This link has expired", body: "Reset links work for 60 minutes. Ask for a new one." },
  token_invalid: { title: "This link isn't valid", body: "Open the whole link from your reset email, or ask for a new one." },
};

function LinkProblem({ code }: { code: string }) {
  const problem = LINK_PROBLEMS[code] ?? LINK_PROBLEMS.token_invalid!;
  return (
    <div className="space-y-6">
      <AuthHeading title={problem.title}>
        <p>{problem.body}</p>
      </AuthHeading>
      <p>
        <TextLink to="/forgot-password">Get a new reset link</TextLink>
      </p>
    </div>
  );
}

/** Opened from the reset email (AUTH-006). Completing it signs out everywhere, so it ends at sign-in. */
export function ResetPasswordPage() {
  const token = useFragmentToken();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [formError, setFormError] = useState<string | null>(null);
  const form = useForm<ResetPasswordValues>({
    resolver: zodResolver(resetPasswordSchema),
    mode: "onBlur",
    defaultValues: { new_password: "", confirm_password: "" },
  });
  const { errors } = form.formState;

  const mutation = useMutation({
    mutationFn: confirmPasswordReset,
    onSuccess: ({ message }) => {
      queryClient.setQueryData(sessionQueryKey, null); // every session was revoked
      const state: SignInNotice = { notice: message };
      void navigate("/sign-in", { replace: true, state });
    },
    onError: (error) => setFormError(applyServerError(error, form.setError, ["new_password"])),
  });

  const linkProblem = mutation.error instanceof ApiError && mutation.error.code in LINK_PROBLEMS ? mutation.error.code : null;
  if (!token) return <LinkProblem code="token_invalid" />;
  if (linkProblem) return <LinkProblem code={linkProblem} />;

  const onSubmit = form.handleSubmit(({ new_password }) => {
    setFormError(null);
    mutation.mutate({ token, new_password });
  });

  return (
    <div className="space-y-8">
      <AuthHeading title="Choose a new password">
        <p>You'll be signed out on every device and can then sign in with the new password.</p>
      </AuthHeading>
      <form noValidate onSubmit={(event) => void onSubmit(event)} className="space-y-5">
        {formError && <Callout tone="danger">{formError}</Callout>}
        <FormField id="new_password" label="New password" type="password" autoComplete="new-password" helper={PASSWORD_RULES} error={errors.new_password?.message} {...form.register("new_password")} />
        <FormField id="confirm_password" label="Repeat new password" type="password" autoComplete="new-password" error={errors.confirm_password?.message} {...form.register("confirm_password")} />
        <SubmitButton pending={mutation.isPending} pendingLabel="Saving…" className="w-full">
          Save new password
        </SubmitButton>
      </form>
    </div>
  );
}
