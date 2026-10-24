import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import type { Me } from "@/features/auth/api";
import { MEMBER, signedIn } from "@/test/auth";
import { envelope, json, mockFetch } from "@/test/http";
import { renderRoute } from "@/test/render";

const ME = "/api/v1/me";
const C = "/api/v1/campus";
const CSE = { id: "d0000000-0000-4000-8000-000000000001", code: "CSE", name: "Computer Science" };
const MECH = { id: "d0000000-0000-4000-8000-000000000002", code: "MECH", name: "Mechanical" };

const ADMIN: Partial<Me> = {
  ...MEMBER,
  membership: { ...MEMBER.membership!, kind: "STAFF", department: null },
  roles: [{ role: "COLLEGE_ADMIN", department: null }],
  capabilities: ["campus", "manage_college", "review_memberships"],
};
const DEPT_ADMIN: Partial<Me> = {
  ...MEMBER,
  membership: { ...MEMBER.membership!, kind: "FACULTY" },
  roles: [{ role: "DEPARTMENT_ADMIN", department: CSE }],
  capabilities: ["campus", "review_memberships"],
};

const page = <T,>(items: T[], next_cursor: string | null = null) => json({ items, next_cursor });

const REQUEST_ITEM = {
  id: "r1",
  requester: { display_name: "Meera Iyer", email: "meera@mail.example" },
  flag: "EMAIL_MISMATCH",
  roll_number: "CSE2025007",
  roster: { full_name: "Meera Iyer", program: "B.Tech", admission_year: 2025, department: CSE },
  status: "PENDING",
  decision_reason: null,
  created_at: "2026-10-20T04:30:00Z",
};

const MEMBER_ROW = {
  id: "m1",
  user_id: "u1",
  display_name: "Kabir Shah",
  kind: "STUDENT",
  status: "ACTIVE",
  department: CSE,
  email: "kabir@northfield.example",
  roll_number: "CSE2024001",
  roles: [],
  joined_at: "2026-09-01T05:00:00Z",
};

/** The JSON body of the n-th `method` request to `path`. */
function bodyOf(fetchMock: ReturnType<typeof mockFetch>, method: string, path: string, index = 0): unknown {
  const call = fetchMock.mock.calls.filter(([input, init]) => input === path && (init?.method ?? "GET") === method)[index];
  const body = call?.[1]?.body;
  return typeof body === "string" ? (JSON.parse(body) as unknown) : undefined;
}

afterEach(() => window.history.replaceState(null, "", "/"));

describe("Manage access", () => {
  it("gives college admins the Manage section with every tab", async () => {
    mockFetch({ [ME]: signedIn({}, ADMIN), [`${C}/membership-requests`]: () => page([]) });
    renderRoute("/manage");
    const [nav] = await screen.findAllByRole("navigation", { name: "Main" });
    expect(within(nav!).getAllByRole("link").map((l) => l.textContent)).toEqual(["Home", "Manage", "Account"]);
    const tabs = screen.getByRole("navigation", { name: "Manage" });
    expect(within(tabs).getAllByRole("link").map((l) => l.textContent)).toEqual(["Requests", "Members", "Invites", "Departments", "Roster", "Audit log"]);
    await waitFor(() => expect(within(tabs).getByRole("link", { name: "Requests" })).toHaveAttribute("aria-current", "page"));
  });

  it("shows department admins only their requests and members", async () => {
    mockFetch({ [ME]: signedIn({}, DEPT_ADMIN), [`${C}/membership-requests`]: () => page([]) });
    renderRoute("/manage/requests");
    const tabs = await screen.findByRole("navigation", { name: "Manage" });
    expect(within(tabs).getAllByRole("link").map((l) => l.textContent)).toEqual(["Requests", "Members"]);
  });

  it("sends department admins away from college-admin tabs", async () => {
    mockFetch({ [ME]: signedIn({}, DEPT_ADMIN), [`${C}/membership-requests`]: () => page([]) });
    const { router } = renderRoute("/manage/roster");
    await waitFor(() => expect(router.state.location.pathname).toBe("/manage/requests"));
  });

  it("sends members without admin roles home", async () => {
    mockFetch({ [ME]: signedIn({}, MEMBER) });
    const { router } = renderRoute("/manage/members");
    await waitFor(() => expect(router.state.location.pathname).toBe("/home"));
  });
});

describe("approval queue", () => {
  it("compares the account with the roster and approves", async () => {
    let decided = false;
    const fetchMock = mockFetch({
      [ME]: signedIn({}, ADMIN),
      [`${C}/membership-requests`]: () => page(decided ? [] : [REQUEST_ITEM]),
      [`POST ${C}/membership-requests/r1/approve`]: () => {
        decided = true;
        return json({ id: "r1", status: "ACTIVE" });
      },
    });
    renderRoute("/manage/requests");
    expect(await screen.findByText("The roster lists a different email for this roll number.")).toBeInTheDocument();
    expect(screen.getByText("meera@mail.example")).toBeInTheDocument();
    expect(screen.getByText("CSE2025007")).toBeInTheDocument();
    expect(screen.getByText(/B\.Tech · 2025 · CSE/)).toBeInTheDocument();
    expect(screen.getByText(/20 Oct 2026, 10:00/)).toBeInTheDocument(); // college time zone
    await userEvent.click(screen.getByRole("button", { name: "Approve" }));
    expect(await screen.findByText("No requests waiting.")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(`${C}/membership-requests/r1/approve`, expect.objectContaining({ method: "POST" }));
  });

  it("shows why an approval was refused", async () => {
    mockFetch({
      [ME]: signedIn({}, ADMIN),
      [`${C}/membership-requests`]: () => page([{ ...REQUEST_ITEM, flag: "NO_ROSTER_MATCH", roster: null }]),
      [`POST ${C}/membership-requests/r1/approve`]: () =>
        envelope(409, "no_roster_entry", "Add this roll number to the roster first, or reject the request."),
    });
    renderRoute("/manage/requests");
    expect(await screen.findByText("Not on the roster")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Approve" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Add this roll number to the roster first");
  });

  it("rejects only with a reason", async () => {
    const fetchMock = mockFetch({
      [ME]: signedIn({}, ADMIN),
      [`${C}/membership-requests`]: () => page([REQUEST_ITEM]),
      [`POST ${C}/membership-requests/r1/reject`]: () => json({ id: "r1", status: "REJECTED" }),
    });
    renderRoute("/manage/requests");
    await userEvent.click(await screen.findByRole("button", { name: "Reject" }));
    const dialog = screen.getByRole("dialog", { name: "Reject Meera Iyer's request?" });
    await userEvent.click(within(dialog).getByRole("button", { name: "Reject request" }));
    expect(within(dialog).getByText("Give a reason.")).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalledWith(`${C}/membership-requests/r1/reject`, expect.anything());
    await userEvent.type(within(dialog).getByLabelText("Reason"), "Not a student here");
    await userEvent.click(within(dialog).getByRole("button", { name: "Reject request" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(bodyOf(fetchMock, "POST", `${C}/membership-requests/r1/reject`)).toEqual({ reason: "Not a student here" });
  });

  it("offers a retry with the request ID when the list fails", async () => {
    let fail = true;
    mockFetch({
      [ME]: signedIn({}, ADMIN),
      [`${C}/membership-requests`]: () => (fail ? envelope(500, "internal_error", "Something went wrong on our side.", null, "req-42") : page([])),
    });
    renderRoute("/manage/requests");
    expect(await screen.findByText("Couldn't load the requests.")).toBeInTheDocument();
    expect(screen.getByText("Request ID req-42")).toBeInTheDocument();
    fail = false;
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByText("No requests waiting.")).toBeInTheDocument();
  });

  it("loads more with the cursor", async () => {
    mockFetch({
      [ME]: signedIn({}, ADMIN),
      [`${C}/membership-requests`]: () => page([REQUEST_ITEM], "next-1"),
      [`${C}/membership-requests?cursor=next-1`]: () =>
        page([{ ...REQUEST_ITEM, id: "r2", requester: { display_name: "Dev Patel", email: "dev@mail.example" } }]),
    });
    renderRoute("/manage/requests");
    expect(await screen.findByText("Showing 1")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Load more" }));
    expect(await screen.findByText("Dev Patel")).toBeInTheDocument();
    expect(screen.getByText("Showing 2")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Load more" })).not.toBeInTheDocument();
  });
});

describe("members", () => {
  const routes = (extra: Record<string, (init?: RequestInit) => Response> = {}) => ({
    [ME]: signedIn({}, ADMIN),
    [`${C}/members?status=ACTIVE`]: () => page([MEMBER_ROW]),
    [`${C}/departments`]: () => json({ items: [{ ...CSE, description: "", archived: false }, { ...MECH, description: "", archived: false }] }),
    ...extra,
  });

  it("lists members and filters by kind", async () => {
    const fetchMock = mockFetch(routes({ [`${C}/members?kind=FACULTY&status=ACTIVE`]: () => page([]) }));
    renderRoute("/manage/members");
    const table = await screen.findByRole("table", { name: "Members" });
    expect(within(table).getByText("Kabir Shah")).toBeInTheDocument();
    expect(within(table).getByText("CSE2024001")).toBeInTheDocument();
    await userEvent.selectOptions(screen.getByLabelText("Kind"), "FACULTY");
    expect(await screen.findByText("No members match these filters.")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(`${C}/members?kind=FACULTY&status=ACTIVE`, expect.anything());
  });

  it("suspends a member only with a reason and shows the server's refusal", async () => {
    const fetchMock = mockFetch(
      routes({ [`PATCH ${C}/members/m1`]: () => envelope(409, "last_college_admin", "The college needs at least one active college admin.") }),
    );
    renderRoute("/manage/members");
    await userEvent.click(await screen.findByRole("button", { name: "Manage Kabir Shah" }));
    await userEvent.click(screen.getByRole("button", { name: "Suspend" }));
    const dialog = screen.getByRole("dialog", { name: "Suspend this membership?" });
    await userEvent.click(within(dialog).getByRole("button", { name: "Suspend" }));
    expect(within(dialog).getByText("Give a reason.")).toBeInTheDocument();
    await userEvent.type(within(dialog).getByLabelText(/Reason/), "Left the college");
    await userEvent.click(within(dialog).getByRole("button", { name: "Suspend" }));
    expect(await within(dialog).findByRole("alert")).toHaveTextContent("at least one active college admin");
    expect(bodyOf(fetchMock, "PATCH", `${C}/members/m1`)).toEqual({ status: "SUSPENDED", reason: "Left the college" });
  });

  it("gives a department admin role for a chosen department", async () => {
    const fetchMock = mockFetch(routes({ [`POST ${C}/members/m1/grants`]: () => json({ id: "g1", role: "DEPARTMENT_ADMIN", department: MECH }, 201) }));
    renderRoute("/manage/members");
    await userEvent.click(await screen.findByRole("button", { name: "Manage Kabir Shah" }));
    const give = await screen.findByRole("button", { name: "Give role" });
    expect(give).toBeDisabled();
    await userEvent.selectOptions(screen.getByLabelText("Of department"), "MECH");
    await userEvent.click(give);
    await waitFor(() => expect(bodyOf(fetchMock, "POST", `${C}/members/m1/grants`)).toEqual({ role: "DEPARTMENT_ADMIN", department_id: MECH.id }));
  });

  it("lets department admins look but not change", async () => {
    mockFetch({ [ME]: signedIn({}, DEPT_ADMIN), [`${C}/members?status=ACTIVE`]: () => page([{ ...MEMBER_ROW, email: null, roll_number: null }]) });
    renderRoute("/manage/members");
    expect(await screen.findByText("Kabir Shah")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Manage/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("columnheader", { name: "Actions" })).not.toBeInTheDocument();
  });
});

describe("departments", () => {
  it("adds a department and shows server problems on the form", async () => {
    let created = false;
    const fetchMock = mockFetch({
      [ME]: signedIn({}, ADMIN),
      [`${C}/departments`]: () => json({ items: created ? [{ ...MECH, description: "", archived: false }] : [] }),
      [`POST ${C}/departments`]: (init) => {
        const body = JSON.parse(init?.body as string) as { code: string };
        if (body.code === "CSE") return envelope(409, "code_taken", "A department with this code already exists.");
        created = true;
        return json({ ...MECH, description: "", archived: false }, 201);
      },
    });
    renderRoute("/manage/departments");
    expect(await screen.findByText("No departments yet.")).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText("Code"), "cse");
    await userEvent.type(screen.getByLabelText("Name"), "Computer Science");
    await userEvent.click(screen.getByRole("button", { name: "Add department" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("already exists");
    await userEvent.clear(screen.getByLabelText("Code"));
    await userEvent.type(screen.getByLabelText("Code"), "mech");
    await userEvent.click(screen.getByRole("button", { name: "Add department" }));
    expect(await screen.findByRole("table", { name: "Departments" })).toHaveTextContent("MECH");
    expect(bodyOf(fetchMock, "POST", `${C}/departments`, 1)).toEqual({ code: "MECH", name: "Computer Science", description: "" });
  });

  it("archives after confirming", async () => {
    const fetchMock = mockFetch({
      [ME]: signedIn({}, ADMIN),
      [`${C}/departments`]: () => json({ items: [{ ...CSE, description: "", archived: false }] }),
      [`PATCH ${C}/departments/${CSE.id}`]: () => json({ ...CSE, description: "", archived: true }),
    });
    renderRoute("/manage/departments");
    await userEvent.click(await screen.findByRole("button", { name: "Archive CSE" }));
    const dialog = screen.getByRole("dialog", { name: "Archive CSE?" });
    await userEvent.click(within(dialog).getByRole("button", { name: "Archive" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(bodyOf(fetchMock, "PATCH", `${C}/departments/${CSE.id}`)).toEqual({ archived: true });
  });
});

describe("invites", () => {
  it("sends an invitation and lists it", async () => {
    let sent = false;
    const invite = { id: "i1", email: "prof@northfield.example", kind: "FACULTY", state: "PENDING", created_at: "2026-10-24T05:00:00Z", expires_at: "2026-10-31T05:00:00Z" };
    const fetchMock = mockFetch({
      [ME]: signedIn({}, ADMIN),
      [`${C}/invites`]: () => json({ items: sent ? [invite] : [] }),
      [`POST ${C}/invites`]: () => {
        sent = true;
        return json(invite, 201);
      },
    });
    renderRoute("/manage/invites");
    expect(await screen.findByText("No invitations sent yet.")).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText("Email"), "Prof@Northfield.example");
    await userEvent.click(screen.getByRole("button", { name: "Send invitation" }));
    expect(await screen.findByText(/Invitation sent to prof@northfield.example/)).toBeInTheDocument();
    expect(await screen.findByRole("table", { name: "Sent invitations" })).toHaveTextContent("Waiting");
    expect(bodyOf(fetchMock, "POST", `${C}/invites`)).toEqual({ email: "prof@northfield.example", kind: "FACULTY" });
  });
});

describe("roster", () => {
  it("lists every problem in a rejected file", async () => {
    mockFetch({
      [ME]: signedIn({}, ADMIN),
      [`${C}/roster`]: () => page([]),
      [`POST ${C}/roster/import`]: () =>
        envelope(422, "roster_invalid", "The roster file has problems. Nothing was imported.", [
          { row: 2, column: "department_code", message: "No current department has this code." },
          { row: 3, column: "roll_number", message: "Appears twice in this file." },
        ]),
    });
    renderRoute("/manage/roster");
    expect(await screen.findByText("The roster is empty.")).toBeInTheDocument();
    await userEvent.upload(screen.getByLabelText("CSV file"), new File(["roll_number,full_name\n"], "students.csv", { type: "text/csv" }));
    expect(await screen.findByText("students.csv is ready to import.")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Import" }));
    const table = await screen.findByRole("table", { name: "Problems in the file" });
    expect(within(table).getAllByRole("row")).toHaveLength(3);
    expect(table).toHaveTextContent("No current department has this code.");
    expect(screen.getByText("Nothing was imported.")).toBeInTheDocument();
  });

  it("imports pasted rows and refreshes the roster", async () => {
    let imported = false;
    const entry = { id: "e1", roll_number: "CSE2025001", full_name: "Asha Rao", email: null, program: "B.Tech", admission_year: 2025, department: CSE, claimed: false };
    const fetchMock = mockFetch({
      [ME]: signedIn({}, ADMIN),
      [`${C}/roster`]: () => page(imported ? [entry] : []),
      [`POST ${C}/roster/import`]: () => {
        imported = true;
        return json({ imported: 1 }, 201);
      },
    });
    renderRoute("/manage/roster");
    await userEvent.click(await screen.findByRole("button", { name: "Import" }));
    expect(screen.getByRole("alert")).toHaveTextContent("Choose a CSV file or paste the rows.");
    await userEvent.type(screen.getByLabelText("Or paste the rows"), "roll_number,full_name");
    await userEvent.click(screen.getByRole("button", { name: "Import" }));
    expect(await screen.findByText("Imported 1 students.")).toBeInTheDocument();
    expect(await screen.findByRole("table", { name: "Roster" })).toHaveTextContent("CSE2025001");
    expect(bodyOf(fetchMock, "POST", `${C}/roster/import`)).toEqual({ csv: "roll_number,full_name" });
  });
});

describe("audit log", () => {
  it("names actions in words and filters by action", async () => {
    const fetchMock = mockFetch({
      [ME]: signedIn({}, ADMIN),
      [`${C}/audit-log`]: () =>
        page([
          { id: "a1", action: "membership.rejected", actor: { id: "u9", display_name: "Priya Menon" }, target_type: "membership", target_id: "r1", reason: "Not enrolled", metadata: {}, created_at: "2026-10-22T09:00:00Z" },
        ]),
      [`${C}/audit-log?action=college.role_granted`]: () => page([]),
    });
    renderRoute("/manage/audit");
    const table = await screen.findByRole("table", { name: "Audit log" });
    expect(table).toHaveTextContent("Request rejected");
    expect(table).toHaveTextContent("Priya Menon");
    expect(table).toHaveTextContent("Not enrolled");
    await userEvent.selectOptions(screen.getByLabelText("Action"), "college.role_granted");
    expect(await screen.findByText("Nothing recorded yet.")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(`${C}/audit-log?action=college.role_granted`, expect.anything());
  });
});
