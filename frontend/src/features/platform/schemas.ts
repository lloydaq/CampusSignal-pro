import { z } from "zod";

import { email } from "@/features/auth/schemas";

/** Mirrors backend app/schemas/platform.py; the server has the last word. */

const DOMAIN = /^[a-z0-9-]{1,63}(\.[a-z0-9-]{1,63})+$/;

/** "northfield.edu, Riverside.EDU" → ["northfield.edu", "riverside.edu"]. */
export const domainsOf = (text: string) => text.split(/[\s,]+/).filter(Boolean).map((d) => d.toLowerCase());

export const collegeSchema = z.object({
  name: z.string().trim().min(1, "Enter the college's name.").max(120, "Use at most 120 characters."),
  slug: z
    .string()
    .trim()
    .toLowerCase()
    .regex(/^[a-z0-9]([a-z0-9-]{0,48}[a-z0-9])?$/, "Use 1 to 50 lower-case letters, digits and hyphens (not at the ends)."),
  timezone: z.string().trim().min(1, "Enter a time zone such as Asia/Kolkata."),
  email_domains: z.string().refine((text) => {
    const domains = domainsOf(text);
    return domains.length <= 10 && domains.every((d) => DOMAIN.test(d));
  }, "Enter up to 10 domains like northfield.edu, separated by commas."),
  is_demo: z.boolean(),
});
export type CollegeValues = z.infer<typeof collegeSchema>;

export const adminInviteSchema = z.object({
  email,
  kind: z.enum(["FACULTY", "STAFF"]),
  reason: z.string().trim().max(500, "Use at most 500 characters."),
});
export type AdminInviteValues = z.infer<typeof adminInviteSchema>;

export const userLookupSchema = z.object({ email });
export type UserLookupValues = z.infer<typeof userLookupSchema>;
