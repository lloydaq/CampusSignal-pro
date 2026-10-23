import { z } from "zod";

/**
 * Client checks mirroring the server's rules (backend app/schemas/auth.py and
 * app/core/security.py; Rules R-3.3). The server stays authoritative: the common-password
 * list and the email-in-password rule are checked there and come back as field errors.
 */

export const PASSWORD_MIN = 10;
export const PASSWORD_MAX = 128;
export const DISPLAY_NAME_MAX = 60;
const EMAIL_MAX = 254;
const EMAIL_PATTERN = /^[^@\s]+@[^@\s]+\.[^@\s]{2,}$/;

const email = z
  .string()
  .trim()
  .toLowerCase()
  .min(1, "Enter your email address.")
  .max(EMAIL_MAX, "Enter a valid email address.")
  .regex(EMAIL_PATTERN, "Enter a valid email address.");

/** Any non-empty password: for signing in and confirming the current password. */
const existingPassword = z.string().min(1, "Enter your password.").max(PASSWORD_MAX, `Use at most ${PASSWORD_MAX} characters.`);

const newPassword = z
  .string()
  .min(PASSWORD_MIN, `Use at least ${PASSWORD_MIN} characters.`)
  .max(PASSWORD_MAX, `Use at most ${PASSWORD_MAX} characters.`);

const displayName = z
  .string()
  .transform((value) => value.split(/\s+/).filter(Boolean).join(" "))
  .pipe(z.string().min(1, "Enter your name.").max(DISPLAY_NAME_MAX, `Use at most ${DISPLAY_NAME_MAX} characters.`));

const MISMATCH = "The passwords don't match.";

export const signInSchema = z.object({ email, password: existingPassword });
export type SignInValues = z.infer<typeof signInSchema>;

export const registerSchema = z.object({ display_name: displayName, email, password: newPassword });
export type RegisterValues = z.infer<typeof registerSchema>;

export const forgotPasswordSchema = z.object({ email });
export type ForgotPasswordValues = z.infer<typeof forgotPasswordSchema>;

export const resetPasswordSchema = z
  .object({ new_password: newPassword, confirm_password: z.string() })
  .refine((v) => v.new_password === v.confirm_password, { message: MISMATCH, path: ["confirm_password"] });
export type ResetPasswordValues = z.infer<typeof resetPasswordSchema>;

export const changePasswordSchema = z
  .object({ current_password: existingPassword, new_password: newPassword, confirm_password: z.string() })
  .refine((v) => v.new_password === v.confirm_password, { message: MISMATCH, path: ["confirm_password"] });
export type ChangePasswordValues = z.infer<typeof changePasswordSchema>;
