import { z } from "zod";

import { email } from "@/features/auth/schemas";

/** Client-side checks mirror the backend's (app/schemas/college_admin.py); the server decides. */

export const inviteSchema = z.object({ email, kind: z.enum(["FACULTY", "STAFF"]) });
export type InviteValues = z.infer<typeof inviteSchema>;

const name = z
  .string()
  .trim()
  .min(1, "Enter a name.")
  .max(120, "Use at most 120 characters.");

export const departmentSchema = z.object({
  code: z
    .string()
    .trim()
    .toUpperCase()
    .regex(/^[A-Z0-9][A-Z0-9-]{0,15}$/, "Use 1 to 16 letters, digits or hyphens, starting with a letter or digit."),
  name,
  description: z.string().max(2000, "Use at most 2,000 characters."),
});
export type DepartmentValues = z.infer<typeof departmentSchema>;

export const departmentEditSchema = departmentSchema.omit({ code: true });
export type DepartmentEditValues = z.infer<typeof departmentEditSchema>;
