import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { useLocation, useNavigate, useSearchParams } from "react-router";

import { Callout } from "@/components/Callout";
import { FormField } from "@/components/FormField";
import { SubmitButton } from "@/components/SubmitButton";
import { TextLink } from "@/components/TextLink";
import { zodResolver } from "@/lib/zodResolver";

import { signIn } from "./api";
import { AuthHeading } from "./AuthHeading";
import { safeNextPath } from "./navigation";
import { signInSchema, type SignInValues } from "./schemas";
import { applyServerError } from "./serverErrors";
import { sessionQueryKey } from "./session";

/** A message handed over by the previous screen, e.g. after a password reset or sign-out. */
export interface SignInNotice {
  notice?: string;
}

export function SignInPage() {
  const [params] = useSearchParams();
  const location = useLocation();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [formError, setFormError] = useState<string | null>(null);
  const notice = (location.state as SignInNotice | null)?.notice;
  const returning = params.has("next");

  const form = useForm<SignInValues>({
    resolver: zodResolver(signInSchema),
    mode: "onBlur",
    defaultValues: { email: "", password: "" },
  });
  const { errors } = form.formState;

  const mutation = useMutation({
    mutationFn: signIn,
    onSuccess: ({ user }) => {
      queryClient.setQueryData(sessionQueryKey, user);
      void navigate(safeNextPath(params.get("next")), { replace: true });
    },
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
    <div className="space-y-8">
      <AuthHeading title="Sign in">{returning && <p>Sign in to continue.</p>}</AuthHeading>
      {notice && <Callout tone="success">{notice}</Callout>}
      <form noValidate onSubmit={(event) => void onSubmit(event)} className="space-y-5">
        {formError && <Callout tone="danger">{formError}</Callout>}
        <FormField id="email" label="Email" type="email" autoComplete="email" inputMode="email" error={errors.email?.message} {...form.register("email")} />
        <FormField id="password" label="Password" type="password" autoComplete="current-password" error={errors.password?.message} {...form.register("password")} />
        <SubmitButton pending={mutation.isPending} pendingLabel="Signing in…" className="w-full">
          Sign in
        </SubmitButton>
      </form>
      <div className="space-y-2 text-sm text-muted">
        <p>
          <TextLink to="/forgot-password">Forgot your password?</TextLink>
        </p>
        <p>
          New to CampusSignal? <TextLink to="/register">Create an account</TextLink>
        </p>
      </div>
    </div>
  );
}
