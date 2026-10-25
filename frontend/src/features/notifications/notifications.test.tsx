import { focusManager } from "@tanstack/react-query";
import { act, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { MEMBER, signedIn } from "@/test/auth";
import { envelope, json, mockFetch, requestsTo } from "@/test/http";
import { renderRoute } from "@/test/render";

import { POLL_MS, type Notification } from "./api";

const ME = "/api/v1/me";
const LIST = "/api/v1/me/notifications";
const COUNT = "/api/v1/me/notifications/unread-count";

function notification(over: Partial<Notification> = {}): Notification {
  return {
    id: "a1",
    type: "NOTICE_PUBLISHED",
    title: "Urgent notice: Campus closed tomorrow",
    subject_type: "NOTICE",
    subject_id: "n1",
    read: false,
    created_at: "2026-10-24T04:30:00Z",
    ...over,
  };
}

/** The rail item's name comes from its text, so browsers may space it differently from the top bar's label. */
const unreadName = (n: number) => new RegExp(`^Notifications\\s*, ${n} unread$`);
const page = (items: Notification[], next_cursor: string | null = null) => () => json({ items, next_cursor });
const gets = (fetchMock: ReturnType<typeof mockFetch>, path: string) => requestsTo(fetchMock, path).filter((r) => r.method === "GET").length;

afterEach(() => {
  window.history.replaceState(null, "", "/");
  vi.useRealTimers();
});

describe("notification bell", () => {
  it("shows the unread count in the rail and the top bar and links to the notifications page", async () => {
    mockFetch({ [ME]: signedIn({}, MEMBER), [COUNT]: () => json({ unread: 3 }), "/api/v1/campus/notices": page([]), "/api/v1/campus/departments": page([]) });
    renderRoute("/home");
    const bells = await screen.findAllByRole("link", { name: unreadName(3) });
    expect(bells).toHaveLength(2);
    for (const bell of bells) expect(bell).toHaveAttribute("href", "/notifications");
  });

  it("says just Notifications when nothing is unread", async () => {
    mockFetch({ [ME]: signedIn({}, MEMBER) });
    renderRoute("/home");
    expect(await screen.findAllByRole("link", { name: "Notifications" })).toHaveLength(2);
    expect(screen.queryByText("0")).not.toBeInTheDocument();
  });

  it("refreshes the count every 60 seconds and when the window regains focus (NOTIF-005)", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    let unread = 1;
    const fetchMock = mockFetch({ [ME]: signedIn({}, MEMBER), [COUNT]: () => json({ unread }) });
    renderRoute("/home");
    expect(await screen.findAllByRole("link", { name: unreadName(1) })).toHaveLength(2);
    const first = gets(fetchMock, COUNT);

    unread = 2;
    await act(() => vi.advanceTimersByTimeAsync(POLL_MS));
    expect(await screen.findAllByRole("link", { name: unreadName(2) })).toHaveLength(2);
    expect(gets(fetchMock, COUNT)).toBe(first + 1);

    unread = 4;
    act(() => {
      focusManager.setFocused(false);
      focusManager.setFocused(true);
    });
    expect(await screen.findAllByRole("link", { name: unreadName(4) })).toHaveLength(2);
    act(() => focusManager.setFocused(undefined));
  });
});

describe("notifications page", () => {
  it("lists unread and read notifications with links to what they are about", async () => {
    mockFetch({
      [ME]: signedIn({}, MEMBER),
      [COUNT]: () => json({ unread: 1 }),
      [LIST]: page([
        notification(),
        notification({ id: "a2", type: "MEMBERSHIP_DECIDED", title: "You've joined Northfield Institute", subject_type: "MEMBERSHIP", subject_id: "r1", read: true }),
      ]),
    });
    renderRoute("/notifications");
    const list = await screen.findByRole("list", { name: "Notifications" });
    const [urgent, joined] = within(list).getAllByRole("link");
    expect(urgent).toHaveAttribute("href", "/notices/n1");
    expect(urgent).toHaveTextContent("Unread: Urgent notice: Campus closed tomorrow");
    expect(urgent).toHaveTextContent("24 Oct 2026, 10:00"); // college time zone
    expect(joined).toHaveAttribute("href", "/home");
    expect(joined).not.toHaveTextContent("Unread");
    expect(document.title).toBe("Notifications · CampusSignal");
  });

  it("marks a notification read when it is opened", async () => {
    const fetchMock = mockFetch({
      [ME]: signedIn({}, MEMBER),
      [COUNT]: () => json({ unread: 1 }),
      [LIST]: page([notification()]),
      [`POST ${LIST}/a1/read`]: () => json(notification({ read: true })),
      "/api/v1/campus/notices/n1": () => envelope(404, "not_found", "Not found."),
    });
    renderRoute("/notifications");
    await userEvent.click(await screen.findByRole("link", { name: /Campus closed tomorrow/ }));
    await waitFor(() => expect(requestsTo(fetchMock, `${LIST}/a1/read`)).toHaveLength(1));
  });

  it("does not mark an already read notification again", async () => {
    const fetchMock = mockFetch({
      [ME]: signedIn({}, MEMBER),
      [LIST]: page([notification({ read: true })]),
      "/api/v1/campus/notices/n1": () => envelope(404, "not_found", "Not found."),
    });
    renderRoute("/notifications");
    await userEvent.click(await screen.findByRole("link", { name: /Campus closed tomorrow/ }));
    expect(requestsTo(fetchMock, `${LIST}/a1/read`)).toHaveLength(0);
  });

  it("marks all as read and brings the count to zero", async () => {
    let read = false;
    const fetchMock = mockFetch({
      [ME]: signedIn({}, MEMBER),
      [COUNT]: () => json({ unread: read ? 0 : 2 }),
      [LIST]: () => json({ items: [notification({ read }), notification({ id: "a3", subject_id: "n3", read })], next_cursor: null }),
      [`POST ${LIST}/read-all`]: () => {
        read = true;
        return json({ marked: 2 });
      },
    });
    renderRoute("/notifications");
    await userEvent.click(await screen.findByRole("button", { name: "Mark all as read" }));
    expect(await screen.findAllByRole("link", { name: "Notifications" })).toHaveLength(2);
    expect(screen.queryByRole("button", { name: "Mark all as read" })).not.toBeInTheDocument();
    expect(screen.queryByText(/Unread:/)).not.toBeInTheDocument();
    expect(requestsTo(fetchMock, `${LIST}/read-all`)).toHaveLength(1);
  });

  it("explains a failed mark-all-read", async () => {
    mockFetch({
      [ME]: signedIn({}, MEMBER),
      [COUNT]: () => json({ unread: 1 }),
      [LIST]: page([notification()]),
      [`POST ${LIST}/read-all`]: () => envelope(500, "internal_error", "Something went wrong on our side."),
    });
    renderRoute("/notifications");
    await userEvent.click(await screen.findByRole("button", { name: "Mark all as read" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Couldn't mark notifications as read.");
  });

  it("loads more with the cursor", async () => {
    const fetchMock = mockFetch({
      [ME]: signedIn({}, MEMBER),
      [LIST]: page([notification({ read: true })], "c2"),
      [`${LIST}?cursor=c2`]: page([notification({ id: "a9", title: "Older notice", read: true })]),
    });
    renderRoute("/notifications");
    await userEvent.click(await screen.findByRole("button", { name: "Load more" }));
    expect(await screen.findByText("Older notice")).toBeInTheDocument();
    expect(requestsTo(fetchMock, `${LIST}?cursor=c2`)).toHaveLength(1);
  });

  it("shows an empty state", async () => {
    mockFetch({ [ME]: signedIn({}, MEMBER), [LIST]: page([]) });
    renderRoute("/notifications");
    expect(await screen.findByText("No notifications.")).toBeInTheDocument();
  });

  it("shows an error with the request ID and retries", async () => {
    let fail = true;
    mockFetch({
      [ME]: signedIn({}, MEMBER),
      [LIST]: () => (fail ? envelope(500, "internal_error", "Something went wrong on our side.", null, "req-n500") : json({ items: [], next_cursor: null })),
    });
    renderRoute("/notifications");
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Couldn't load notifications.");
    expect(alert).toHaveTextContent("req-n500");
    fail = false;
    await userEvent.click(within(alert).getByRole("button", { name: "Try again" }));
    expect(await screen.findByText("No notifications.")).toBeInTheDocument();
  });

  it("is open to someone without a college, who sees a rejection", async () => {
    mockFetch({
      [ME]: signedIn(),
      [COUNT]: () => json({ unread: 1 }),
      [LIST]: page([
        notification({ type: "MEMBERSHIP_DECIDED", title: "Your request to join Riverside College wasn't approved", subject_type: "MEMBERSHIP", subject_id: "r2" }),
      ]),
    });
    renderRoute("/notifications");
    const row = await screen.findByRole("link", { name: /wasn't approved/ });
    expect(row).toHaveAttribute("href", "/home");
  });

  it("shows unknown kinds of notification without a link", async () => {
    mockFetch({ [ME]: signedIn({}, MEMBER), [LIST]: page([notification({ type: "ISSUE_STATUS_CHANGED", subject_type: "ISSUE", title: "Your issue was updated", read: true })]) });
    renderRoute("/notifications");
    const list = await screen.findByRole("list", { name: "Notifications" });
    expect(within(list).getByText("Your issue was updated")).toBeInTheDocument();
    expect(within(list).queryByRole("link")).not.toBeInTheDocument();
  });
});
