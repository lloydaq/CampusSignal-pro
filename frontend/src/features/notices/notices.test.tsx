import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import type { Me } from "@/features/auth/api";
import { MEMBER, signedIn } from "@/test/auth";
import { envelope, json, mockFetch } from "@/test/http";
import { renderRoute } from "@/test/render";

import type { Notice, NoticeSummary } from "./api";

const ME = "/api/v1/me";
const N = "/api/v1/campus/notices";
const DEPTS = "/api/v1/campus/departments";
const CSE = { id: "d0000000-0000-4000-8000-000000000001", code: "CSE", name: "Computer Science" };
const MECH = { id: "d0000000-0000-4000-8000-000000000002", code: "MECH", name: "Mechanical" };

const ADMIN: Partial<Me> = {
  ...MEMBER,
  roles: [{ role: "COLLEGE_ADMIN", department: null }],
  capabilities: ["campus", "manage_college", "review_memberships"],
};
const CSE_ADMIN: Partial<Me> = { ...MEMBER, roles: [{ role: "DEPARTMENT_ADMIN", department: CSE }], capabilities: ["campus", "review_memberships"] };

function summary(over: Partial<NoticeSummary> = {}): NoticeSummary {
  return {
    id: "n1",
    title: "Exam timetable",
    excerpt: "Exams start Monday.",
    category: "EXAMINATION",
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

function notice(over: Partial<Notice> = {}): Notice {
  return { ...summary(), body: "Exams start **Monday**.", version: 2, author_name: null, ...over };
}

const page = (items: unknown[], next_cursor: string | null = null) => () => json({ items, next_cursor });
const departments = () => json({ items: [{ ...CSE, description: "", archived: false }, { ...MECH, description: "", archived: false }] });

function bodyOf(fetchMock: ReturnType<typeof mockFetch>, method: string, path: string): unknown {
  const call = fetchMock.mock.calls.find(([input, init]) => input === path && (init?.method ?? "GET") === method);
  const body = call?.[1]?.body;
  return typeof body === "string" ? (JSON.parse(body) as unknown) : undefined;
}

afterEach(() => window.history.replaceState(null, "", "/"));

describe("notices list", () => {
  it("shows urgent notices pinned first, with audience badges, and no compose button for readers", async () => {
    mockFetch({
      [ME]: signedIn({}, MEMBER),
      [DEPTS]: departments,
      [N]: page([
        summary({ id: "u", title: "Campus closed tomorrow", priority: "URGENT", pinned: true }),
        summary({ id: "d", title: "Lab schedule", scope: "DEPARTMENT", department: CSE }),
      ]),
    });
    renderRoute("/notices");
    const urgent = await screen.findByRole("region", { name: "Urgent" });
    expect(within(urgent).getByText("Campus closed tomorrow")).toBeInTheDocument();
    expect(within(urgent).getByText("College")).toBeInTheDocument();
    const latest = screen.getByRole("region", { name: "Latest" });
    expect(within(latest).getByText("Dept · CSE")).toBeInTheDocument();
    expect(within(latest).getByRole("link", { name: /Lab schedule/ })).toHaveAttribute("href", "/notices/d");
    expect(screen.getAllByText(/20 Oct 2026, 10:00/).length).toBe(2); // college time zone
    expect(screen.queryByRole("link", { name: "New notice" })).not.toBeInTheDocument();
    const views = screen.getByRole("navigation", { name: "Notice views" });
    expect(within(views).getAllByRole("link").map((l) => l.textContent)).toEqual(["Current", "Past notices"]);
  });

  it("states plainly when there is nothing", async () => {
    mockFetch({ [ME]: signedIn({}, MEMBER), [DEPTS]: departments, [N]: page([]) });
    renderRoute("/notices");
    expect(await screen.findByText("No current notices.")).toBeInTheDocument();
  });

  it("filters by category and department, and shows past notices", async () => {
    const fetchMock = mockFetch({
      [ME]: signedIn({}, MEMBER),
      [DEPTS]: departments,
      [N]: page([summary()]),
      [`${N}?category=EVENT`]: page([]),
      [`${N}?category=EVENT&department_id=${MECH.id}`]: page([]),
      [`${N}?past=true`]: page([summary({ id: "old", title: "Old notice", expired: true })]),
    });
    const { router } = renderRoute("/notices");
    await screen.findByText("Exam timetable");
    await userEvent.selectOptions(screen.getByLabelText("Category"), "EVENT");
    expect(await screen.findByText("No notices match these filters.")).toBeInTheDocument();
    await userEvent.selectOptions(await screen.findByLabelText("Department"), "Mechanical");
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(`${N}?category=EVENT&department_id=${MECH.id}`, expect.anything()));
    expect(router.state.location.search).toBe(`?category=EVENT&department=${MECH.id}`);

    await router.navigate("/notices?view=past");
    expect(await screen.findByText("Old notice")).toBeInTheDocument();
    expect(screen.getByText("Expired")).toBeInTheDocument();
  });

  it("gives publishers a compose button and their drafts and withdrawn notices", async () => {
    mockFetch({
      [ME]: signedIn({}, ADMIN),
      [DEPTS]: departments,
      [N]: page([]),
      [`${N}?status=DRAFT`]: page([summary({ id: "dr", title: "Sports day draft", status: "DRAFT", published_at: null, can_manage: true })]),
    });
    renderRoute("/notices?view=drafts");
    expect(await screen.findByText("Sports day draft")).toBeInTheDocument();
    expect(screen.getByText("Draft")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "New notice" })).toHaveAttribute("href", "/notices/new");
    const views = screen.getByRole("navigation", { name: "Notice views" });
    expect(within(views).getByRole("link", { name: "Drafts" })).toHaveAttribute("aria-current", "page");
  });

  it("ignores manager views in the URL for readers", async () => {
    const fetchMock = mockFetch({ [ME]: signedIn({}, MEMBER), [DEPTS]: departments, [N]: page([]) });
    renderRoute("/notices?view=drafts");
    expect(await screen.findByText("No current notices.")).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalledWith(`${N}?status=DRAFT`, expect.anything());
  });

  it("sends people without a college to the join flow", async () => {
    mockFetch({ [ME]: signedIn(), "/api/v1/colleges": () => json({ items: [] }), "/api/v1/me/membership-requests": () => json({ items: [] }) });
    const { router } = renderRoute("/notices");
    await waitFor(() => expect(router.state.location.pathname).toBe("/join"));
  });
});

describe("a notice", () => {
  it("shows the official notice with its issuer, dates and safe Markdown", async () => {
    mockFetch({
      [ME]: signedIn({}, MEMBER),
      [`${N}/n1`]: () =>
        json(
          notice({
            scope: "DEPARTMENT",
            department: CSE,
            edited_at: "2026-10-21T06:00:00Z",
            expires_at: "2026-10-30T12:00:00Z",
            body: "Exams start **Monday**.\n\n<script>alert(1)</script>",
          }),
        ),
    });
    renderRoute("/notices/n1");
    expect(await screen.findByRole("heading", { level: 1, name: "Exam timetable" })).toBeInTheDocument();
    expect(screen.getByText(/Official/).closest("p")).toHaveTextContent("Official · Computer Science");
    await waitFor(() => expect(screen.getByText("Monday").tagName).toBe("STRONG")); // renderer loads lazily
    expect(document.querySelector("article script")).toBeNull();
    expect(screen.getByText("Published").nextSibling).toHaveTextContent("20 Oct 2026, 10:00");
    expect(screen.getByText("Updated").nextSibling).toHaveTextContent("21 Oct 2026, 11:30");
    expect(screen.getByText("Expires").nextSibling).toHaveTextContent("30 Oct 2026, 5:30");
    expect(screen.queryByRole("region", { name: "Manage this notice" })).not.toBeInTheDocument();
    expect(screen.queryByText(/posted by/)).not.toBeInTheDocument();
  });

  it("says when a notice isn't available, without guessing why", async () => {
    mockFetch({ [ME]: signedIn({}, MEMBER), [`${N}/gone`]: () => envelope(404, "not_found", "Not found.") });
    renderRoute("/notices/gone");
    expect(await screen.findByText("This notice isn't available")).toBeInTheDocument();
  });

  it("lets a manager publish a draft", async () => {
    let published = false;
    const fetchMock = mockFetch({
      [ME]: signedIn({}, ADMIN),
      [`${N}/n1`]: () => json(notice({ status: published ? "PUBLISHED" : "DRAFT", published_at: null, version: 1, can_manage: true, author_name: "Priya Menon", priority: "URGENT" })),
      [`${N}/n1/publish`]: () => {
        published = true;
        return json(notice({ status: "PUBLISHED", version: 2, can_manage: true, author_name: "Priya Menon" }));
      },
    });
    renderRoute("/notices/n1");
    expect(await screen.findByText(/notified when it's published/)).toBeInTheDocument();
    expect(screen.getByText(/posted by Priya Menon/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Publish" }));
    expect(await screen.findByText("Notice published.")).toBeInTheDocument();
    expect(bodyOf(fetchMock, "POST", `${N}/n1/publish`)).toEqual({ version: 1 });
    expect(screen.queryByRole("button", { name: "Publish" })).not.toBeInTheDocument();
  });

  it("explains a publish that lost a race and offers a reload", async () => {
    mockFetch({
      [ME]: signedIn({}, ADMIN),
      [`${N}/n1`]: () => json(notice({ status: "DRAFT", published_at: null, version: 1, can_manage: true })),
      [`${N}/n1/publish`]: () => envelope(409, "version_conflict", "Someone else changed this notice. Reload it and try again."),
    });
    renderRoute("/notices/n1");
    await userEvent.click(await screen.findByRole("button", { name: "Publish" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Someone else changed this notice");
    expect(screen.getByRole("button", { name: "Reload the notice" })).toBeInTheDocument();
  });

  it("withdraws only with a reason", async () => {
    const fetchMock = mockFetch({
      [ME]: signedIn({}, ADMIN),
      [`${N}/n1`]: () => json(notice({ can_manage: true })),
      [`${N}/n1/withdraw`]: () => json(notice({ status: "WITHDRAWN", can_manage: true, version: 3 })),
    });
    renderRoute("/notices/n1");
    await userEvent.click(await screen.findByRole("button", { name: "Withdraw" }));
    const dialog = screen.getByRole("dialog", { name: "Withdraw this notice?" });
    await userEvent.click(within(dialog).getByRole("button", { name: "Withdraw notice" }));
    expect(within(dialog).getByText("Give a reason.")).toBeInTheDocument();
    await userEvent.type(within(dialog).getByLabelText(/Reason/), "Posted by mistake");
    await userEvent.click(within(dialog).getByRole("button", { name: "Withdraw notice" }));
    expect(await screen.findByText("Notice withdrawn.")).toBeInTheDocument();
    expect(screen.getByText("Readers can no longer see this notice.")).toBeInTheDocument();
    expect(bodyOf(fetchMock, "POST", `${N}/n1/withdraw`)).toEqual({ reason: "Posted by mistake" });
  });
});

describe("composing", () => {
  it("keeps readers out of the editor", async () => {
    mockFetch({ [ME]: signedIn({}, MEMBER), [DEPTS]: departments, [N]: page([]) });
    const { router } = renderRoute("/notices/new");
    await waitFor(() => expect(router.state.location.pathname).toBe("/notices"));
  });

  it("checks the form, previews the Markdown and saves a college-wide draft", async () => {
    const fetchMock = mockFetch({
      [ME]: signedIn({}, ADMIN),
      [DEPTS]: departments,
      [N]: () => json(notice({ id: "n9", status: "DRAFT", published_at: null, can_manage: true, version: 1 }), 201),
      [`${N}/n9`]: () => json(notice({ id: "n9", status: "DRAFT", published_at: null, can_manage: true, version: 1 })),
    });
    const { router } = renderRoute("/notices/new");
    await userEvent.click(await screen.findByRole("button", { name: "Save draft" }));
    expect(await screen.findByText("Enter a title.")).toBeInTheDocument();
    expect(screen.getByText("Write the notice.")).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalledWith(N, expect.objectContaining({ method: "POST" }));

    await userEvent.type(screen.getByLabelText("Title"), "Exam timetable");
    await userEvent.type(screen.getByLabelText("Notice text"), "Exams start **Monday**.");
    await userEvent.click(screen.getByRole("button", { name: "Preview" }));
    await waitFor(() => expect(within(screen.getByLabelText("Preview")).getByText("Monday").tagName).toBe("STRONG"));
    await userEvent.click(screen.getByRole("button", { name: "Write" }));
    await userEvent.selectOptions(screen.getByLabelText("Category"), "EXAMINATION");
    await userEvent.click(screen.getByRole("button", { name: "Save draft" }));

    await waitFor(() => expect(router.state.location.pathname).toBe("/notices/n9"));
    expect(await screen.findByText("Draft saved.")).toBeInTheDocument();
    expect(bodyOf(fetchMock, "POST", N)).toEqual({
      title: "Exam timetable",
      body: "Exams start **Monday**.",
      category: "EXAMINATION",
      priority: "NORMAL",
      expires_at: null,
      scope: "COLLEGE",
      publish: false,
    });
  });

  it("publishes a department notice with an expiry in the college's time zone", async () => {
    const fetchMock = mockFetch({
      [ME]: signedIn({}, ADMIN),
      [DEPTS]: departments,
      [N]: () => json(notice({ id: "p", can_manage: true }), 201),
      [`${N}/p`]: () => json(notice({ id: "p", can_manage: true })),
    });
    renderRoute("/notices/new");
    await userEvent.type(await screen.findByLabelText("Title"), "Lab closed");
    await userEvent.type(screen.getByLabelText("Notice text"), "Power work.");
    await userEvent.selectOptions(screen.getByLabelText("Priority"), "URGENT");
    expect(screen.getByText(/everyone in the audience is notified/)).toBeInTheDocument();
    await userEvent.click(screen.getByLabelText("One department"));
    await userEvent.click(screen.getByRole("button", { name: "Publish" }));
    expect(await screen.findByText("Choose a department.")).toBeInTheDocument();
    await userEvent.selectOptions(screen.getByLabelText("Department"), "Computer Science");
    await userEvent.type(screen.getByLabelText("Expires (optional)"), "2026-10-30T17:30");
    await userEvent.click(screen.getByRole("button", { name: "Publish" }));
    expect(await screen.findByText("Notice published.")).toBeInTheDocument();
    expect(bodyOf(fetchMock, "POST", N)).toMatchObject({
      priority: "URGENT",
      scope: "DEPARTMENT",
      department_id: CSE.id,
      expires_at: "2026-10-30T12:00:00.000Z",
      publish: true,
    });
  });

  it("offers a department admin only their own departments", async () => {
    mockFetch({ [ME]: signedIn({}, CSE_ADMIN), [DEPTS]: departments });
    renderRoute("/notices/new");
    await screen.findByLabelText("Title");
    expect(screen.queryByLabelText("Whole college")).not.toBeInTheDocument();
    expect(screen.getByLabelText("One department")).toBeChecked();
    const select = await screen.findByLabelText("Department");
    await waitFor(() => expect(within(select).getAllByRole("option").map((o) => o.textContent)).toEqual(["Computer Science"]));
  });

  it("shows the server's field errors on the form", async () => {
    mockFetch({
      [ME]: signedIn({}, ADMIN),
      [DEPTS]: departments,
      [N]: () => envelope(422, "validation_error", "Some fields are invalid.", [{ field: "expires_at", message: "Choose a time in the future." }]),
    });
    renderRoute("/notices/new");
    await userEvent.type(await screen.findByLabelText("Title"), "x");
    await userEvent.type(screen.getByLabelText("Notice text"), "y");
    await userEvent.type(screen.getByLabelText("Expires (optional)"), "2020-01-01T10:00");
    await userEvent.click(screen.getByRole("button", { name: "Save draft" }));
    expect(await screen.findByText("Choose a time in the future.")).toBeInTheDocument();
  });

  it("edits by sending only what changed", async () => {
    const fetchMock = mockFetch({
      [ME]: signedIn({}, ADMIN),
      [`${N}/n1`]: (init) => {
        if (init?.method === "PATCH") {
          return json(notice({ title: "Exam timetable (revised)", can_manage: true, version: 3 }));
        }
        return json(notice({ can_manage: true, edited_at: null }));
      },
    });
    renderRoute("/notices/n1/edit");
    expect(await screen.findByText(/nobody is notified again/)).toBeInTheDocument();
    expect(screen.getByText("Whole college")).toBeInTheDocument();
    const title = screen.getByLabelText("Title");
    await userEvent.type(title, " (revised)");
    await userEvent.click(screen.getByRole("button", { name: "Save changes" }));
    expect(await screen.findByText("Changes saved.")).toBeInTheDocument();
    expect(bodyOf(fetchMock, "PATCH", `${N}/n1`)).toEqual({ title: "Exam timetable (revised)", version: 2 });
  });

  it("tells an editor whose version is stale to reload", async () => {
    mockFetch({
      [ME]: signedIn({}, ADMIN),
      [`${N}/n1`]: (init) => (init?.method === "PATCH" ? envelope(409, "version_conflict", "Someone else changed this notice.") : json(notice({ can_manage: true }))),
    });
    renderRoute("/notices/n1/edit");
    await userEvent.type(await screen.findByLabelText("Title"), "!");
    await userEvent.click(screen.getByRole("button", { name: "Save changes" }));
    expect(await screen.findByText("Someone else changed this notice")).toBeInTheDocument();
  });

  it("won't edit a notice the viewer can't manage", async () => {
    mockFetch({ [ME]: signedIn({}, MEMBER), [`${N}/n1`]: () => json(notice()) });
    renderRoute("/notices/n1/edit");
    expect(await screen.findByText("You can't edit this notice")).toBeInTheDocument();
    expect(screen.queryByLabelText("Title")).not.toBeInTheDocument();
  });
});

describe("department page", () => {
  const deptPage = (over: object = {}) => () => json({ ...CSE, description: "Labs in block C.", archived: false, admins: ["Ravi Sharma"], ...over });

  it("shows the department, its admins and its current notices", async () => {
    const fetchMock = mockFetch({
      [ME]: signedIn({}, MEMBER),
      [`${DEPTS}/${CSE.id}`]: deptPage(),
      [`${N}?department_id=${CSE.id}`]: page([summary({ title: "Lab schedule", scope: "DEPARTMENT", department: CSE })]),
    });
    renderRoute(`/departments/${CSE.id}`);
    expect(await screen.findByRole("heading", { level: 1, name: "Computer Science · CSE" })).toBeInTheDocument();
    expect(screen.getByText("Labs in block C.")).toBeInTheDocument();
    expect(screen.getByText("Ravi Sharma")).toBeInTheDocument();
    const notices = screen.getByRole("region", { name: "Department notices" });
    expect(await within(notices).findByText("Lab schedule")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(`${N}?department_id=${CSE.id}`, expect.anything());
    expect(screen.queryByRole("button", { name: "Edit description" })).not.toBeInTheDocument();
  });

  it("lets the department's admin edit the description", async () => {
    let description = "Labs in block C.";
    const fetchMock = mockFetch({
      [ME]: signedIn({}, CSE_ADMIN),
      [`${DEPTS}/${CSE.id}`]: (init) => {
        if (init?.method === "PATCH") description = (JSON.parse(init.body as string) as { description: string }).description;
        return deptPage({ description })();
      },
      [`${N}?department_id=${CSE.id}`]: page([]),
    });
    renderRoute(`/departments/${CSE.id}`);
    await userEvent.click(await screen.findByRole("button", { name: "Edit description" }));
    const box = screen.getByLabelText("Description");
    await userEvent.clear(box);
    await userEvent.type(box, "Labs moved to block D.");
    await userEvent.click(screen.getByRole("button", { name: "Save description" }));
    expect(await screen.findByText("Labs moved to block D.")).toBeInTheDocument();
    expect(bodyOf(fetchMock, "PATCH", `${DEPTS}/${CSE.id}`)).toEqual({ description: "Labs moved to block D." });
    expect(screen.getByText("No current notices for this department.")).toBeInTheDocument();
  });

  it("marks an archived department read-only", async () => {
    mockFetch({ [ME]: signedIn({}, ADMIN), [`${DEPTS}/${CSE.id}`]: deptPage({ archived: true }), [`${N}?department_id=${CSE.id}`]: page([]) });
    renderRoute(`/departments/${CSE.id}`);
    expect(await screen.findByText("This department is archived")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Edit description" })).not.toBeInTheDocument();
  });

  it("links a member's home to their department page", async () => {
    mockFetch({ [ME]: signedIn({}, MEMBER) });
    renderRoute("/home");
    expect(await screen.findByRole("link", { name: "Computer Science (CSE)" })).toHaveAttribute("href", `/departments/${CSE.id}`);
  });
});
