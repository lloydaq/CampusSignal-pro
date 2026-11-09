import type { Page, Route } from "@playwright/test";

/**
 * A synthetic faculty member's teaching (backend app/api/v1/academic.py): Aarav Nair teaches
 * CS301 A to four students. One session recorded today (editable), one last week (window
 * closed); a draft quiz with no scores and a published mid-term. Saves update the state.
 */
const ME = "5b1c0d5e-0000-4000-8000-000000000001";
const TERM = { id: "t1", name: "2026-27 Odd semester", is_current: true };
const CSE = { id: "d1", code: "CSE", name: "Computer Science" };
const SECTION = { id: "sec1", name: "A", term: TERM, subject: { id: "s1", code: "CS301", name: "Compilers" }, department: CSE, instructors: [{ membership_id: ME, display_name: "Aarav Nair" }], enrollment_count: 4 };
const NAMES = ["Ishita Verma", "Kabir Shah", "Meera Iyer", "Rohan Gupta"];
const ENROLLMENTS = NAMES.map((name, i) => ({ id: `e${i + 1}`, membership_id: `m${i + 1}`, display_name: name, roll_number: null, department: CSE }));

function reply(route: Route, body: unknown, status = 200) {
  return route.fulfill({ status, contentType: "application/json", headers: { "X-Request-ID": "e2e-teaching" }, body: JSON.stringify(body) });
}

export async function mockTeachingApi(page: Page) {
  const record = (id: string, held_on: string, slot: number, edit: string, statuses: string[]) => ({
    id,
    section_id: "sec1",
    held_on,
    slot,
    version: 1,
    recorded_by: { membership_id: ME, display_name: "Aarav Nair" },
    edit,
    edit_window_closes_at: "2026-10-23T05:00:00Z",
    created_at: "2026-10-21T05:00:00Z",
    updated_at: "2026-10-21T05:00:00Z",
    records: ENROLLMENTS.map((e, i) => ({ enrollment_id: e.id, membership_id: e.membership_id, display_name: e.display_name, status: statuses[i] })),
  });
  const sessions = [record("ses1", "2026-10-21", 1, "faculty", ["PRESENT", "ABSENT", "PRESENT", "PRESENT"]), record("ses2", "2026-10-14", 2, "window_closed", ["PRESENT", "PRESENT", "EXCUSED", "ABSENT"])];
  const withCounts = (s: (typeof sessions)[number]) => {
    const n = (status: string) => s.records.filter((r) => r.status === status).length;
    const rest: Partial<typeof s> = { ...s };
    delete rest.records;
    return { ...rest, counts: { present: n("PRESENT"), absent: n("ABSENT"), excused: n("EXCUSED") } };
  };
  const detail = (s: (typeof sessions)[number]) => ({ ...withCounts(s), records: s.records });
  const assessment = (id: string, name: string, kind: string, max: number, published: boolean, scores: (number | null)[]) => ({
    id,
    section_id: "sec1",
    name,
    kind,
    max_score: max,
    held_on: "2026-10-20",
    version: 1,
    published_at: published ? "2026-10-21T06:00:00Z" : null,
    published_by: published ? { membership_id: ME, display_name: "Aarav Nair" } : null,
    actions: { enter_scores: true, publish: !published },
    created_at: "2026-10-20T05:00:00Z",
    scores,
  });
  const assessments = [assessment("as1", "Quiz 1", "QUIZ", 20, false, [null, null, null, null]), assessment("as2", "Mid-term", "MIDTERM", 50, true, [41, 37.5, 44, 29])];
  const out = (a: (typeof assessments)[number]) => {
    const { scores, ...rest } = a;
    return { ...rest, counts: { enrolled: 4, entered: scores.filter((s) => s !== null).length, absent: 0 } };
  };
  const results = (a: (typeof assessments)[number]) => ({
    assessment: out(a),
    rows: ENROLLMENTS.map((e, i) => ({ enrollment_id: e.id, membership_id: e.membership_id, display_name: e.display_name, score: a.scores[i] ?? null, absent: false, revised: false })),
  });

  await page.route("**/api/v1/campus/{teaching,sections,attendance-sessions,assessments}/**", (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname.replace("/api/v1/campus", "");
    const method = request.method();
    if (path === "/teaching/sections") return reply(route, { term: TERM, items: [SECTION] });
    if (path === "/sections/sec1") return reply(route, SECTION);
    if (path === "/sections/sec1/enrollments") return reply(route, { items: ENROLLMENTS, next_cursor: null });
    if (path === "/sections/sec1/attendance-sessions" && method === "GET") return reply(route, { items: sessions.map(withCounts), next_cursor: null });
    if (path === "/sections/sec1/attendance-sessions") {
      const body = request.postDataJSON() as { held_on: string; slot: number; records: { status: string }[] };
      const created = record(`ses${sessions.length + 1}`, body.held_on, body.slot, "faculty", body.records.map((r) => r.status));
      sessions.unshift(created);
      return reply(route, detail(created), 201);
    }
    const one = path.match(/^\/attendance-sessions\/(\w+)$/);
    if (one) {
      const s = sessions.find((x) => x.id === one[1]);
      return s ? reply(route, detail(s)) : reply(route, { error: { code: "not_found", message: "Not found.", details: null, request_id: "x" } }, 404);
    }
    if (path === "/sections/sec1/assessments") return reply(route, { items: assessments.map(out), next_cursor: null });
    const res = path.match(/^\/assessments\/(\w+)\/(results|publish)$/);
    const a = res && assessments.find((x) => x.id === res[1]);
    if (a && res[2] === "results" && method === "PUT") {
      const body = request.postDataJSON() as { results: { enrollment_id: string; score: string | null }[] };
      for (const r of body.results) a.scores[ENROLLMENTS.findIndex((e) => e.id === r.enrollment_id)] = r.score === null ? null : Number(r.score);
      a.version += 1;
      return reply(route, results(a));
    }
    if (a && res[2] === "results") return reply(route, results(a));
    if (a && res[2] === "publish") {
      Object.assign(a, { published_at: "2026-10-21T12:00:00Z", published_by: { membership_id: ME, display_name: "Aarav Nair" }, actions: { enter_scores: true, publish: false }, version: a.version + 1 });
      return reply(route, out(a));
    }
    return route.abort("blockedbyclient");
  });
}
