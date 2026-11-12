import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import type { Me } from "@/features/auth/api";
import { MEMBER, NORTHFIELD_MEMBERSHIP, signedIn } from "@/test/auth";
import { envelope, json, mockFetch } from "@/test/http";
import { renderRoute } from "@/test/render";

const ME = "/api/v1/me";
const C = "/api/v1/campus";
const MINE = NORTHFIELD_MEMBERSHIP.id;
const FACULTY: Partial<Me> = { ...MEMBER, membership: { ...NORTHFIELD_MEMBERSHIP, kind: "FACULTY" }, capabilities: ["campus", "teaching"] };
const DEPT_ADMIN: Partial<Me> = {
  ...MEMBER,
  membership: { ...NORTHFIELD_MEMBERSHIP, kind: "STAFF" },
  roles: [{ role: "DEPARTMENT_ADMIN", department: NORTHFIELD_MEMBERSHIP.department }],
  capabilities: ["campus", "review_memberships", "moderate_community"],
};
const TERM = { id: "t1", name: "2026-27 Odd semester", is_current: true };
const SECTION = {
  id: "sec1",
  name: "A",
  term: TERM,
  subject: { id: "s1", code: "CS301", name: "Compilers" },
  department: { id: "d1", code: "CSE", name: "Computer Science" },
  instructors: [{ membership_id: MINE, display_name: "Aarav Nair" }],
  enrollment_count: 2,
};
const ENROLLMENTS = [
  { id: "e1", membership_id: "m1", display_name: "Ishita Verma", roll_number: null, department: SECTION.department },
  { id: "e2", membership_id: "m2", display_name: "Kabir Shah", roll_number: null, department: SECTION.department },
];

function bodyOf(fetchMock: ReturnType<typeof mockFetch>, method: string, path: string): unknown {
  const call = fetchMock.mock.calls.find(([input, init]) => input === path && init?.method === method);
  return typeof call?.[1]?.body === "string" ? (JSON.parse(call[1].body) as unknown) : undefined;
}

const session = (over: Record<string, unknown> = {}) => ({
  id: "ses1",
  section_id: "sec1",
  held_on: "2026-10-20",
  slot: 2,
  version: 1,
  recorded_by: { membership_id: MINE, display_name: "Aarav Nair" },
  counts: { present: 1, absent: 1, excused: 0 },
  edit: "faculty",
  edit_window_closes_at: "2026-10-22T05:00:00Z",
  created_at: "2026-10-20T05:00:00Z",
  updated_at: "2026-10-20T05:00:00Z",
  records: [
    { enrollment_id: "e1", membership_id: "m1", display_name: "Ishita Verma", status: "PRESENT" },
    { enrollment_id: "e2", membership_id: "m2", display_name: "Kabir Shah", status: "ABSENT" },
  ],
  ...over,
});

afterEach(() => window.history.replaceState(null, "", "/"));

/** The save bar's live counts line. */
const counts = () => screen.getByText((_, el) => el?.tagName === "P" && /^\d+ present/.test(el.textContent ?? ""));

describe("Teaching", () => {
  it("puts Teaching third for faculty and lists their sections", async () => {
    mockFetch({ [ME]: signedIn({}, FACULTY), [`${C}/teaching/sections`]: () => json({ term: TERM, items: [SECTION] }) });
    renderRoute("/teaching");
    const [rail] = await screen.findAllByRole("navigation", { name: "Main" });
    expect(within(rail!).getAllByRole("link").map((l) => l.textContent)).toEqual(["Home", "Notices", "Teaching", "Community", "Issues", "Account"]);
    const list = await screen.findByRole("list", { name: "Your sections" });
    expect(within(list).getByRole("link")).toHaveAttribute("href", "/teaching/sections/sec1");
    expect(list).toHaveTextContent("CS301 CompilersSection A · CSE2 students");
  });

  it("says when the faculty member teaches nothing this term", async () => {
    mockFetch({ [ME]: signedIn({}, FACULTY), [`${C}/teaching/sections`]: () => json({ term: TERM, items: [] }) });
    renderRoute("/teaching");
    expect(await screen.findByText("You aren't teaching any sections this term.")).toBeInTheDocument();
  });

  it("keeps students out", async () => {
    mockFetch({ [ME]: signedIn({}, { ...MEMBER, capabilities: ["campus", "academics"] }), [`${C}/me/timetable`]: () => json({ term: null, is_demo: false, classes: [] }) });
    const { router } = renderRoute("/teaching/sections/sec1");
    await waitFor(() => expect(router.state.location.pathname).toBe("/home"));
  });
});

describe("Taking attendance", () => {
  it("starts everyone Present, sets marks by key, shows counts and saves the whole class", async () => {
    const fetchMock = mockFetch({
      [ME]: signedIn({}, FACULTY),
      [`${C}/sections/sec1`]: () => json(SECTION),
      [`${C}/sections/sec1/enrollments?limit=100`]: () => json({ items: ENROLLMENTS, next_cursor: null }),
      [`POST ${C}/sections/sec1/attendance-sessions`]: () => json(session(), 201),
      [`${C}/attendance-sessions/ses1`]: () => json(session()),
    });
    renderRoute("/teaching/sections/sec1/attendance/new");
    const list = await screen.findByRole("list", { name: "Class list" });
    const kabir = within(list).getByRole("radiogroup", { name: "Kabir Shah" });
    expect(within(kabir).getByRole("radio", { name: "Present" })).toBeChecked();
    expect(counts()).toHaveTextContent("2 present · 0 absent · 0 excused");
    within(kabir).getByRole("radio", { name: "Present" }).focus();
    await userEvent.keyboard("a");
    expect(within(kabir).getByRole("radio", { name: "Absent" })).toBeChecked();
    expect(counts()).toHaveTextContent("1 present · 1 absent · 0 excused");
    await userEvent.selectOptions(screen.getByLabelText("Period"), "2");
    await userEvent.clear(screen.getByLabelText("Date"));
    await userEvent.type(screen.getByLabelText("Date"), "2026-10-20");
    await userEvent.click(screen.getByRole("button", { name: "Save attendance" }));
    expect(await screen.findByText("Attendance saved.")).toBeInTheDocument();
    expect(bodyOf(fetchMock, "POST", `${C}/sections/sec1/attendance-sessions`)).toEqual({
      held_on: "2026-10-20",
      slot: 2,
      records: [
        { enrollment_id: "e1", status: "PRESENT" },
        { enrollment_id: "e2", status: "ABSENT" },
      ],
    });
  });

  it("shows the server's 409 when the period is already recorded", async () => {
    mockFetch({
      [ME]: signedIn({}, FACULTY),
      [`${C}/sections/sec1`]: () => json(SECTION),
      [`${C}/sections/sec1/enrollments?limit=100`]: () => json({ items: ENROLLMENTS, next_cursor: null }),
      [`POST ${C}/sections/sec1/attendance-sessions`]: () => envelope(409, "session_exists", "Attendance for this section, date and period is already recorded."),
    });
    renderRoute("/teaching/sections/sec1/attendance/new");
    await userEvent.click(await screen.findByRole("button", { name: "Save attendance" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("already recorded");
  });

  it("sends only the changes when editing inside the window", async () => {
    const fetchMock = mockFetch({
      [ME]: signedIn({}, FACULTY),
      [`${C}/sections/sec1`]: () => json(SECTION),
      [`${C}/attendance-sessions/ses1`]: (init) => json(init?.method === "PATCH" ? session({ version: 2 }) : session()),
    });
    renderRoute("/teaching/sessions/ses1");
    const kabir = await screen.findByRole("radiogroup", { name: "Kabir Shah" });
    expect(screen.getByRole("button", { name: "Save 0 changes" })).toBeDisabled();
    await userEvent.click(within(kabir).getByRole("radio", { name: "Excused" }));
    await userEvent.click(screen.getByRole("button", { name: "Save 1 change" }));
    await waitFor(() => expect(bodyOf(fetchMock, "PATCH", `${C}/attendance-sessions/ses1`)).toEqual({ version: 1, records: [{ enrollment_id: "e2", status: "EXCUSED" }] }));
  });

  it("is read-only once the window closes, saying who can still correct it", async () => {
    mockFetch({ [ME]: signedIn({}, FACULTY), [`${C}/sections/sec1`]: () => json(SECTION), [`${C}/attendance-sessions/ses1`]: () => json(session({ edit: "window_closed" })) });
    renderRoute("/teaching/sessions/ses1");
    expect(await screen.findByText("Edit window closed — ask your department admin")).toBeInTheDocument();
    expect(screen.getByText(/for 48 hours after recording it/)).toBeInTheDocument();
    for (const radio of screen.getAllByRole("radio")) expect(radio).toBeDisabled();
    expect(screen.queryByRole("button", { name: /Save/ })).not.toBeInTheDocument();
  });

  it("asks a department admin for a reason before a correction", async () => {
    const fetchMock = mockFetch({
      [ME]: signedIn({}, DEPT_ADMIN),
      [`${C}/sections/sec1`]: () => json(SECTION),
      [`${C}/attendance-sessions/ses1`]: (init) => json(init?.method === "PATCH" ? session({ version: 2, edit: "correction" }) : session({ edit: "correction" })),
    });
    renderRoute("/teaching/sessions/ses1");
    const kabir = await screen.findByRole("radiogroup", { name: "Kabir Shah" });
    await userEvent.click(within(kabir).getByRole("radio", { name: "Present" }));
    await userEvent.click(screen.getByRole("button", { name: "Save 1 change" }));
    expect(screen.getByText("Give a reason for the correction.")).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText("Reason for the correction"), "Medical certificate");
    await userEvent.click(screen.getByRole("button", { name: "Save 1 change" }));
    await waitFor(() => expect(bodyOf(fetchMock, "PATCH", `${C}/attendance-sessions/ses1`)).toEqual({ version: 1, records: [{ enrollment_id: "e2", status: "PRESENT" }], reason: "Medical certificate" }));
  });
});

describe("Assessments", () => {
  const assessment = (over: Record<string, unknown> = {}) => ({
    id: "as1",
    section_id: "sec1",
    name: "Quiz 1",
    kind: "QUIZ",
    max_score: 20,
    held_on: "2026-10-20",
    version: 1,
    published_at: null,
    published_by: null,
    counts: { enrolled: 2, entered: 0, absent: 0 },
    actions: { enter_scores: true, publish: true },
    created_at: "2026-10-20T05:00:00Z",
    ...over,
  });
  const row = (id: string, name: string, score: number | null, absent = false, revised = false) => ({ enrollment_id: id, membership_id: `m-${id}`, display_name: name, score, absent, revised });

  it("enters scores and absences, checks the maximum, then publishes", async () => {
    let state = { assessment: assessment(), rows: [row("e1", "Ishita Verma", null), row("e2", "Kabir Shah", null)] };
    const fetchMock = mockFetch({
      [ME]: signedIn({}, FACULTY),
      [`${C}/assessments/as1/results`]: (init) => {
        if (init?.method === "PUT") state = { assessment: assessment({ version: 2, counts: { enrolled: 2, entered: 2, absent: 1 } }), rows: [row("e1", "Ishita Verma", 18.5), row("e2", "Kabir Shah", null, true)] };
        return json(state);
      },
      [`POST ${C}/assessments/as1/publish`]: () => {
        state = { ...state, assessment: assessment({ version: 3, published_at: "2026-10-21T12:00:00Z", published_by: { membership_id: MINE, display_name: "Aarav Nair" }, actions: { enter_scores: true, publish: false } }) };
        return json(state.assessment);
      },
      [`${C}/sections/sec1/assessments`]: () => json({ items: [], next_cursor: null }),
    });
    renderRoute("/teaching/assessments/as1");
    expect(await screen.findByText("Students can't see these scores until you publish them.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Publish" })).toBeDisabled();
    const ishita = screen.getByLabelText("Score for Ishita Verma");
    await userEvent.type(ishita, "21");
    expect(screen.getByText("The most is 20.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Save scores" })).toBeDisabled();
    await userEvent.clear(ishita);
    await userEvent.type(ishita, "18.5");
    await userEvent.click(screen.getByLabelText("Kabir Shah was absent"));
    await userEvent.click(screen.getByRole("button", { name: "Save scores" }));
    expect(await screen.findByText("Scores saved.")).toBeInTheDocument();
    expect(bodyOf(fetchMock, "PUT", `${C}/assessments/as1/results`)).toEqual({
      version: 1,
      results: [
        { enrollment_id: "e1", score: "18.5", absent: false },
        { enrollment_id: "e2", score: null, absent: true },
      ],
    });
    await userEvent.click(screen.getByRole("button", { name: "Publish" }));
    const dialog = screen.getByRole("dialog", { name: "Publish these results?" });
    await userEvent.click(within(dialog).getByRole("button", { name: "Publish results" }));
    expect(await screen.findByText("Published. All 2 students have been told.")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(`${C}/assessments/as1/publish`, expect.objectContaining({ method: "POST", body: JSON.stringify({ version: 2 }) }));
  });

  it("asks for a reason before changing a published score", async () => {
    const published = assessment({ version: 3, published_at: "2026-10-21T12:00:00Z", published_by: { membership_id: MINE, display_name: "Aarav Nair" }, counts: { enrolled: 1, entered: 1, absent: 0 }, actions: { enter_scores: true, publish: false } });
    const fetchMock = mockFetch({
      [ME]: signedIn({}, FACULTY),
      [`${C}/assessments/as1/results`]: (init) => json({ assessment: init?.method === "PUT" ? { ...published, version: 4 } : published, rows: [row("e1", "Ishita Verma", init?.method === "PUT" ? 19.5 : 18.5, false, init?.method === "PUT")] }),
      [`${C}/sections/sec1/assessments`]: () => json({ items: [], next_cursor: null }),
    });
    renderRoute("/teaching/assessments/as1");
    const ishita = await screen.findByLabelText("Score for Ishita Verma");
    expect(screen.queryByRole("button", { name: "Publish" })).not.toBeInTheDocument();
    await userEvent.clear(ishita);
    await userEvent.type(ishita, "19.5");
    await userEvent.click(screen.getByRole("button", { name: "Save scores" }));
    const dialog = screen.getByRole("dialog", { name: "Change 1 published result?" });
    await userEvent.type(within(dialog).getByLabelText("Reason"), "Re-marked question 4");
    await userEvent.click(within(dialog).getByRole("button", { name: "Save changes" }));
    expect(await screen.findByText("Changes saved. The students have been told their results were revised.")).toBeInTheDocument();
    expect(bodyOf(fetchMock, "PUT", `${C}/assessments/as1/results`)).toEqual({ version: 3, results: [{ enrollment_id: "e1", score: "19.5", absent: false }], reason: "Re-marked question 4" });
    expect(screen.getByText("Revised")).toBeInTheDocument();
  });

  it("corrects a draft's details and shows the server's reason when the maximum is too low", async () => {
    let calls = 0;
    const fetchMock = mockFetch({
      [ME]: signedIn({}, FACULTY),
      [`${C}/assessments/as1/results`]: () => json({ assessment: assessment({ counts: { enrolled: 2, entered: 1, absent: 0 } }), rows: [row("e1", "Ishita Verma", 18.5), row("e2", "Kabir Shah", null)] }),
      [`PATCH ${C}/assessments/as1`]: () =>
        ++calls === 1
          ? envelope(422, "validation_error", "Check the highlighted fields.", [{ field: "max_score", message: "A score of 18.50 is already entered; the maximum can't be lower." }])
          : json(assessment({ name: "Quiz 1 (retest)", version: 2 })),
      [`${C}/sections/sec1/assessments`]: () => json({ items: [], next_cursor: null }),
    });
    renderRoute("/teaching/assessments/as1");
    await userEvent.click(await screen.findByRole("button", { name: "Edit details" }));
    const form = screen.getByRole("form", { name: "Edit assessment" });
    await userEvent.clear(within(form).getByLabelText("Maximum score"));
    await userEvent.type(within(form).getByLabelText("Maximum score"), "15");
    await userEvent.click(within(form).getByRole("button", { name: "Save details" }));
    expect(await within(form).findByText(/the maximum can't be lower/)).toBeInTheDocument();
    await userEvent.clear(within(form).getByLabelText("Maximum score"));
    await userEvent.type(within(form).getByLabelText("Maximum score"), "20");
    await userEvent.clear(within(form).getByLabelText("Name"));
    await userEvent.type(within(form).getByLabelText("Name"), "Quiz 1 (retest)");
    await userEvent.click(within(form).getByRole("button", { name: "Save details" }));
    expect(await screen.findByText("Details saved.")).toBeInTheDocument();
    const patches = fetchMock.mock.calls.filter(([path, init]) => path === `${C}/assessments/as1` && init?.method === "PATCH");
    expect(JSON.parse(patches[1]![1]!.body as string)).toEqual({ version: 1, name: "Quiz 1 (retest)", kind: "QUIZ", max_score: "20", held_on: "2026-10-20" });
  });

  it("deletes a draft after confirming and goes back to the assessments", async () => {
    mockFetch({
      [ME]: signedIn({}, FACULTY),
      [`${C}/assessments/as1/results`]: () => json({ assessment: assessment({ counts: { enrolled: 2, entered: 1, absent: 0 } }), rows: [row("e1", "Ishita Verma", 18.5), row("e2", "Kabir Shah", null)] }),
      [`DELETE ${C}/assessments/as1`]: () => new Response(null, { status: 204 }),
      [`${C}/sections/sec1`]: () => json(SECTION),
      [`${C}/sections/sec1/assessments`]: () => json({ items: [], next_cursor: null }),
      [`${C}/sections/sec1/attendance-sessions`]: () => json({ items: [], next_cursor: null }),
    });
    const { router } = renderRoute("/teaching/assessments/as1");
    await userEvent.click(await screen.findByRole("button", { name: "Delete" }));
    const dialog = screen.getByRole("dialog", { name: "Delete Quiz 1?" });
    expect(dialog).toHaveTextContent("Its 1 entered scores go with it.");
    await userEvent.click(within(dialog).getByRole("button", { name: "Delete assessment" }));
    await waitFor(() => expect(router.state.location.pathname).toBe("/teaching/sections/sec1"));
    expect(router.state.location.search).toBe("?tab=assessments");
  });

  it("offers no edit or delete once published", async () => {
    mockFetch({
      [ME]: signedIn({}, FACULTY),
      [`${C}/assessments/as1/results`]: () => json({ assessment: assessment({ published_at: "2026-10-21T12:00:00Z", published_by: { membership_id: MINE, display_name: "Aarav Nair" }, actions: { enter_scores: true, publish: false } }), rows: [row("e1", "Ishita Verma", 18.5)] }),
    });
    renderRoute("/teaching/assessments/as1");
    expect(await screen.findByText("Published")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Edit details" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Delete" })).not.toBeInTheDocument();
  });

  it("shows a department admin the scores read-only, with Publish", async () => {
    mockFetch({
      [ME]: signedIn({}, DEPT_ADMIN),
      [`${C}/assessments/as1/results`]: () => json({ assessment: assessment({ actions: { enter_scores: false, publish: true }, counts: { enrolled: 1, entered: 1, absent: 0 } }), rows: [row("e1", "Ishita Verma", 18.5)] }),
    });
    renderRoute("/teaching/assessments/as1");
    expect(await screen.findByText(/Only the section's faculty enter scores/)).toBeInTheDocument();
    expect(screen.queryByLabelText("Score for Ishita Verma")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Publish" })).toBeEnabled();
  });
});
