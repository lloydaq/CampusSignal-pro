import { z } from "zod";

/** Mirrors backend app/schemas/issues.py (ISSUE-001, 005); the server has the last word. */

export const TITLE_MAX = 120;
export const LOCATION_MAX = 200;
export const ROOM_MAX = 100;
export const TEXT_MAX = 3000;

const text = (max: number, empty: string) =>
  z.string().trim().min(1, empty).max(max, `Use at most ${max.toLocaleString("en-IN")} characters.`);

export const reportSchema = z.object({
  category: z.enum(["CLASSROOM_EQUIPMENT", "INFRASTRUCTURE", "WATER_SANITATION", "ELECTRICAL", "NETWORK", "LIBRARY", "LABORATORY", "OTHER"], {
    error: "Choose a category.",
  }),
  title: text(TITLE_MAX, "Say what's wrong in a few words."),
  location: text(LOCATION_MAX, "Say where it is."),
  room: z.string().trim().max(ROOM_MAX, `Use at most ${ROOM_MAX} characters.`),
  description: text(TEXT_MAX, "Describe the problem."),
});

export type ReportFormValues = z.infer<typeof reportSchema>;

export const commentSchema = z.object({ body: text(TEXT_MAX, "Write a comment.") });
export type CommentFormValues = z.infer<typeof commentSchema>;
