import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import type { NoticeSummary } from "@/features/notices/api";
import { MEMBER, signedIn } from "@/test/auth";
import { envelope, json, mockFetch } from "@/test/http";
import { renderRoute } from "@/test/render";

const ME = "/api/v1/me";
const NOTICES = "/api/v1/campus/notices";
const COUNT = "/api/v1/me/notifications/unread-count";

function summary(id: string, over: Partial<NoticeSummary> = {}): NoticeSummary {
  return {
    id,
    title: `Notice ${id}`,
    excerpt: "",
    category: "GENERAL",
    priority: "NORMAL",
    scope: "COLLEGE",
    department: null,
    status: "PUBLISHED",
    pinned: false,
    expired: false,
    published_at: "2026-10-20T04:30:00Z",
    expires_at: null,
    edited_at: null,
    created_at: "2026-10-20T04:00:00Z",
    can_manage: false,
    ...over,
  };
}

const page = (items: NoticeSummary[]) => () => json({ items, next_cursor: null });

describe("home notice blocks (HOME-001, brought forward)", () => {
  it("shows urgent notices first, then the five latest others, with a link to all notices", async () => {
    mockFetch({
      [ME]: signedIn({}, MEMBER),
      [NOTICES]: page([
        summary("u1", { title: "Campus closed tomorrow", priority: "URGENT", pinned: true }),
        ...["a", "b", "c", "d", "e", "f"].map((id) => summary(id)),
      ]),
    });
    renderRoute("/home");
    const urgent = await screen.findByRole("region", { name: "Urgent now" });
    expect(within(urgent).getByRole("link", { name: /Campus closed tomorrow/ })).toHaveAttribute("href", "/notices/u1");
    const latest = screen.getByRole("region", { name: "Latest notices" });
    expect(within(latest).getAllByRole("listitem")).toHaveLength(5);
    expect(within(latest).queryByText("Campus closed tomorrow")).not.toBeInTheDocument();
    expect(within(latest).getByRole("link", { name: "All notices" })).toHaveAttribute("href", "/notices");
    // The membership stays below the notices.
    expect(screen.getByRole("region", { name: "Your membership" })).toBeInTheDocument();
  });

  it("leaves out the urgent block when nothing is urgent", async () => {
    mockFetch({ [ME]: signedIn({}, MEMBER), [NOTICES]: page([summary("a")]) });
    renderRoute("/home");
    expect(await screen.findByText("Notice a")).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Urgent now" })).not.toBeInTheDocument();
  });

  it("says so when there are no current notices", async () => {
    mockFetch({ [ME]: signedIn({}, MEMBER), [NOTICES]: page([]) });
    renderRoute("/home");
    expect(await screen.findByText("No current notices.")).toBeInTheDocument();
  });

  it("keeps the rest of the home when the notices fail, and retries", async () => {
    let fail = true;
    mockFetch({
      [ME]: signedIn({}, MEMBER),
      [NOTICES]: () => (fail ? envelope(500, "internal_error", "Something went wrong on our side.") : json({ items: [summary("a")], next_cursor: null })),
    });
    renderRoute("/home");
    const latest = await screen.findByRole("region", { name: "Latest notices" });
    const alert = await within(latest).findByRole("alert");
    expect(alert).toHaveTextContent("Couldn't load notices.");
    expect(screen.getByRole("link", { name: "Computer Science (CSE)" })).toBeInTheDocument();
    fail = false;
    await userEvent.click(within(alert).getByRole("button", { name: "Try again" }));
    expect(await screen.findByText("Notice a")).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("links unread notifications only when there are some", async () => {
    mockFetch({ [ME]: signedIn({}, MEMBER), [NOTICES]: page([]), [COUNT]: () => json({ unread: 3 }) });
    renderRoute("/home");
    expect(await screen.findByRole("link", { name: "3 unread notifications" })).toHaveAttribute("href", "/notifications");
  });

  it("has no unread link when everything is read", async () => {
    mockFetch({ [ME]: signedIn({}, MEMBER), [NOTICES]: page([]) });
    renderRoute("/home");
    await screen.findByText("No current notices.");
    expect(screen.queryByRole("link", { name: /unread notification/ })).not.toBeInTheDocument();
  });
});
