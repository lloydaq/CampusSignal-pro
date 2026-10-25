import { z } from "zod";

/** Mirrors backend app/schemas/notices.py (NOTICE-001); the server has the last word. */

export const TITLE_MAX = 150;
export const BODY_MAX = 10_000;

export const noticeSchema = z
  .object({
    title: z.string().trim().min(1, "Enter a title.").max(TITLE_MAX, `Use at most ${TITLE_MAX} characters.`),
    body: z.string().trim().min(1, "Write the notice.").max(BODY_MAX, "Use at most 10,000 characters."),
    category: z.enum(["ACADEMIC", "EXAMINATION", "ADMINISTRATIVE", "EVENT", "FACILITIES", "GENERAL"]),
    priority: z.enum(["NORMAL", "HIGH", "URGENT"]),
    scope: z.enum(["COLLEGE", "DEPARTMENT"]),
    department_id: z.string(),
    expires: z.string(),
  })
  .superRefine((values, ctx) => {
    if (values.scope === "DEPARTMENT" && !values.department_id) {
      ctx.addIssue({ code: "custom", path: ["department_id"], message: "Choose a department." });
    }
  });

export type NoticeFormValues = z.infer<typeof noticeSchema>;
