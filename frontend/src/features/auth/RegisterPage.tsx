import { useMutation } from "@tanstack/react-query";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { useNavigate } from "react-router";

import { Callout } from "@/components/Callout";
import { FormField } from "@/components/FormField";
import { SubmitButton } from "@/components/SubmitButton";
import { TextLink } from "@/components/TextLink";
import { zodResolver } from "@/lib/zodResolver";

import { register } from "./api";
import { AuthHeading } from "./AuthHeading";
import { PASSWORD_MIN, registerSchema, type RegisterValues } from "./schemas";
import { applyServerError } from "./serverErrors";

export const PASSWORD_RULES = `At least ${PASSWORD_MIN} characters. Avoid common passwords and your email address.`;

export function RegisterPage() {
  const navigate = useNavigate();
  const [formError, setFormError] = useState<string | null>(null);
  const form = useForm<RegisterValues>({
    resolver: zodResolver(registerSchema),
    mode: "onBlur",
    defaultValues: { display_name: "", email: "", password: "" },
  });
  const { errors } = form.formState;

  const mutation = useMutation({
    mutationFn: register,
    // The same answer for new and already-registered emails (AUTH-002): no enumeration.
    onSuccess: () => void navigate("/check-email"),
    onError: (error) => setFormError(applyServerError(error, form.setError, ["display_name", "email", "password"], "Too many sign-ups from this network.")),
  });

  const onSubmit = form.handleSubmit((values) => {
    setFormError(null);
    mutation.mutate(values);
  });

  return (
    <div className="space-y-8">
      <AuthHeading title="Create your account">
        <p>You'll join your college after you verify your email.</p>
      </AuthHeading>
      <form noValidate onSubmit={(event) => void onSubmit(event)} className="space-y-5">
        {formError && <Callout tone="danger">{formError}</Callout>}
        <FormField id="display_name" label="Your name" autoComplete="name" helper="How other members will see you." error={errors.display_name?.message} {...form.register("display_name")} />
        <FormField id="email" label="Email" type="email" autoComplete="email" inputMode="email" error={errors.email?.message} {...form.register("email")} />
        <FormField id="password" label="Password" type="password" autoComplete="new-password" helper={PASSWORD_RULES} error={errors.password?.message} {...form.register("password")} />
        <SubmitButton pending={mutation.isPending} pendingLabel="Creating account…" className="w-full">
          Create account
        </SubmitButton>
      </form>
      <p className="text-sm text-muted">
        Already have an account? <TextLink to="/sign-in">Sign in</TextLink>
      </p>
    </div>
  );
}
