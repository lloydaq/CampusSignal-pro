import type { Page, Route } from "@playwright/test";

/**
 * A synthetic student's academics (backend app/api/v1/academic.py) for Aarav Nair of CSE in
 * Northfield's demo college: a week of classes, attendance in two subjects and published
 * results, one of them revised. `empty` gives a term with nothing recorded yet.
 */
const TERM = { id: "t1", name: "2026-27 Odd semester", is_current: true };
const CS301 = { id: "s1", code: "CS301", name: "Compilers" };
const MA201 = { id: "s2", code: "MA201", name: "Probability and Statistics" };
const HS110 = { id: "s3", code: "HS110", name: "Technical Writing" };
const section = (subject: { id: string }) => ({ id: `${subject.id}-A`, name: "A" });

function reply(route: Route, body: unknown, status = 200) {
  return route.fulfill({ status, contentType: "application/json", headers: { "X-Request-ID": "e2e-academic" }, body: JSON.stringify(body) });
}

export async function mockAcademicApi(page: Page, { empty = false }: { empty?: boolean } = {}) {
  const cls = (weekday: number, starts_at: string, ends_at: string, subject: typeof CS301, room: string) => ({ weekday, starts_at, ends_at, room, section: section(subject), subject });
  const classes = empty
    ? []
    : [1, 3, 5].flatMap((d) => [cls(d, "09:00:00", "10:00:00", CS301, "C-103"), cls(d, "11:15:00", "12:15:00", MA201, "B-12")]).concat([
        cls(2, "10:00:00", "11:00:00", HS110, "Library seminar room"),
        cls(4, "14:00:00", "16:00:00", CS301, "Compilers lab"),
      ]);
  const summary = (subject: typeof CS301, held: number, attended: number, excused: number) => ({
    section: section(subject),
    subject,
    held,
    attended,
    excused,
    percentage: held - excused > 0 ? Math.round((1000 * attended) / (held - excused)) / 10 : null,
  });
  const attendance = empty ? [summary(CS301, 0, 0, 0)] : [summary(CS301, 12, 10, 1), summary(MA201, 9, 6, 0), summary(HS110, 0, 0, 0)];
  const result = (id: string, name: string, kind: string, max: number, held_on: string, score: number | null, extra: Record<string, unknown> = {}) => ({
    id,
    name,
    kind,
    max_score: max,
    held_on,
    published_at: "2026-10-21T12:00:00Z",
    score,
    absent: false,
    revised: false,
    ...extra,
  });

  await page.route("**/api/v1/campus/me/{timetable,attendance,results}**", (route) => {
    const path = new URL(route.request().url()).pathname.replace("/api/v1/campus/me/", "");
    if (path === "timetable") return reply(route, { term: TERM, is_demo: true, classes });
    if (path === "attendance") return reply(route, { term: TERM, is_demo: true, items: attendance });
    if (path === "results") {
      return reply(route, {
        term: TERM,
        is_demo: true,
        items: empty
          ? []
          : [
              {
                section: section(CS301),
                subject: CS301,
                assessments: [result("a1", "Quiz 1", "QUIZ", 20, "2026-09-02", 18.5), result("a2", "Mid-term", "MIDTERM", 50, "2026-10-05", 41, { revised: true })],
              },
              { section: section(MA201), subject: MA201, assessments: [result("a3", "Assignment 1", "ASSIGNMENT", 10, "2026-09-20", null, { absent: true })] },
            ],
      });
    }
    const [, sectionId] = path.split("/");
    const found = attendance.find((a) => a.section.id === sectionId);
    if (!found) return reply(route, { error: { code: "not_found", message: "Not found.", details: null, request_id: "x" } }, 404);
    const statuses = ["PRESENT", "PRESENT", "ABSENT", "EXCUSED", "PRESENT"];
    return reply(route, {
      ...found,
      term: TERM,
      is_demo: true,
      sessions: Array.from({ length: Math.min(found.held, 5) }, (_, i) => ({ held_on: `2026-10-${String(20 - i * 2).padStart(2, "0")}`, slot: 1 + (i % 2), status: statuses[i] })),
    });
  });
}
