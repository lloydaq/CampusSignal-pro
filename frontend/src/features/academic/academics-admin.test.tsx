import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import type { Me } from "@/features/auth/api";
import { MEMBER, NORTHFIELD_MEMBERSHIP, signedIn } from "@/test/auth";
import { envelope, json, mockFetch, noContent } from "@/test/http";
import { renderRoute } from "@/test/render";

import { rollNumbersCsv } from "./setupApi";

const ME = "/api/v1/me";
const C = "/api/v1/campus";
const CSE = { id: "d1", code: "CSE", name: "Computer Science" };
const MECH = { id: "d2", code: "MECH", name: "Mechanical" };
const COLLEGE_ADMIN: Partial<Me> = {
  ...MEMBER,
  membership: { ...NORTHFIELD_MEMBERSHIP, kind: "STAFF", department: null },
  roles: [{ role: "COLLEGE_ADMIN", department: null }],
  capabilities: ["campus", "manage_college", "review_memberships", "moderate_community", "manage_academics"],
};
const CSE_ADMIN: Partial<Me> = {
  ...MEMBER,
  membership: { ...NORTHFIELD_MEMBERSHIP, kind: "STAFF" },
  roles: [{ role: "DEPARTMENT_ADMIN", department: CSE }],
  capabilities: ["campus", "review_memberships", "moderate_community", "manage_academics"],
};
const TERMS = [
  { id: "t2", name: "2026-27 Odd semester", is_current: true, starts_on: "2026-07-01", ends_on: "2026-12-15" },
  { id: "t1", name: "2025-26 Even semester", is_current: false, starts_on: "2026-01-05", ends_on: "2026-05-30" },
];
const SUBJECTS = [{ id: "s1", code: "CS301", name: "Compilers", department: CSE }];
const SECTION = {
  id: "sec1",
  name: "A",
  term: TERMS[0],
  subject: { id: "s1", code: "CS301", name: "Compilers" },
  department: CSE,
  instructors: [] as { membership_id: string; display_name: string }[],
  enrollment_count: 0,
};
const page = <T,>(items: T[]) => json({ items, next_cursor: null });

function bodyOf(fetchMock: ReturnType<typeof mockFetch>, method: string, path: string): unknown {
  const call = fetchMock.mock.calls.find(([input, init]) => input === path && init?.method === method);
  return typeof call?.[1]?.body === "string" ? (JSON.parse(call[1].body) as unknown) : undefined;
}

afterEach(() => window.history.replaceState(null, "", "/"));

describe("Manage → Academics", () => {
  it("is a Manage tab for department admins, listing the current term's sections", async () => {
    mockFetch({
      [ME]: signedIn({}, CSE_ADMIN),
      [`${C}/terms`]: () => json({ items: TERMS }),
      [`${C}/subjects?limit=100`]: () => page(SUBJECTS),
      [`${C}/sections?term_id=t2`]: () => page([SECTION]),
      [`${C}/sections?term_id=t1`]: () => page([]),
    });
    renderRoute("/manage/academics");
    const tabs = await screen.findByRole("navigation", { name: "Manage" });
    expect(within(tabs).getAllByRole("link").map((l) => l.textContent)).toEqual(["Requests", "Members", "Moderation", "Academics"]);
    const table = await screen.findByRole("table", { name: "Sections" });
    expect(within(table).getByRole("link", { name: /CS301/ })).toHaveAttribute("href", "/manage/academics/sections/sec1");
    expect(table).toHaveTextContent("None assigned");
    await userEvent.selectOptions(screen.getByLabelText("Term"), "t1");
    expect(await screen.findByText("No sections in this term yet.")).toBeInTheDocument();
  });

  it("adds a section to the chosen term", async () => {
    const fetchMock = mockFetch({
      [ME]: signedIn({}, CSE_ADMIN),
      [`${C}/terms`]: () => json({ items: TERMS }),
      [`${C}/subjects?limit=100`]: () => page(SUBJECTS),
      [`${C}/sections?term_id=t2`]: () => page([]),
      [`POST ${C}/sections`]: () => json(SECTION, 201),
    });
    renderRoute("/manage/academics");
    const form = await screen.findByRole("form", { name: "Add section" });
    await userEvent.selectOptions(within(form).getByLabelText("Subject"), "s1");
    await userEvent.type(within(form).getByLabelText("Section name"), "A");
    await userEvent.click(within(form).getByRole("button", { name: "Add section" }));
    await waitFor(() => expect(bodyOf(fetchMock, "POST", `${C}/sections`)).toEqual({ term_id: "t2", subject_id: "s1", name: "A" }));
  });

  it("offers a department admin only their own departments for new subjects", async () => {
    const fetchMock = mockFetch({
      [ME]: signedIn({}, CSE_ADMIN),
      [`${C}/subjects?limit=100`]: () => page(SUBJECTS),
      [`POST ${C}/subjects`]: () => envelope(409, "subject_code_taken", "A subject with this code already exists."),
    });
    renderRoute("/manage/academics?view=subjects");
    const form = await screen.findByRole("form", { name: "Add subject" });
    expect(within(within(form).getByLabelText("Department")).getAllByRole("option").map((o) => o.textContent)).toEqual(["CSE Computer Science"]);
    await userEvent.type(within(form).getByLabelText("Code"), "CS301");
    await userEvent.type(within(form).getByLabelText("Name"), "Compilers");
    await userEvent.click(within(form).getByRole("button", { name: "Add subject" }));
    expect(await within(form).findByRole("alert")).toHaveTextContent("already exists");
    expect(bodyOf(fetchMock, "POST", `${C}/subjects`)).toEqual({ department_id: "d1", code: "CS301", name: "Compilers" });
    expect(screen.getByRole("table", { name: "Subjects" })).toHaveTextContent("CS301");
  });

  it("lets college admins add terms and choose the current one; department admins only read", async () => {
    const fetchMock = mockFetch({
      [ME]: signedIn({}, COLLEGE_ADMIN),
      [`${C}/terms`]: () => json({ items: TERMS }),
      [`${C}/departments`]: () => json({ items: [CSE, MECH] }),
      [`${C}/settings`]: () => json({ attendance_edit_window_hours: 48 }),
      [`PATCH ${C}/terms/t1`]: () => json({ ...TERMS[1], is_current: true }),
    });
    renderRoute("/manage/academics?view=terms");
    const table = await screen.findByRole("table", { name: "Terms" });
    expect(within(table).getByText("Current")).toBeInTheDocument();
    await userEvent.click(within(table).getByRole("button", { name: "Make current" }));
    await waitFor(() => expect(bodyOf(fetchMock, "PATCH", `${C}/terms/t1`)).toEqual({ is_current: true }));
    expect(screen.getByRole("form", { name: "Add term" })).toBeInTheDocument();
  });

  it("lets college admins change the attendance edit window (1 to 720 hours)", async () => {
    const fetchMock = mockFetch({
      [ME]: signedIn({}, COLLEGE_ADMIN),
      [`${C}/terms`]: () => json({ items: TERMS }),
      [`${C}/settings`]: (init) => json({ attendance_edit_window_hours: init?.method === "PATCH" ? 24 : 48 }),
    });
    renderRoute("/manage/academics?view=terms");
    const form = await screen.findByRole("form", { name: "Attendance edit window" });
    const field = within(form).getByLabelText("Attendance edit window (hours)");
    expect(field).toHaveValue("48");
    expect(within(form).getByRole("button", { name: "Save" })).toBeDisabled();
    await userEvent.clear(field);
    await userEvent.type(field, "721");
    expect(within(form).getByText("Use a whole number from 1 to 720 (30 days).")).toBeInTheDocument();
    expect(within(form).getByRole("button", { name: "Save" })).toBeDisabled();
    await userEvent.clear(field);
    await userEvent.type(field, "24");
    await userEvent.click(within(form).getByRole("button", { name: "Save" }));
    expect(await within(form).findByText(/Saved\. It applies to every session/)).toBeInTheDocument();
    expect(bodyOf(fetchMock, "PATCH", `${C}/settings`)).toEqual({ attendance_edit_window_hours: 24 });
  });

  it("tells department admins that college admins run terms", async () => {
    mockFetch({ [ME]: signedIn({}, CSE_ADMIN), [`${C}/terms`]: () => json({ items: TERMS }) });
    renderRoute("/manage/academics?view=terms");
    expect(await screen.findByText("College admins add terms and choose the current one.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Make current" })).not.toBeInTheDocument();
  });
});

describe("Section setup", () => {
  const routes = (extra: Record<string, (init?: RequestInit) => Response> = {}) => ({
    [ME]: signedIn({}, CSE_ADMIN),
    [`${C}/sections/sec1`]: () => json(SECTION),
    [`${C}/sections/sec1/enrollments?limit=100`]: () =>
      page([{ id: "e1", membership_id: "m1", display_name: "Ishita Verma", roll_number: "NF-CSE-002", department: CSE }]),
    [`${C}/sections/sec1/timetable`]: () => json({ items: [{ id: "tt1", section_id: "sec1", weekday: 1, starts_at: "09:00:00", ends_at: "10:00:00", room: "C-103" }] }),
    ...extra,
  });

  it("assigns faculty found by name", async () => {
    const fetchMock = mockFetch(
      routes({
        [`${C}/members?query=ra&kind=FACULTY&status=ACTIVE`]: () =>
          page([{ id: "f1", user_id: "u", display_name: "Ravi Sharma", kind: "FACULTY", status: "ACTIVE", department: CSE, email: null, roll_number: null, roles: [], joined_at: "2026-01-01T00:00:00Z" }]),
        [`PUT ${C}/sections/sec1/instructors`]: () => json({ ...SECTION, instructors: [{ membership_id: "f1", display_name: "Ravi Sharma" }] }),
      }),
    );
    renderRoute("/manage/academics/sections/sec1");
    expect(await screen.findByText(/No faculty assigned yet/)).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText("Find faculty to assign"), "ra");
    await userEvent.click(await screen.findByRole("button", { name: "Assign Ravi Sharma" }));
    expect(await screen.findByRole("list", { name: "Assigned faculty" })).toHaveTextContent("Ravi Sharma");
    expect(bodyOf(fetchMock, "PUT", `${C}/sections/sec1/instructors`)).toEqual({ membership_ids: ["f1"] });
    expect(screen.getByRole("link", { name: "Attendance and results" })).toHaveAttribute("href", "/teaching/sections/sec1");
  });

  it("enrolls pasted roll numbers and lists the problems when any line is wrong", async () => {
    let calls = 0;
    const fetchMock = mockFetch(
      routes({
        [`POST ${C}/sections/sec1/enrollments/import`]: () =>
          ++calls === 1
            ? envelope(422, "enrollment_invalid", "The file has problems. Nobody was enrolled.", [{ row: 3, column: "roll_number", message: "No active student has this roll number." }])
            : json({ enrolled: 2, already_enrolled: 0 }, 201),
      }),
    );
    renderRoute("/manage/academics/sections/sec1");
    const box = await screen.findByLabelText("Enroll by roll number");
    await userEvent.type(box, "NF-CSE-003{Enter}NF-XX-999");
    await userEvent.click(screen.getByRole("button", { name: "Enroll" }));
    const problems = await screen.findByRole("table", { name: "Problems in the list" });
    expect(problems).toHaveTextContent("No active student has this roll number.");
    expect(bodyOf(fetchMock, "POST", `${C}/sections/sec1/enrollments/import`)).toEqual({ csv: "roll_number\nNF-CSE-003\nNF-XX-999\n" });
    await userEvent.click(screen.getByRole("button", { name: "Enroll" }));
    expect(await screen.findByText("2 students enrolled.")).toBeInTheDocument();
  });

  it("explains when a student with records can't be removed", async () => {
    mockFetch(routes({ [`DELETE ${C}/enrollments/e1`]: () => envelope(409, "enrollment_has_records", "This student already has attendance or results in this section.") }));
    renderRoute("/manage/academics/sections/sec1");
    await userEvent.click(await screen.findByRole("button", { name: "Remove Ishita Verma" }));
    const dialog = screen.getByRole("dialog", { name: "Remove Ishita Verma from this section?" });
    await userEvent.click(within(dialog).getByRole("button", { name: "Remove student" }));
    expect(await within(dialog).findByRole("alert")).toHaveTextContent("already has attendance or results");
  });

  it("adds and removes timetable classes, showing an overlap", async () => {
    const fetchMock = mockFetch(
      routes({
        [`POST ${C}/sections/sec1/timetable`]: () => envelope(409, "timetable_overlap", "This section already has a class at that time on that day."),
        [`DELETE ${C}/timetable-entries/tt1`]: () => noContent(),
      }),
    );
    renderRoute("/manage/academics/sections/sec1");
    expect(await screen.findByRole("list", { name: "Scheduled classes" })).toHaveTextContent("Monday 09:00–10:00 · C-103");
    const form = screen.getByRole("form", { name: "Add a class" });
    await userEvent.type(within(form).getByLabelText("Room"), "C-103");
    await userEvent.click(within(form).getByRole("button", { name: "Add class" }));
    expect(await within(form).findByRole("alert")).toHaveTextContent("already has a class at that time");
    expect(bodyOf(fetchMock, "POST", `${C}/sections/sec1/timetable`)).toEqual({ weekday: 1, starts_at: "09:00", ends_at: "10:00", room: "C-103" });
    await userEvent.click(screen.getByRole("button", { name: "Remove Monday 09:00" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(`${C}/timetable-entries/tt1`, expect.objectContaining({ method: "DELETE" })));
  });
});

describe("rollNumbersCsv", () => {
  it("accepts lines or commas, with or without the header", () => {
    expect(rollNumbersCsv(" N-1 \n\nN-2, N-3")).toBe("roll_number\nN-1\nN-2\nN-3\n");
    expect(rollNumbersCsv("roll_number\nN-1")).toBe("roll_number\nN-1\n");
  });
});
