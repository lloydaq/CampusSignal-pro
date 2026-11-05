import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import type { Me } from "@/features/auth/api";
import { MEMBER, NORTHFIELD_MEMBERSHIP, signedIn } from "@/test/auth";
import { envelope, json, mockFetch, sentBody } from "@/test/http";
import { renderRoute } from "@/test/render";

import type { Comment, Post } from "./api";
import { initials, relativeTime } from "./labels";
import { linkify } from "./text";

const ME = "/api/v1/me";
const POSTS = "/api/v1/campus/posts";
const COLLEGE_FEED = `${POSTS}?feed=college`;
const DEPT_FEED = `${POSTS}?feed=department`;
const NO_DEPARTMENT: Partial<Me> = { ...MEMBER, membership: { ...NORTHFIELD_MEMBERSHIP, kind: "STAFF", department: null } };

function post(over: Partial<Post> = {}): Post {
  return {
    id: "p1",
    body: "Chess club meets Friday. Details: https://northfield.example/chess.",
    visibility: "COLLEGE",
    department: null,
    author: { name: "Ravi Sharma", kind: "FACULTY" },
    status: "VISIBLE",
    hidden_reason: null,
    edited_at: null,
    created_at: new Date(Date.now() - 5 * 60_000).toISOString(),
    reaction_count: 2,
    comment_count: 1,
    reacted: false,
    can_edit: false,
    can_delete: false,
    can_engage: true,
    ...over,
  };
}

function comment(over: Partial<Comment> = {}): Comment {
  return {
    id: "c1",
    body: "I'll bring a board.",
    author: { name: "Ishita Verma", kind: "STUDENT" },
    status: "VISIBLE",
    hidden_reason: null,
    edited_at: null,
    created_at: new Date().toISOString(),
    can_edit: false,
    can_delete: false,
    ...over,
  };
}

const page = (items: unknown[]) => () => json({ items, next_cursor: null });

function bodyOf(fetchMock: ReturnType<typeof mockFetch>, method: string, path: string): unknown {
  const call = fetchMock.mock.calls.find(([input, init]) => input === path && (init?.method ?? "GET") === method);
  const body = call?.[1]?.body;
  return typeof body === "string" ? (JSON.parse(body) as unknown) : undefined;
}

afterEach(() => window.history.replaceState(null, "", "/"));

describe("the feed", () => {
  it("shows posts with author, role, audience and safe links", async () => {
    mockFetch({ [ME]: signedIn({}, MEMBER), [COLLEGE_FEED]: page([post(), post({ id: "p2", body: "CSE only", visibility: "DEPARTMENT", department: NORTHFIELD_MEMBERSHIP.department, author: { name: "Aarav Nair", kind: "STUDENT" } })]) })
    renderRoute("/community");
    const posts = await screen.findAllByRole("article");
    const first = within(posts[0]!);
    expect(first.getByText("Ravi Sharma")).toBeInTheDocument();
    expect(first.getByText("Faculty")).toBeInTheDocument();
    expect(first.getByText("College")).toBeInTheDocument();
    expect(first.getByText("5 min ago")).toBeInTheDocument();
    const link = first.getByRole("link", { name: "https://northfield.example/chess" });
    expect(link).toHaveAttribute("rel", "noopener noreferrer nofollow");
    expect(first.getByRole("link", { name: "1 comment" })).toHaveAttribute("href", "/community/posts/p1");
    const second = within(posts[1]!);
    expect(second.getByText("Dept · CSE")).toBeInTheDocument();
    expect(second.queryByText("Faculty")).not.toBeInTheDocument(); // students wear no badge
    expect(screen.queryByText("Official")).not.toBeInTheDocument(); // posts are never notices
  });

  it("has College and My department tabs for members of a department", async () => {
    mockFetch({ [ME]: signedIn({}, MEMBER), [COLLEGE_FEED]: page([]), [DEPT_FEED]: page([post({ body: "Department news" })]) });
    renderRoute("/community");
    const tabs = await screen.findByRole("navigation", { name: "Feeds" });
    await userEvent.click(within(tabs).getByRole("link", { name: "My department · CSE" }));
    expect(await screen.findByText("Department news")).toBeInTheDocument();
    expect(within(tabs).getByRole("link", { name: "My department · CSE" })).toHaveAttribute("aria-current", "page");
  });

  it("offers only the college feed without a department", async () => {
    mockFetch({ [ME]: signedIn({}, NO_DEPARTMENT), [COLLEGE_FEED]: page([]) });
    renderRoute("/community?feed=department");
    expect(await screen.findByText("No posts yet. Start the first discussion.")).toBeInTheDocument();
    expect(screen.queryByRole("navigation", { name: "Feeds" })).not.toBeInTheDocument();
  });

  it("offers a retry when the feed fails", async () => {
    mockFetch({ [ME]: signedIn({}, MEMBER), [COLLEGE_FEED]: () => envelope(500, "internal_error", "Something went wrong on our side.") });
    renderRoute("/community");
    expect(await screen.findByText("Couldn't load posts.")).toBeInTheDocument();
  });
});

describe("writing a post", () => {
  it("defaults to the department, shows the badge it will carry, and posts", async () => {
    const fetchMock = mockFetch({
      [ME]: signedIn({}, MEMBER),
      [COLLEGE_FEED]: page([]),
      [`POST ${POSTS}`]: () => json(post({ body: "Hello all" }), 201),
    });
    renderRoute("/community");
    await userEvent.click(await screen.findByRole("button", { name: "Write a post…" }));
    const form = screen.getByRole("form", { name: "Write a post" });
    expect(within(form).getByRole("radio", { name: "My department (CSE)" })).toBeChecked();
    expect(within(form).getByText("Dept · CSE")).toBeInTheDocument();
    await userEvent.click(within(form).getByRole("radio", { name: "The whole college" }));
    expect(within(form).getByText("College")).toBeInTheDocument();
    await userEvent.click(within(form).getByRole("button", { name: "Post" }));
    expect(within(form).getByRole("alert")).toHaveTextContent("Write something first.");
    await userEvent.type(within(form).getByLabelText("Your post"), "  Hello all  ");
    expect(within(form).getByText(/13 \/ 5,000/)).toBeInTheDocument();
    await userEvent.click(within(form).getByRole("button", { name: "Post" }));
    expect(await screen.findByText("Posted.")).toBeInTheDocument();
    expect(sentBody(fetchMock, POSTS)).toEqual({ body: "Hello all", visibility: "COLLEGE" });
  });

  it("explains the hourly limit", async () => {
    mockFetch({
      [ME]: signedIn({}, NO_DEPARTMENT),
      [COLLEGE_FEED]: page([]),
      [`POST ${POSTS}`]: () => envelope(429, "rate_limited", "Too many requests.", null, "r", { "Retry-After": "600" }),
    });
    renderRoute("/community");
    await userEvent.click(await screen.findByRole("button", { name: "Write a post…" }));
    const form = screen.getByRole("form", { name: "Write a post" });
    expect(within(form).queryByRole("radio")).not.toBeInTheDocument(); // no department: college only
    await userEvent.type(within(form).getByLabelText("Your post"), "Again");
    await userEvent.click(within(form).getByRole("button", { name: "Post" }));
    expect(await within(form).findByRole("alert")).toHaveTextContent("You've posted 10 times in the last hour. Try again in 10 minutes.");
  });
});

describe("a post's actions", () => {
  it("toggles Helpful with PUT and DELETE", async () => {
    const fetchMock = mockFetch({
      [ME]: signedIn({}, MEMBER),
      [COLLEGE_FEED]: page([post()]),
      [`PUT ${POSTS}/p1/reaction`]: () => json({ reacted: true, reaction_count: 3 }),
      [`DELETE ${POSTS}/p1/reaction`]: () => json({ reacted: false, reaction_count: 2 }),
    });
    renderRoute("/community");
    const helpful = await screen.findByRole("button", { name: /Helpful/ });
    expect(helpful).toHaveAttribute("aria-pressed", "false");
    await userEvent.click(helpful);
    await waitFor(() => expect(screen.getByRole("button", { name: /Helpful/ })).toHaveAttribute("aria-pressed", "true"));
    expect(screen.getByRole("button", { name: /Helpful/ })).toHaveTextContent("Helpful · 3");
    await userEvent.click(screen.getByRole("button", { name: /Helpful/ }));
    await waitFor(() => expect(screen.getByRole("button", { name: /Helpful/ })).toHaveTextContent("Helpful · 2"));
    const methods = fetchMock.mock.calls.filter(([url]) => url === `${POSTS}/p1/reaction`).map(([, init]) => init?.method);
    expect(methods).toEqual(["PUT", "DELETE"]);
  });

  it("offers the author Edit and Delete, everyone else Report", async () => {
    mockFetch({ [ME]: signedIn({}, MEMBER), [COLLEGE_FEED]: page([post({ id: "mine", can_edit: true, can_delete: true }), post({ id: "theirs" })]) });
    renderRoute("/community");
    const [mine, theirs] = await screen.findAllByRole("article");
    await userEvent.click(within(mine!).getByRole("button", { name: "Post actions" }));
    expect(within(mine!).getAllByRole("button").map((b) => b.textContent)).toEqual(expect.arrayContaining(["Edit", "Delete"]));
    expect(within(mine!).queryByRole("button", { name: "Report" })).not.toBeInTheDocument();
    await userEvent.click(within(theirs!).getByRole("button", { name: "Post actions" }));
    expect(within(theirs!).getByRole("button", { name: "Report" })).toBeInTheDocument();
    expect(within(theirs!).queryByRole("button", { name: "Edit" })).not.toBeInTheDocument();
  });

  it("edits in place", async () => {
    const fetchMock = mockFetch({
      [ME]: signedIn({}, MEMBER),
      [COLLEGE_FEED]: page([post({ can_edit: true, can_delete: true })]),
      [`PATCH ${POSTS}/p1`]: () => json(post({ body: "Chess moved to Saturday", can_edit: true, can_delete: true, edited_at: new Date().toISOString() })),
    });
    renderRoute("/community");
    await userEvent.click(await screen.findByRole("button", { name: "Post actions" }));
    await userEvent.click(screen.getByRole("button", { name: "Edit" }));
    const box = screen.getByLabelText("Edit your post");
    await userEvent.clear(box);
    await userEvent.type(box, "Chess moved to Saturday");
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByText("Chess moved to Saturday")).toBeInTheDocument();
    expect(screen.getByText(/· edited/)).toBeInTheDocument();
    expect(sentBody(fetchMock, `${POSTS}/p1`)).toEqual({ body: "Chess moved to Saturday" });
  });

  it("deletes after confirming", async () => {
    mockFetch({ [ME]: signedIn({}, MEMBER), [COLLEGE_FEED]: page([post({ can_delete: true })]), [`DELETE ${POSTS}/p1`]: () => new Response(null, { status: 204 }) });
    renderRoute("/community");
    await userEvent.click(await screen.findByRole("button", { name: "Post actions" }));
    await userEvent.click(screen.getByRole("button", { name: "Delete" }));
    await userEvent.click(within(screen.getByRole("dialog", { name: "Delete this post?" })).getByRole("button", { name: "Delete post" }));
    await waitFor(() => expect(screen.queryByRole("article")).not.toBeInTheDocument());
  });

  it("reports with a reason", async () => {
    const fetchMock = mockFetch({ [ME]: signedIn({}, MEMBER), [COLLEGE_FEED]: page([post()]), [`POST /api/v1/campus/reports`]: () => json({ id: "r1", status: "OPEN" }, 201) });
    renderRoute("/community");
    await userEvent.click(await screen.findByRole("button", { name: "Post actions" }));
    await userEvent.click(screen.getByRole("button", { name: "Report" }));
    const dialog = screen.getByRole("dialog", { name: "Report this post?" });
    await userEvent.click(within(dialog).getByRole("button", { name: "Send report" }));
    expect(within(dialog).getByText("Choose a reason.")).toBeInTheDocument();
    await userEvent.click(within(dialog).getByRole("radio", { name: "Spam" }));
    await userEvent.type(within(dialog).getByLabelText(/Anything they should know/), "Posted five times");
    await userEvent.click(within(dialog).getByRole("button", { name: "Send report" }));
    expect(await screen.findByText("Thanks. Moderators will look at it.")).toBeInTheDocument();
    expect(sentBody(fetchMock, "/api/v1/campus/reports")).toEqual({ post_id: "p1", reason: "SPAM", note: "Posted five times" });
  });
});

describe("a post's page", () => {
  it("lists comments oldest first and takes a new one", async () => {
    const fetchMock = mockFetch({
      [ME]: signedIn({}, MEMBER),
      [`${POSTS}/p1`]: () => json(post()),
      [`${POSTS}/p1/comments`]: (init) => (init?.method === "POST" ? json(comment({ id: "c2", body: "Count me in" }), 201) : json({ items: [comment()], next_cursor: null })),
    });
    renderRoute("/community/posts/p1");
    const comments = await screen.findByRole("region", { name: "Comments" });
    expect(await within(comments).findByText("I'll bring a board.")).toBeInTheDocument();
    await userEvent.type(within(comments).getByLabelText("Comment"), "Count me in");
    await userEvent.click(within(comments).getByRole("button", { name: "Post comment" }));
    await waitFor(() => expect(bodyOf(fetchMock, "POST", `${POSTS}/p1/comments`)).toEqual({ body: "Count me in" }));
  });

  it("shows the author why their post was hidden, and freezes it", async () => {
    mockFetch({
      [ME]: signedIn({}, MEMBER),
      [`${POSTS}/p1`]: () => json(post({ status: "HIDDEN", hidden_reason: "Names a person", can_delete: true, can_engage: false })),
      [`${POSTS}/p1/comments`]: page([]),
    });
    renderRoute("/community/posts/p1");
    expect(await screen.findByText("Hidden by a moderator")).toBeInTheDocument();
    expect(screen.getByText(/Only you and moderators can see it\. Reason: Names a person/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Helpful/ })).toBeDisabled();
    expect(screen.queryByRole("form", { name: "Add a comment" })).not.toBeInTheDocument();
  });

  it("says a post it can't show isn't available", async () => {
    mockFetch({ [ME]: signedIn({}, MEMBER), [`${POSTS}/p1`]: () => envelope(404, "not_found", "Not found.") });
    renderRoute("/community/posts/p1");
    expect(await screen.findByText("This post isn't available")).toBeInTheDocument();
  });
});

describe("text helpers", () => {
  it("links only web addresses, leaving sentence punctuation out", () => {
    expect(linkify("See https://a.example/x. Or javascript:alert(1) or www.b.example")).toEqual([
      { text: "See " },
      { href: "https://a.example/x" },
      { text: ". Or javascript:alert(1) or www.b.example" },
    ]);
    expect(linkify("(http://c.example/path)")).toEqual([{ text: "(" }, { href: "http://c.example/path" }, { text: ")" }]);
  });

  it("makes initials and relative times", () => {
    expect(initials("Ravi Kumar Sharma")).toBe("RS");
    expect(initials("Meera")).toBe("M");
    const now = new Date("2026-11-05T12:00:00Z");
    expect(relativeTime("2026-11-05T11:59:40Z", now)).toBe("Just now");
    expect(relativeTime("2026-11-05T09:00:00Z", now)).toBe("3 h ago");
    expect(relativeTime("2026-11-04T09:00:00Z", now)).toBe("Yesterday");
  });
});
