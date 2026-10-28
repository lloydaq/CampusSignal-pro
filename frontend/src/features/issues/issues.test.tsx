import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { MEMBER, signedIn } from "@/test/auth";
import { envelope, json, mockFetch, sentBody } from "@/test/http";
import { renderRoute } from "@/test/render";

import type { Issue, IssueSummary, IssueUpdate } from "./api";
import { ageText } from "./labels";

const ME = "/api/v1/me";
const ISSUES = "/api/v1/campus/issues";
const MINE = `${ISSUES}?scope=mine`;

function summary(over: Partial<IssueSummary> = {}): IssueSummary {
  return {
    id: "i1",
    title: "Projector doesn't turn on",
    category: "CLASSROOM_EQUIPMENT",
    location: "Main block, second floor",
    room: "204",
    status: "SUBMITTED",
    reporter_name: "Aarav Nair",
    assignee_name: null,
    created_at: "2026-10-20T04:30:00Z",
    updated_at: "2026-10-20T04:30:00Z",
    ...over,
  };
}

function update(over: Partial<IssueUpdate> = {}): IssueUpdate {
  return {
    id: "u1",
    kind: "CREATED",
    from_status: null,
    to_status: null,
    body: null,
    is_internal: false,
    actor_name: "Aarav Nair",
    assignee_name: null,
    created_at: "2026-10-20T04:30:00Z",
    ...over,
  };
}

const NONE = { transitions: [], assign: false, comment: false, comment_internal: false };
const REPORTER = { ...NONE, comment: true };

function issue(over: Partial<Issue> = {}): Issue {
  return {
    ...summary(),
    description: "It sparks when switched on.",
    resolved_at: null,
    version: 1,
    duplicate_of: null,
    updates: [update()],
    actions: REPORTER,
    ...over,
  };
}

const one = (value: Issue) => () => json(value);

afterEach(() => window.history.replaceState(null, "", "/"));

describe("reporting an issue", () => {
  it("asks for every required field", async () => {
    const fetchMock = mockFetch({ [ME]: signedIn({}, MEMBER) });
    renderRoute("/issues/new");
    await userEvent.click(await screen.findByRole("button", { name: "Report issue" }));
    expect(await screen.findByText("Choose a category.")).toBeInTheDocument();
    expect(screen.getByText("Say what's wrong in a few words.")).toBeInTheDocument();
    expect(screen.getByText("Say where it is.")).toBeInTheDocument();
    expect(screen.getByText("Describe the problem.")).toBeInTheDocument();
    expect(fetchMock.mock.calls.some(([, init]) => init?.method === "POST")).toBe(false);
  });

  it("reports it and opens the new issue", async () => {
    const created = issue({ id: "i9" });
    const fetchMock = mockFetch({ [ME]: signedIn({}, MEMBER), [`POST ${ISSUES}`]: () => json(created, 201), [`${ISSUES}/i9`]: one(created) });
    const { router } = renderRoute("/issues/new");
    await userEvent.click(await screen.findByRole("radio", { name: "Network / Wi-Fi" }));
    await userEvent.type(screen.getByLabelText("What's wrong?"), "  Wi-Fi down  ");
    await userEvent.type(screen.getByLabelText("Where is it?"), "Library");
    await userEvent.type(screen.getByLabelText("Description"), "No connection since morning.");
    await userEvent.click(screen.getByRole("button", { name: "Report issue" }));

    await waitFor(() => expect(router.state.location.pathname).toBe("/issues/i9"));
    // An empty room isn't sent at all; text is trimmed.
    expect(sentBody(fetchMock, ISSUES)).toEqual({ category: "NETWORK", title: "Wi-Fi down", location: "Library", description: "No connection since morning." });
    expect(await screen.findByText("Issue reported. You'll be notified each time its status changes.")).toBeInTheDocument();
  });

  it("explains the daily limit", async () => {
    mockFetch({ [ME]: signedIn({}, MEMBER), [`POST ${ISSUES}`]: () => envelope(429, "rate_limited", "Too many requests.", null, "r", { "Retry-After": "7200" }) });
    renderRoute("/issues/new");
    await userEvent.click(await screen.findByRole("radio", { name: "Other" }));
    await userEvent.type(screen.getByLabelText("What's wrong?"), "Broken bench");
    await userEvent.type(screen.getByLabelText("Where is it?"), "Quad");
    await userEvent.type(screen.getByLabelText("Description"), "Snapped in half.");
    await userEvent.click(screen.getByRole("button", { name: "Report issue" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("You've reported 5 issues in the last 24 hours. Try again in 120 minutes.");
  });
});

describe("my issues", () => {
  it("lists my reports with status, title, place and age", async () => {
    mockFetch({ [ME]: signedIn({}, MEMBER), [MINE]: () => json({ items: [summary(), summary({ id: "i2", title: "Tap leaking", status: "RESOLVED", room: null })], next_cursor: null }) });
    renderRoute("/issues");
    const list = await screen.findByRole("list", { name: "My issues" });
    const rows = within(list).getAllByRole("link");
    expect(rows[0]).toHaveAttribute("href", "/issues/i1");
    expect(rows[0]).toHaveTextContent("Submitted");
    expect(rows[0]).toHaveTextContent("Main block, second floor · Room 204");
    expect(rows[1]).toHaveTextContent("Resolved");
    expect(rows[1]).toHaveTextContent("Tap leaking");
  });

  it("says when there are none, and offers to report one", async () => {
    mockFetch({ [ME]: signedIn({}, MEMBER), [MINE]: () => json({ items: [], next_cursor: null }) });
    renderRoute("/issues");
    expect(await screen.findByText("You haven't reported any issues.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Report an issue" })).toHaveAttribute("href", "/issues/new");
  });

  it("offers a retry when the list fails", async () => {
    mockFetch({ [ME]: signedIn({}, MEMBER), [MINE]: () => envelope(500, "internal_error", "Something went wrong on our side.") });
    renderRoute("/issues");
    expect(await screen.findByText("Couldn't load your issues.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Try again/ })).toBeInTheDocument();
  });

  it("describes age in hours, then days", () => {
    const now = new Date("2026-10-23T04:30:00Z");
    expect(ageText("2026-10-23T04:00:00Z", now)).toBe("Less than an hour ago");
    expect(ageText("2026-10-22T22:30:00Z", now)).toBe("6 hours ago");
    expect(ageText("2026-10-22T04:30:00Z", now)).toBe("1 day ago");
    expect(ageText("2026-10-20T04:30:00Z", now)).toBe("3 days ago");
  });
});

describe("an issue's page", () => {
  it("shows where it stands and everything that happened", async () => {
    const value = issue({
      status: "IN_PROGRESS",
      assignee_name: "Ravi Sharma",
      updates: [
        update(),
        update({ id: "u2", kind: "STATUS", from_status: "SUBMITTED", to_status: "ACKNOWLEDGED", actor_name: "Coordinator" }),
        update({ id: "u3", kind: "ASSIGNMENT", actor_name: "Coordinator", assignee_name: "Ravi Sharma" }),
        update({ id: "u4", kind: "COMMENT", body: "Electrician booked for Friday.", actor_name: "Ravi Sharma" }),
      ],
    });
    mockFetch({ [ME]: signedIn({}, MEMBER), [`${ISSUES}/i1`]: one(value) });
    renderRoute("/issues/i1");
    expect(await screen.findByRole("heading", { level: 1, name: "Projector doesn't turn on" })).toBeInTheDocument();
    expect(screen.getByText("Ravi Sharma", { selector: "dd" })).toBeInTheDocument();

    const progress = screen.getByRole("navigation", { name: "Progress" });
    const steps = within(progress).getAllByRole("listitem");
    expect(steps.map((s) => s.textContent)).toEqual(["Submitted (done)", "Acknowledged (done)", "In progress", "Resolved"]);
    expect(steps[2]).toHaveAttribute("aria-current", "step");

    const timeline = screen.getByRole("region", { name: "Updates" });
    const entries = within(timeline).getAllByRole("listitem");
    expect(entries.map((e) => e.querySelector("p")?.textContent)).toEqual([
      "Aarav NairReported the issue",
      "CoordinatorMoved it toAcknowledged",
      "CoordinatorAssigned it to Ravi Sharma",
      "Ravi SharmaCommented",
    ]);
    expect(within(timeline).getByText("Electrician booked for Friday.")).toBeInTheDocument();
  });

  it("ends the line at Rejected where it was rejected", async () => {
    const value = issue({
      status: "REJECTED",
      actions: NONE,
      updates: [update(), update({ id: "u2", kind: "STATUS", from_status: "SUBMITTED", to_status: "ACKNOWLEDGED" }), update({ id: "u3", kind: "STATUS", from_status: "ACKNOWLEDGED", to_status: "REJECTED", body: "Not ours." })],
    });
    mockFetch({ [ME]: signedIn({}, MEMBER), [`${ISSUES}/i1`]: one(value) });
    renderRoute("/issues/i1");
    const progress = await screen.findByRole("navigation", { name: "Progress" });
    expect(within(progress).getAllByRole("listitem").map((s) => s.textContent)).toEqual(["Submitted (done)", "Acknowledged (done)", "Rejected"]);
    // Rejected: the reporter can't comment any more (ISSUE-005).
    expect(screen.queryByRole("form", { name: "Add a comment" })).not.toBeInTheDocument();
  });

  it("shows a duplicate's original by status and date only", async () => {
    const value = issue({ status: "REJECTED", actions: NONE, duplicate_of: { id: null, status: "RESOLVED", resolved_at: "2026-10-22T10:00:00Z" } });
    mockFetch({ [ME]: signedIn({}, MEMBER), [`${ISSUES}/i1`]: one(value) });
    renderRoute("/issues/i1");
    const banner = await screen.findByText("Closed as a duplicate");
    const callout = banner.closest("[role=status]") as HTMLElement;
    expect(callout).toHaveTextContent("Resolved");
    expect(within(callout).getByRole("time")).toHaveAttribute("dateTime", "2026-10-22T10:00:00Z");
    expect(within(callout).queryByRole("link")).not.toBeInTheDocument();
  });

  it("marks internal updates for the handling side", async () => {
    const value = issue({ actions: { ...REPORTER, comment_internal: true }, updates: [update(), update({ id: "u2", kind: "COMMENT", body: "Vendor quote pending", is_internal: true, actor_name: "Coordinator" })] });
    mockFetch({ [ME]: signedIn({}, MEMBER), [`${ISSUES}/i1`]: one(value) });
    renderRoute("/issues/i1");
    const timeline = await screen.findByRole("region", { name: "Updates" });
    expect(within(timeline).getByText("Internal")).toBeInTheDocument();
    expect(screen.getByRole("checkbox", { name: "Internal: hidden from the reporter" })).toBeInTheDocument();
  });

  it("lets the reporter comment publicly only", async () => {
    const commented = issue({ updates: [update(), update({ id: "u2", kind: "COMMENT", body: "Smells of smoke too." })] });
    const fetchMock = mockFetch({ [ME]: signedIn({}, MEMBER), [`${ISSUES}/i1`]: one(issue()), [`POST ${ISSUES}/i1/updates`]: () => json(commented, 201) });
    renderRoute("/issues/i1");
    const form = await screen.findByRole("form", { name: "Add a comment" });
    expect(within(form).queryByRole("checkbox")).not.toBeInTheDocument();
    await userEvent.click(within(form).getByRole("button", { name: "Post comment" }));
    expect(await within(form).findByText("Write a comment.")).toBeInTheDocument();
    await userEvent.type(within(form).getByLabelText("Comment"), "Smells of smoke too.");
    await userEvent.click(within(form).getByRole("button", { name: "Post comment" }));
    expect(await screen.findByText("Smells of smoke too.", { selector: "li p" })).toBeInTheDocument();
    expect(sentBody(fetchMock, `${ISSUES}/i1/updates`)).toEqual({ body: "Smells of smoke too.", is_internal: false });
    expect(within(form).getByLabelText("Comment")).toHaveValue("");
  });

  it("offers a reopen only when the server allows it, with a reason", async () => {
    const resolved = issue({ status: "RESOLVED", resolved_at: "2026-10-22T10:00:00Z", version: 4 });
    const reopenable = { ...resolved, actions: { ...REPORTER, transitions: [{ to_status: "ACKNOWLEDGED" as const, needs_note: true }] } };
    const reopened = issue({ status: "ACKNOWLEDGED", version: 5 });
    const fetchMock = mockFetch({ [ME]: signedIn({}, MEMBER), [`${ISSUES}/i1`]: one(reopenable), [`POST ${ISSUES}/i1/transitions`]: () => json(reopened) });
    renderRoute("/issues/i1");
    expect(await screen.findByText(/Still not fixed\? You can reopen it within 14 days/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Reopen issue" }));
    const dialog = screen.getByRole("dialog", { name: "Reopen this issue?" });
    await userEvent.type(within(dialog).getByLabelText("What's still wrong?"), "Still sparks.");
    await userEvent.click(within(dialog).getByRole("button", { name: "Reopen issue" }));
    expect(await screen.findByText("Issue reopened.")).toBeInTheDocument();
    expect(sentBody(fetchMock, `${ISSUES}/i1/transitions`)).toEqual({ to_status: "ACKNOWLEDGED", note: "Still sparks.", version: 4 });
  });

  it("doesn't offer a reopen the server wouldn't allow", async () => {
    mockFetch({ [ME]: signedIn({}, MEMBER), [`${ISSUES}/i1`]: one(issue({ status: "RESOLVED", resolved_at: "2026-10-01T10:00:00Z" })) });
    renderRoute("/issues/i1");
    expect(await screen.findByText(/^Resolved /)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Reopen issue" })).not.toBeInTheDocument();
  });

  it("says when someone else changed it first", async () => {
    const reopenable = issue({ status: "RESOLVED", resolved_at: "2026-10-22T10:00:00Z", actions: { ...REPORTER, transitions: [{ to_status: "ACKNOWLEDGED", needs_note: true }] } });
    mockFetch({
      [ME]: signedIn({}, MEMBER),
      [`${ISSUES}/i1`]: one(reopenable),
      [`POST ${ISSUES}/i1/transitions`]: () => envelope(409, "version_conflict", "This issue was changed by someone else. Reload and try again."),
    });
    renderRoute("/issues/i1");
    await userEvent.click(await screen.findByRole("button", { name: "Reopen issue" }));
    const dialog = screen.getByRole("dialog", { name: "Reopen this issue?" });
    await userEvent.type(within(dialog).getByLabelText("What's still wrong?"), "Again.");
    await userEvent.click(within(dialog).getByRole("button", { name: "Reopen issue" }));
    expect(await screen.findByText("Updated by someone else")).toBeInTheDocument();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Reload the issue" })).toBeInTheDocument();
  });

  it("says an issue it can't show isn't available", async () => {
    mockFetch({ [ME]: signedIn({}, MEMBER), [`${ISSUES}/i1`]: () => envelope(404, "not_found", "Not found.") });
    renderRoute("/issues/i1");
    expect(await screen.findByText("This issue isn't available")).toBeInTheDocument();
  });
});
