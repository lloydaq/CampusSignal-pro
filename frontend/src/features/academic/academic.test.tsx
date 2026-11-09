import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import type { Me } from "@/features/auth/api";
import { MEMBER, signedIn } from "@/test/auth";
import { envelope, json, mockFetch } from "@/test/http";
import { renderRoute } from "@/test/render";

import { collegeWeekday, formatScore, percent } from "./format";

const ME = "/api/v1/me";
const C = "/api/v1/campus";
const STUDENT: Partial<Me> = { ...MEMBER, capabilities: ["campus", "academics"] };
const TERM = { id: "t1", name: "2026-27 Odd semester", is_current: true };
const CS301 = { id: "s1", code: "CS301", name: "Compilers" };
const MA201 = { id: "s2", code: "MA201", name: "Probability" };

const cls = (weekday: number, starts_at: string, ends_at: string, subject = CS301, room = "C-103") => ({
  weekday,
  starts_at,
  ends_at,
  room,
  section: { id: `${subject.id}-A`, name: "A" },
  subject,
});

afterEach(() => window.history.replaceState(null, "", "/"));

describe("Academics navigation", () => {
  it("puts Academics third for students, in the rail and the phone bar", async () => {
    mockFetch({ [ME]: signedIn({}, STUDENT), [`${C}/me/timetable`]: () => json({ term: TERM, is_demo: false, classes: [] }) });
    renderRoute("/academics");
    const [rail, bar] = await screen.findAllByRole("navigation", { name: "Main" });
    expect(within(rail!).getAllByRole("link").map((l) => l.textContent)).toEqual(["Home", "Notices", "Academics", "Community", "Issues", "Account"]);
    expect(within(bar!).getAllByRole("link").map((l) => l.textContent)).toEqual(["Home", "Notices", "Academics", "Community"]);
    const tabs = screen.getByRole("navigation", { name: "Academics" });
    expect(within(tabs).getAllByRole("link").map((l) => l.textContent)).toEqual(["Timetable", "Attendance", "Results"]);
    await waitFor(() => expect(within(tabs).getByRole("link", { name: "Timetable" })).toHaveAttribute("aria-current", "page"));
  });

  it("sends anyone without Academics (faculty, staff) to their home", async () => {
    mockFetch({ [ME]: signedIn({}, MEMBER), [`${C}/home`]: () => json({}) });
    const { router } = renderRoute("/academics/results");
    await waitFor(() => expect(router.state.location.pathname).toBe("/home"));
  });
});

describe("Timetable", () => {
  it("lists a day's classes in time order and switches days", async () => {
    mockFetch({
      [ME]: signedIn({}, STUDENT),
      [`${C}/me/timetable`]: () =>
        json({ term: TERM, is_demo: true, classes: [cls(2, "11:00:00", "12:00:00", MA201, "B-12"), cls(2, "09:00:00", "10:00:00"), cls(4, "09:00:00", "10:00:00")] }),
    });
    renderRoute("/academics/timetable");
    expect(await screen.findByText("2026-27 Odd semester")).toBeInTheDocument();
    expect(screen.getByText("Demo data")).toBeInTheDocument();
    const days = screen.getByRole("group", { name: "Day" });
    expect(within(days).getAllByRole("button")).toHaveLength(6); // no Sunday classes, so Mon–Sat
    await userEvent.click(within(days).getByRole("button", { name: /Tue/ }));
    const list = screen.getByRole("list", { name: "Classes" });
    expect(within(list).getAllByRole("listitem").map((li) => li.textContent)).toEqual([
      "09:00–10:00CS301 CompilersC-103 · Section A",
      "11:00–12:00MA201 ProbabilityB-12 · Section A",
    ]);
    await userEvent.click(within(days).getByRole("button", { name: /Mon/ }));
    expect(screen.getByText("No classes")).toBeInTheDocument();
    // The desktop grid has a row per time and a column per day.
    const grid = screen.getByRole("table", { name: "Your week" });
    expect(within(grid).getAllByRole("rowheader").map((r) => r.textContent)).toEqual(["09:00–10:00", "11:00–12:00"]);
  });

  it("says when the college has no current term", async () => {
    mockFetch({ [ME]: signedIn({}, STUDENT), [`${C}/me/timetable`]: () => json({ term: null, is_demo: false, classes: [] }) });
    renderRoute("/academics/timetable");
    expect(await screen.findByText("Your college hasn't set up the current term yet.")).toBeInTheDocument();
  });

  it("has an empty state and an error state", async () => {
    mockFetch({ [ME]: signedIn({}, STUDENT), [`${C}/me/timetable`]: () => json({ term: TERM, is_demo: false, classes: [] }) });
    renderRoute("/academics/timetable");
    expect(await screen.findByText("No classes in your timetable yet.")).toBeInTheDocument();
    expect(screen.queryByText("Demo data")).not.toBeInTheDocument();
  });

  it("shows an error with a retry", async () => {
    mockFetch({ [ME]: signedIn({}, STUDENT), [`${C}/me/timetable`]: () => envelope(500, "internal_error", "Something went wrong on our side.") });
    renderRoute("/academics/timetable");
    expect(await screen.findByText("Couldn't load your timetable.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Try again/ })).toBeInTheDocument();
  });
});

describe("Attendance", () => {
  const summary = (subject: typeof CS301, held: number, attended: number, excused: number, percentage: number | null) => ({
    section: { id: `${subject.id}-A`, name: "A" },
    subject,
    held,
    attended,
    excused,
    percentage,
  });

  it("shows held, attended and the percentage per subject, linking to its sessions", async () => {
    mockFetch({
      [ME]: signedIn({}, STUDENT),
      [`${C}/me/attendance`]: () => json({ term: TERM, is_demo: false, items: [summary(CS301, 3, 1, 1, 50), summary(MA201, 0, 0, 0, null)] }),
      [`${C}/me/attendance/s1-A`]: () =>
        json({
          ...summary(CS301, 3, 1, 1, 50),
          term: TERM,
          is_demo: false,
          sessions: [
            { held_on: "2026-10-21", slot: 2, status: "EXCUSED" },
            { held_on: "2026-10-20", slot: 1, status: "ABSENT" },
            { held_on: "2026-10-19", slot: 1, status: "PRESENT" },
          ],
        }),
    });
    renderRoute("/academics/attendance");
    const table = await screen.findByRole("table", { name: "Attendance by subject" });
    const rows = within(table).getAllByRole("row").slice(1);
    expect(rows.map((r) => within(r).getAllByRole("cell").map((c) => c.textContent))).toEqual([
      ["3", "1", "50%"],
      ["0", "0", "—"],
    ]);
    await userEvent.click(within(table).getByRole("link", { name: /CS301/ }));
    const sessions = await screen.findByRole("list", { name: "Sessions" });
    expect(within(sessions).getAllByRole("listitem").map((li) => li.textContent)).toEqual([
      "Wed, 21 Oct, 2026 · Period 2Excused",
      "Tue, 20 Oct, 2026 · Period 1Absent",
      "Mon, 19 Oct, 2026 · Period 1Present",
    ]);
    expect(screen.getByText(/Attended/)).toHaveTextContent("Attended 1 of 2 counted (1 excused) · 50%");
    await userEvent.click(screen.getByRole("link", { name: "All subjects" }));
    expect(await screen.findByRole("table", { name: "Attendance by subject" })).toBeInTheDocument();
  });

  it("says when nothing has been recorded this term", async () => {
    mockFetch({ [ME]: signedIn({}, STUDENT), [`${C}/me/attendance`]: () => json({ term: TERM, is_demo: false, items: [summary(CS301, 0, 0, 0, null)] }) });
    renderRoute("/academics/attendance");
    expect(await screen.findByText("No attendance has been recorded for this term yet.")).toBeInTheDocument();
  });

  it("shows another section's page as an error, never someone else's data", async () => {
    mockFetch({ [ME]: signedIn({}, STUDENT), [`${C}/me/attendance/zzz`]: () => envelope(404, "not_found", "Not found.") });
    renderRoute("/academics/attendance/zzz");
    expect(await screen.findByText("Couldn't load this subject's attendance.")).toBeInTheDocument();
  });
});

describe("Results", () => {
  const result = (over: Record<string, unknown>) => ({
    id: "a1",
    name: "Quiz 1",
    kind: "QUIZ",
    max_score: 20,
    held_on: "2026-10-20",
    published_at: "2026-10-21T12:00:00Z",
    score: 18.5,
    absent: false,
    revised: false,
    ...over,
  });

  it("groups published results by subject, with Revised and Absent", async () => {
    mockFetch({
      [ME]: signedIn({}, STUDENT),
      [`${C}/me/results`]: () =>
        json({
          term: TERM,
          is_demo: false,
          items: [
            { section: { id: "s1-A", name: "A" }, subject: CS301, assessments: [result({}), result({ id: "a2", name: "Mid-term", kind: "MIDTERM", max_score: 50, score: 41, revised: true })] },
            { section: { id: "s2-A", name: "A" }, subject: MA201, assessments: [result({ id: "a3", name: "Assignment 1", kind: "ASSIGNMENT", score: null, absent: true })] },
          ],
        }),
    });
    renderRoute("/academics/results");
    const cs = await screen.findByRole("region", { name: "CS301 Compilers" });
    const rows = within(cs).getAllByRole("row").slice(1);
    expect(within(rows[0]!).getAllByRole("cell").at(-1)).toHaveTextContent("18.5 / 20");
    expect(within(rows[1]!).getByText("Revised")).toBeInTheDocument();
    expect(within(rows[0]!).queryByText("Revised")).not.toBeInTheDocument();
    const ma = screen.getByRole("region", { name: "MA201 Probability" });
    expect(within(ma).getByText("Absent")).toBeInTheDocument();
  });

  it("says when nothing is published", async () => {
    mockFetch({ [ME]: signedIn({}, STUDENT), [`${C}/me/results`]: () => json({ term: TERM, is_demo: false, items: [] }) });
    renderRoute("/academics/results");
    expect(await screen.findByText("No results have been published yet.")).toBeInTheDocument();
  });
});

describe("formatting", () => {
  it("formats scores, percentages and today's weekday", () => {
    expect([formatScore(18.5), formatScore(20), formatScore(7.25)]).toEqual(["18.5", "20", "7.25"]);
    expect(percent({ held: 0, attended: 0, excused: 0, percentage: null })).toBe("—");
    // 2026-10-21 20:00 UTC is already Thursday in Asia/Kolkata.
    expect(collegeWeekday("Asia/Kolkata", new Date("2026-10-21T20:00:00Z"))).toBe(4);
    expect(collegeWeekday("UTC", new Date("2026-10-21T20:00:00Z"))).toBe(3);
  });
});
