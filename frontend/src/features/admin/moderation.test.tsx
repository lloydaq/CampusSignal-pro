import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import type { Me } from "@/features/auth/api";
import { MEMBER, signedIn } from "@/test/auth";
import { envelope, json, mockFetch } from "@/test/http";
import { renderRoute } from "@/test/render";

const ME = "/api/v1/me";
const QUEUE = "/api/v1/campus/moderation/reports";
const CSE = { id: "d0000000-0000-4000-8000-000000000001", code: "CSE", name: "Computer Science" };

const ADMIN: Partial<Me> = {
  ...MEMBER,
  membership: { ...MEMBER.membership!, kind: "STAFF", department: null },
  roles: [{ role: "COLLEGE_ADMIN", department: null }],
  capabilities: ["campus", "manage_college", "review_memberships", "moderate_community"],
};

const REPORT = {
  id: "r1",
  reason: "MISINFORMATION",
  note: "Nobody announced this.",
  status: "OPEN",
  created_at: "2026-10-24T05:00:00Z",
  handled_at: null,
  open_reports: 3,
  content: {
    type: "post",
    post_id: "p1",
    comment_id: null,
    body: "The hostel closes for good next week.",
    author: { name: "Kabir Shah", kind: "STUDENT" },
    visibility: "DEPARTMENT",
    department: CSE,
    status: "VISIBLE",
    hidden_reason: null,
  },
};

const page = <T,>(items: T[]) => json({ items, next_cursor: null });

function bodyOf(fetchMock: ReturnType<typeof mockFetch>, path: string): unknown {
  const call = fetchMock.mock.calls.find(([input, init]) => input === path && init?.method === "POST");
  return typeof call?.[1]?.body === "string" ? (JSON.parse(call[1].body) as unknown) : undefined;
}

afterEach(() => window.history.replaceState(null, "", "/"));

describe("Manage → Moderation", () => {
  it("shows a report: why, the note, how many, and the content with its audience and author", async () => {
    mockFetch({ [ME]: signedIn({}, ADMIN), [`${QUEUE}?status=OPEN`]: () => page([REPORT]) });
    renderRoute("/manage/moderation");
    const row = within(await screen.findByRole("list", { name: "Open reports" })).getByRole("listitem");
    expect(row).toHaveTextContent("False information");
    expect(row).toHaveTextContent("3 open reports on this post");
    expect(row).toHaveTextContent("Reporter's note: Nobody announced this.");
    expect(row).toHaveTextContent("Post by Kabir Shah");
    expect(within(row).getByText("Dept · CSE")).toBeInTheDocument();
    expect(within(row).getByText("The hostel closes for good next week.")).toBeInTheDocument();
    expect(within(row).getByRole("link", { name: "Open the post" })).toHaveAttribute("href", "/community/posts/p1");
  });

  it("hides with the reason its author reads, then refreshes the queue", async () => {
    let open = [REPORT];
    const fetchMock = mockFetch({
      [ME]: signedIn({}, ADMIN),
      [`${QUEUE}?status=OPEN`]: () => page(open),
      [`POST ${QUEUE}/r1/resolve`]: () => {
        open = [];
        return json({ action: "HIDE", closed_reports: 3 });
      },
    });
    renderRoute("/manage/moderation");
    await userEvent.click(await screen.findByRole("button", { name: "Hide post" }));
    const dialog = screen.getByRole("dialog", { name: "Hide this post?" });
    await userEvent.click(within(dialog).getByRole("button", { name: "Hide post" }));
    expect(within(dialog).getByText("Give a reason.")).toBeInTheDocument(); // required
    expect(fetchMock).not.toHaveBeenCalledWith(`${QUEUE}/r1/resolve`, expect.anything());
    await userEvent.type(within(dialog).getByLabelText(/Reason \(its author sees this\)/), "Unverified claim");
    await userEvent.click(within(dialog).getByRole("button", { name: "Hide post" }));
    expect(await screen.findByText("Post hidden. Its author has been told why. 2 other reports on it closed too.")).toBeInTheDocument();
    expect(bodyOf(fetchMock, `${QUEUE}/r1/resolve`)).toEqual({ action: "HIDE", reason: "Unverified claim" });
    expect(await screen.findByText("No reports to review.")).toBeInTheDocument();
  });

  it("dismisses without a reason; the post stays up", async () => {
    const fetchMock = mockFetch({
      [ME]: signedIn({}, ADMIN),
      [`${QUEUE}?status=OPEN`]: () => page([{ ...REPORT, open_reports: 1 }]),
      [`POST ${QUEUE}/r1/resolve`]: () => json({ action: "DISMISS", closed_reports: 1 }),
    });
    renderRoute("/manage/moderation");
    expect(await screen.findByText("False information")).toBeInTheDocument();
    expect(screen.queryByText(/open reports on this/)).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Dismiss" }));
    const dialog = screen.getByRole("dialog", { name: "Dismiss this report?" });
    await userEvent.click(within(dialog).getByRole("button", { name: "Dismiss report" }));
    expect(await screen.findByText("Report dismissed. The post stays up.")).toBeInTheDocument();
    expect(bodyOf(fetchMock, `${QUEUE}/r1/resolve`)).toEqual({ action: "DISMISS" });
  });

  it("says when someone else already handled it", async () => {
    mockFetch({
      [ME]: signedIn({}, ADMIN),
      [`${QUEUE}?status=OPEN`]: () => page([REPORT]),
      [`POST ${QUEUE}/r1/resolve`]: () => envelope(409, "already_resolved", "This report has already been handled."),
    });
    renderRoute("/manage/moderation");
    await userEvent.click(await screen.findByRole("button", { name: "Dismiss" }));
    const dialog = screen.getByRole("dialog", { name: "Dismiss this report?" });
    await userEvent.click(within(dialog).getByRole("button", { name: "Dismiss report" }));
    expect(await within(dialog).findByRole("alert")).toHaveTextContent("This report has already been handled.");
  });

  it("lists hidden content with when and the reason given, and offers no actions", async () => {
    const hidden = { ...REPORT, status: "ACTIONED", handled_at: "2026-10-24T06:00:00Z", open_reports: 0, content: { ...REPORT.content, status: "HIDDEN", hidden_reason: "Unverified claim" } };
    mockFetch({ [ME]: signedIn({}, ADMIN), [`${QUEUE}?status=ACTIONED`]: () => page([hidden]) });
    renderRoute("/manage/moderation?status=ACTIONED");
    const row = within(await screen.findByRole("list", { name: "Hidden" })).getByRole("listitem");
    expect(row).toHaveTextContent(/Hidden .*Reason given to its author: Unverified claim/);
    expect(within(row).queryByRole("button")).not.toBeInTheDocument();
    expect(screen.getByLabelText("Show")).toHaveValue("ACTIONED");
  });

  it("switches views from the Show menu and has empty states", async () => {
    mockFetch({ [ME]: signedIn({}, ADMIN), [`${QUEUE}?status=OPEN`]: () => page([]), [`${QUEUE}?status=DISMISSED`]: () => page([]) });
    const { router } = renderRoute("/manage/moderation");
    expect(await screen.findByText("No reports to review.")).toBeInTheDocument();
    await userEvent.selectOptions(screen.getByLabelText("Show"), "DISMISSED");
    expect(await screen.findByText("No reports have been dismissed yet.")).toBeInTheDocument();
    await waitFor(() => expect(router.state.location.search).toBe("?status=DISMISSED"));
  });

  it("shows an error state when the queue can't load", async () => {
    mockFetch({ [ME]: signedIn({}, ADMIN), [`${QUEUE}?status=OPEN`]: () => envelope(500, "internal_error", "Something went wrong.") });
    renderRoute("/manage/moderation");
    expect(await screen.findByText("Couldn't load the reports.")).toBeInTheDocument();
  });

  it("sends members without the capability away", async () => {
    mockFetch({ [ME]: signedIn({}, { ...ADMIN, capabilities: ["campus", "review_memberships"] }), "/api/v1/campus/membership-requests": () => page([]) });
    const { router } = renderRoute("/manage/moderation");
    await waitFor(() => expect(router.state.location.pathname).toBe("/manage/requests"));
  });
});
