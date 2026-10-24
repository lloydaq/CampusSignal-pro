import { useMutation } from "@tanstack/react-query";
import { useState } from "react";
import { useForm } from "react-hook-form";

import { Callout } from "@/components/Callout";
import { FormField } from "@/components/FormField";
import { SubmitButton } from "@/components/SubmitButton";
import { zodResolver } from "@/lib/zodResolver";

import { signIn, type User } from "./api";
import { signInSchema, type SignInValues } from "./schemas";
import { applyServerError } from "./serverErrors";

/** Email + password form shared by the sign-in page and the "session ended" dialog. */
export function SignInForm({
  onSignedIn,
  defaultEmail = "",
  idPrefix = "",
}: {
  onSignedIn: (user: User) => Promise<void> | void;
  defaultEmail?: string;
  idPrefix?: string;
}) {
  const [formError, setFormError] = useState<string | null>(null);
  const form = useForm<SignInValues>({
    resolver: zodResolver(signInSchema),
    mode: "onBlur",
    defaultValues: { email: defaultEmail, password: "" },
  });
  const { errors } = form.formState;

  const mutation = useMutation({
    mutationFn: signIn,
    onSuccess: ({ user }) => onSignedIn(user),
    onError: (error) => {
      // invalid_credentials carries one generic message for every failure (AUTH-007).
      setFormError(applyServerError(error, form.setError, ["email", "password"], "Too many sign-in attempts."));
      form.resetField("password", { keepError: true });
    },
  });

  const onSubmit = form.handleSubmit((values) => {
    setFormError(null);
    mutation.mutate(values);
  });

  return (
    <form noValidate onSubmit={(event) => void onSubmit(event)} className="space-y-5">
      {formError && <Callout tone="danger">{formError}</Callout>}
      <FormField id={`${idPrefix}email`} label="Email" type="email" autoComplete="email" inputMode="email" error={errors.email?.message} {...form.register("email")} />
      <FormField id={`${idPrefix}password`} label="Password" type="password" autoComplete="current-password" error={errors.password?.message} {...form.register("password")} />
      <SubmitButton pending={mutation.isPending} pendingLabel="Signing in…" className="w-full">
        Sign in
      </SubmitButton>
    </form>
  );
}
