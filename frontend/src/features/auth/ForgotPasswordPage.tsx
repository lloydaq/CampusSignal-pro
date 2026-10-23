import { useMutation } from "@tanstack/react-query";
import { useState } from "react";
import { useForm } from "react-hook-form";

import { Callout } from "@/components/Callout";
import { FormField } from "@/components/FormField";
import { SubmitButton } from "@/components/SubmitButton";
import { TextLink } from "@/components/TextLink";
import { zodResolver } from "@/lib/zodResolver";

import { requestPasswordReset } from "./api";
import { AuthHeading } from "./AuthHeading";
import { forgotPasswordSchema, type ForgotPasswordValues } from "./schemas";
import { applyServerError } from "./serverErrors";

export function ForgotPasswordPage() {
  const [formError, setFormError] = useState<string | null>(null);
  const form = useForm<ForgotPasswordValues>({ resolver: zodResolver(forgotPasswordSchema), mode: "onBlur", defaultValues: { email: "" } });
  const mutation = useMutation({
    mutationFn: requestPasswordReset,
    onError: (error) => setFormError(applyServerError(error, form.setError, ["email"], "Too many reset requests.")),
  });

  if (mutation.isSuccess) {
    // The server's reply is the same whether or not the account exists (AUTH-006).
    return (
      <div className="space-y-8">
        <AuthHeading title="Check your email">
          <p>{mutation.data.message} The link works for 60 minutes.</p>
        </AuthHeading>
        <p className="text-sm text-muted">
          <TextLink to="/sign-in">Back to sign in</TextLink>
        </p>
      </div>
    );
  }

  const onSubmit = form.handleSubmit((values) => {
    setFormError(null);
    mutation.mutate(values);
  });

  return (
    <div className="space-y-8">
      <AuthHeading title="Reset your password">
        <p>Enter the email you signed up with and we'll send you a link to choose a new password.</p>
      </AuthHeading>
      <form noValidate onSubmit={(event) => void onSubmit(event)} className="space-y-5">
        {formError && <Callout tone="danger">{formError}</Callout>}
        <FormField id="email" label="Email" type="email" autoComplete="email" inputMode="email" error={form.formState.errors.email?.message} {...form.register("email")} />
        <SubmitButton pending={mutation.isPending} pendingLabel="Sending…" className="w-full">
          Send reset link
        </SubmitButton>
      </form>
      <p className="text-sm text-muted">
        <TextLink to="/sign-in">Back to sign in</TextLink>
      </p>
    </div>
  );
}
