import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import type { Me } from "@/features/auth/api";
import { MEMBER, NORTHFIELD_MEMBERSHIP, signedIn } from "@/test/auth";
import { json, mockFetch, sentBody } from "@/test/http";
import { renderRoute } from "@/test/render";

import type { Issue, IssueActions, IssueSummary } from "./api";
import { originalIdFrom } from "./labels";

const ME = "/api/v1/me";
const ISSUES = "/api/v1/campus/issues";
const ASSIGNEES = "/api/v1/campus/assignees";
const ORIGINAL = "0f1e2d3c-4b5a-4987-8a6b-5c4d3e2f1a0b";

const FACULTY: Partial<Me> = { ...MEMBER, membership: { ...NORTHFIELD_MEMBERSHIP, kind: "FACULTY" } };
const COORDINATOR: Partial<Me> = {
  ...MEMBER,
  membership: { ...NORTHFIELD_MEMBERSHIP, kind: "STAFF", department: null },
  roles: [{ role: "ISSUE_COORDINATOR", department: null }],
};

function summary(over: Partial<IssueSummary> = {}): IssueSummary {
  return {
    id: "i1",
    title: "Projector doesn't turn on",
    category: "CLASSROOM_EQUIPMENT",
    location: "Main block",
    room: "204",
    status: "SUBMITTED",
    reporter_name: "Aarav Nair",
    assignee_name: null,
    created_at: "2026-10-20T04:30:00Z",
    updated_at: "2026-10-20T04:30:00Z",
    ...over,
  };
}

const STAFF_NEW: IssueActions = {
  transitions: [
    { to_status: "ACKNOWLEDGED", needs_note: false },
    { to_status: "REJECTED", needs_note: true },
  ],
  assign: true,
  comment: true,
  comment_internal: true,
};

function issue(over: Partial<Issue> = {}): Issue {
  return {
    ...summary(),
    description: "It sparks.",
    resolved_at: null,
    version: 3,
    duplicate_of: null,
    updates: [],
    actions: STAFF_NEW,
    ...over,
  };
}

const page = (items: unknown[]) => () => json({ items, next_cursor: null });

afterEach(() => window.history.replaceState(null, "", "/"));

describe("issue lists by role", () => {
  it("gives students only their own list", async () => {
    mockFetch({ [ME]: signedIn({}, MEMBER), [`${ISSUES}?scope=mine`]: page([]) });
    const { router } = renderRoute("/issues/queue"); // asking for the queue doesn't get it
    expect(await screen.findByRole("heading", { level: 1, name: "My issues" })).toBeInTheDocument();
    expect(screen.queryByRole("navigation", { name: "Issue lists" })).not.toBeInTheDocument();
    expect(await screen.findByText("You haven't reported any issues.")).toBeInTheDocument();
    expect(router.state.location.pathname).toBe("/issues");
  });

  it("adds Assigned to me for faculty", async () => {
    mockFetch({ [ME]: signedIn({}, FACULTY), [`${ISSUES}?scope=assigned`]: page([summary({ status: "ACKNOWLEDGED" })]) });
    renderRoute("/issues?view=assigned");
    const tabs = await screen.findByRole("navigation", { name: "Issue lists" });
    expect(within(tabs).getAllByRole("link").map((l) => l.textContent)).toEqual(["Mine", "Assigned to me"]);
    expect(within(tabs).getByRole("link", { name: "Assigned to me" })).toHaveAttribute("aria-current", "page");
    const list = await screen.findByRole("list", { name: "Issues assigned to me" });
    expect(within(list).getByRole("link")).toHaveAttribute("href", "/issues/i1");
  });

  it("says when nothing is assigned", async () => {
    mockFetch({ [ME]: signedIn({}, FACULTY), [`${ISSUES}?scope=assigned`]: page([]) });
    renderRoute("/issues?view=assigned");
    expect(await screen.findByText("Nothing is assigned to you.")).toBeInTheDocument();
  });
});

describe("the coordinator queue", () => {
  it("lists the college's issues in a table and filters through the URL", async () => {
    const fetchMock = mockFetch({
      [ME]: signedIn({}, COORDINATOR),
      [`${ISSUES}?scope=queue`]: page([summary(), summary({ id: "i2", title: "Tap leaking", status: "ACKNOWLEDGED", assignee_name: "Ravi Sharma", reporter_name: "Ishita Verma" })]),
      [ASSIGNEES]: page([{ id: "m-ravi", name: "Ravi Sharma", kind: "FACULTY" }]),
      [`${ISSUES}?scope=queue&status=ACKNOWLEDGED`]: page([summary({ id: "i2", title: "Tap leaking", status: "ACKNOWLEDGED" })]),
      [`${ISSUES}?scope=queue&status=ACKNOWLEDGED&category=WATER_SANITATION`]: page([]),
      [`${ISSUES}?scope=queue&status=ACKNOWLEDGED&category=WATER_SANITATION&assignee_id=m-ravi`]: page([]),
      [`${ISSUES}?scope=queue&status=ACKNOWLEDGED&category=WATER_SANITATION&assignee_id=m-ravi&older_than_days=7`]: page([]),
    });
    const { router } = renderRoute("/issues/queue");
    const table = await screen.findByRole("table", { name: "Issue queue" });
    expect(within(table).getByRole("link", { name: "Tap leaking" })).toHaveAttribute("href", "/issues/i2");
    expect(within(table).getByText("Ishita Verma")).toBeInTheDocument();
    expect(within(table).getByText("Nobody")).toBeInTheDocument();

    await userEvent.selectOptions(screen.getByLabelText("Status"), "ACKNOWLEDGED");
    await waitFor(() => expect(within(screen.getByRole("table")).queryByText("Projector doesn't turn on")).not.toBeInTheDocument());
    await userEvent.selectOptions(screen.getByLabelText("Category"), "WATER_SANITATION");
    expect(await screen.findByText("No issues match these filters.")).toBeInTheDocument();
    await userEvent.selectOptions(await screen.findByLabelText("Assignee"), "m-ravi");
    await userEvent.selectOptions(screen.getByLabelText("Reported"), "7");
    await waitFor(() => expect(router.state.location.search).toBe("?status=ACKNOWLEDGED&category=WATER_SANITATION&assignee=m-ravi&older_than=7"));
    expect(fetchMock.mock.calls.some(([url]) => url === `${ISSUES}?scope=queue&status=ACKNOWLEDGED&category=WATER_SANITATION&assignee_id=m-ravi&older_than_days=7`)).toBe(true);
  });
});

describe("staff actions on an issue", () => {
  it("offers exactly the changes the server allows, and acknowledges in one click", async () => {
    const fetchMock = mockFetch({
      [ME]: signedIn({}, COORDINATOR),
      [`${ISSUES}/i1`]: () => json(issue()),
      [`POST ${ISSUES}/i1/transitions`]: () => json(issue({ status: "ACKNOWLEDGED", version: 4 })),
    });
    renderRoute("/issues/i1");
    const section = await screen.findByRole("region", { name: "Change status" });
    expect(within(section).getAllByRole("button").map((b) => b.textContent)).toEqual(["Acknowledge", "Reject", "Reject as duplicate"]);
    await userEvent.click(within(section).getByRole("button", { name: "Acknowledge" }));
    expect(await screen.findByText("Issue acknowledged. The reporter has been told.")).toBeInTheDocument();
    expect(sentBody(fetchMock, `${ISSUES}/i1/transitions`)).toEqual({ to_status: "ACKNOWLEDGED", version: 3 });
  });

  it("asks for a resolution note", async () => {
    const working = issue({ status: "IN_PROGRESS", actions: { ...STAFF_NEW, transitions: [{ to_status: "RESOLVED", needs_note: true }] } });
    const fetchMock = mockFetch({
      [ME]: signedIn({}, COORDINATOR),
      [`${ISSUES}/i1`]: () => json(working),
      [`POST ${ISSUES}/i1/transitions`]: () => json(issue({ status: "RESOLVED", resolved_at: "2026-10-22T10:00:00Z", actions: { ...STAFF_NEW, transitions: [] } })),
    });
    renderRoute("/issues/i1");
    await userEvent.click(await screen.findByRole("button", { name: "Resolve" }));
    const dialog = screen.getByRole("dialog", { name: "Resolve this issue?" });
    await userEvent.click(within(dialog).getByRole("button", { name: "Resolve issue" }));
    expect(within(dialog).getByText("Give a reason.")).toBeInTheDocument();
    await userEvent.type(within(dialog).getByLabelText(/Resolution note/), "Replaced the cable.");
    await userEvent.click(within(dialog).getByRole("button", { name: "Resolve issue" }));
    expect(await screen.findByText("Issue resolved. The reporter has been told.")).toBeInTheDocument();
    expect(sentBody(fetchMock, `${ISSUES}/i1/transitions`)).toEqual({ to_status: "RESOLVED", note: "Replaced the cable.", version: 3 });
  });

  it("closes a duplicate from the original's link, the note optional", async () => {
    const fetchMock = mockFetch({
      [ME]: signedIn({}, COORDINATOR),
      [`${ISSUES}/i1`]: () => json(issue()),
      [`POST ${ISSUES}/i1/transitions`]: () => json(issue({ status: "REJECTED", duplicate_of: { id: ORIGINAL, status: "SUBMITTED", resolved_at: null }, actions: { ...STAFF_NEW, transitions: [] } })),
    });
    renderRoute("/issues/i1");
    await userEvent.click(await screen.findByRole("button", { name: "Reject as duplicate" }));
    const dialog = screen.getByRole("dialog", { name: "Close as a duplicate?" });
    await userEvent.type(within(dialog).getByLabelText("Original issue (link or ID)"), "the projector one");
    await userEvent.click(within(dialog).getByRole("button", { name: "Close as duplicate" }));
    expect(within(dialog).getByText("Paste the original issue's link or ID.")).toBeInTheDocument();
    await userEvent.clear(within(dialog).getByLabelText("Original issue (link or ID)"));
    await userEvent.type(within(dialog).getByLabelText("Original issue (link or ID)"), `https://campus.example/issues/${ORIGINAL}`);
    await userEvent.click(within(dialog).getByRole("button", { name: "Close as duplicate" }));
    expect(await screen.findByText("Closed as a duplicate. The reporter has been told.")).toBeInTheDocument();
    expect(sentBody(fetchMock, `${ISSUES}/i1/transitions`)).toEqual({ to_status: "REJECTED", duplicate_of_id: ORIGINAL, version: 3 });
    expect(screen.getByRole("link", { name: "Open the original" })).toHaveAttribute("href", `/issues/${ORIGINAL}`);
  });

  it("assigns from the list of faculty and staff, and unassigns", async () => {
    const assigned = issue({ assignee_name: "Ravi Sharma", version: 4 });
    const fetchMock = mockFetch({
      [ME]: signedIn({}, COORDINATOR),
      [`${ISSUES}/i1`]: () => json(issue()),
      [ASSIGNEES]: page([{ id: "m-ravi", name: "Ravi Sharma", kind: "FACULTY" }, { id: "m-meera", name: "Meera Iyer", kind: "STAFF" }]),
      [`${ASSIGNEES}?query=me`]: page([{ id: "m-meera", name: "Meera Iyer", kind: "STAFF" }]),
      [`POST ${ISSUES}/i1/assignment`]: (init) => json((JSON.parse(typeof init?.body === "string" ? init.body : "{}") as { assignee_id: string | null }).assignee_id ? assigned : issue({ version: 5 })),
    });
    renderRoute("/issues/i1");
    await userEvent.click(await screen.findByRole("button", { name: "Assign" }));
    const list = await screen.findByRole("list", { name: "Faculty and staff" });
    expect(within(list).getAllByRole("listitem").map((li) => li.textContent)).toEqual(["Ravi Sharma · FacultyAssign", "Meera Iyer · StaffAssign"]);
    await userEvent.type(screen.getByLabelText("Find faculty or staff"), "me");
    await waitFor(() => expect(within(screen.getByRole("list", { name: "Faculty and staff" })).getAllByRole("listitem")).toHaveLength(1));
    await userEvent.clear(screen.getByLabelText("Find faculty or staff"));
    await userEvent.click(await screen.findByRole("button", { name: "Assign to Ravi Sharma" }));
    expect(await screen.findByText("Assigned to Ravi Sharma. They've been told.")).toBeInTheDocument();
    expect(sentBody(fetchMock, `${ISSUES}/i1/assignment`)).toEqual({ assignee_id: "m-ravi", version: 3 });

    await userEvent.click(screen.getByRole("button", { name: "Unassign" }));
    expect(await screen.findByText("Nobody is assigned now.")).toBeInTheDocument();
    expect(sentBody(fetchMock, `${ISSUES}/i1/assignment`, 1)).toEqual({ assignee_id: null, version: 4 });
  });

  it("shows the assignee only what the server allows them", async () => {
    const forAssignee = issue({ status: "ACKNOWLEDGED", actions: { transitions: [{ to_status: "IN_PROGRESS", needs_note: false }], assign: false, comment: true, comment_internal: true } });
    mockFetch({ [ME]: signedIn({}, FACULTY), [`${ISSUES}/i1`]: () => json(forAssignee) });
    renderRoute("/issues/i1");
    const section = await screen.findByRole("region", { name: "Change status" });
    expect(within(section).getAllByRole("button").map((b) => b.textContent)).toEqual(["Start work"]);
    expect(screen.queryByRole("region", { name: "Assignment" })).not.toBeInTheDocument();
  });

  it("reads the original's ID from a link or the ID itself", () => {
    expect(originalIdFrom(`  ${ORIGINAL.toUpperCase()} `)).toBe(ORIGINAL);
    expect(originalIdFrom(`/issues/${ORIGINAL}?x=1`)).toBe(ORIGINAL);
    expect(originalIdFrom("issue 42")).toBeNull();
  });
});
