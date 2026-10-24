import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import type { Me } from "@/features/auth/api";
import { MEMBER, signedIn } from "@/test/auth";
import { envelope, json, mockFetch } from "@/test/http";
import { renderRoute } from "@/test/render";

const ME = "/api/v1/me";
const P = "/api/v1/platform";

const PLATFORM: Partial<Me> = { capabilities: ["platform"] };
const OPS = { platform_role: "PLATFORM_ADMIN" };

const NORTHFIELD = {
  id: "c1",
  name: "Northfield Institute",
  slug: "northfield",
  timezone: "Asia/Kolkata",
  status: "ONBOARDING",
  email_domains: ["northfield.example"],
  is_demo: true,
  created_at: "2026-10-20T04:30:00Z",
  active_member_count: 0,
};

const page = <T,>(items: T[], next_cursor: string | null = null) => json({ items, next_cursor });

function bodyOf(fetchMock: ReturnType<typeof mockFetch>, method: string, path: string, index = 0): unknown {
  const call = fetchMock.mock.calls.filter(([input, init]) => input === path && (init?.method ?? "GET") === method)[index];
  const body = call?.[1]?.body;
  return typeof body === "string" ? (JSON.parse(body) as unknown) : undefined;
}

afterEach(() => window.history.replaceState(null, "", "/"));

describe("platform access", () => {
  it("lands platform admins on the platform and offers Platform and Account", async () => {
    mockFetch({ [ME]: signedIn(OPS, PLATFORM), [`${P}/colleges`]: () => page([]) });
    const { router } = renderRoute("/");
    await waitFor(() => expect(router.state.location.pathname).toBe("/platform/colleges"));
    const [nav] = await screen.findAllByRole("navigation", { name: "Main" });
    expect(within(nav!).getAllByRole("link").map((l) => l.textContent)).toEqual(["Platform", "Account"]);
    const tabs = screen.getByRole("navigation", { name: "Platform" });
    expect(within(tabs).getAllByRole("link").map((l) => l.textContent)).toEqual(["Colleges", "Users", "Audit log"]);
  });

  it("sends members who open /platform back home", async () => {
    mockFetch({ [ME]: signedIn({}, MEMBER) });
    const { router } = renderRoute("/platform/users");
    await waitFor(() => expect(router.state.location.pathname).toBe("/home"));
  });
});

describe("colleges", () => {
  it("lists colleges with their status and member counts", async () => {
    mockFetch({
      [ME]: signedIn(OPS, PLATFORM),
      [`${P}/colleges`]: () => page([NORTHFIELD, { ...NORTHFIELD, id: "c2", name: "Riverside College", slug: "riverside", status: "ACTIVE", active_member_count: 42, is_demo: false }]),
    });
    renderRoute("/platform/colleges");
    const table = await screen.findByRole("table", { name: "Colleges" });
    expect(within(table).getByRole("link", { name: "Northfield Institute" })).toHaveAttribute("href", "/platform/colleges/c1");
    expect(table).toHaveTextContent("Onboarding");
    expect(table).toHaveTextContent("42");
    expect(table).toHaveTextContent("Demo data");
    expect(screen.getByText("Showing 2")).toBeInTheDocument();
  });

  it("creates a college and points to inviting its first admin", async () => {
    let created = false;
    const fetchMock = mockFetch({
      [ME]: signedIn(OPS, PLATFORM),
      [`${P}/colleges`]: (init) => {
        if (init?.method === "POST") {
          created = true;
          return json(NORTHFIELD, 201);
        }
        return page(created ? [NORTHFIELD] : []);
      },
    });
    renderRoute("/platform/colleges");
    expect(await screen.findByText("No colleges yet.")).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText("Name"), "Northfield Institute");
    await userEvent.type(screen.getByLabelText("Slug"), "Northfield");
    await userEvent.type(screen.getByLabelText(/Email domains/), "Northfield.example, nf.example");
    await userEvent.click(screen.getByLabelText(/demo college/));
    await userEvent.click(screen.getByRole("button", { name: "Create college" }));
    expect(await screen.findByRole("link", { name: "Invite its first admin" })).toHaveAttribute("href", "/platform/colleges/c1");
    expect(bodyOf(fetchMock, "POST", `${P}/colleges`)).toEqual({
      name: "Northfield Institute",
      slug: "northfield",
      timezone: "Asia/Kolkata",
      email_domains: ["northfield.example", "nf.example"],
      is_demo: true,
    });
  });

  it("shows a taken slug on the form and checks the slug before sending", async () => {
    const fetchMock = mockFetch({
      [ME]: signedIn(OPS, PLATFORM),
      [`${P}/colleges`]: (init) => (init?.method === "POST" ? envelope(409, "slug_taken", "A college with this slug already exists.") : page([])),
    });
    renderRoute("/platform/colleges");
    await userEvent.type(await screen.findByLabelText("Name"), "Northfield");
    await userEvent.type(screen.getByLabelText("Slug"), "-bad-");
    await userEvent.click(screen.getByRole("button", { name: "Create college" }));
    expect(await screen.findByText(/lower-case letters, digits and hyphens \(not at the ends\)/)).toBeInTheDocument();
    expect(bodyOf(fetchMock, "POST", `${P}/colleges`)).toBeUndefined();
    await userEvent.clear(screen.getByLabelText("Slug"));
    await userEvent.type(screen.getByLabelText("Slug"), "northfield");
    await userEvent.click(screen.getByRole("button", { name: "Create college" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("already exists");
  });
});

describe("college detail", () => {
  const detail = (extra: Record<string, unknown> = {}) => json({ ...NORTHFIELD, admin_invites: [], ...extra });

  it("activates an onboarding college after confirming", async () => {
    let status = "ONBOARDING";
    const fetchMock = mockFetch({
      [ME]: signedIn(OPS, PLATFORM),
      [`${P}/colleges/c1`]: (init) => {
        if (init?.method === "PATCH") status = "ACTIVE";
        return detail({ status });
      },
      [`${P}/colleges`]: () => page([]),
    });
    renderRoute("/platform/colleges/c1");
    await userEvent.click(await screen.findByRole("button", { name: "Activate" }));
    const dialog = screen.getByRole("dialog", { name: "Activate Northfield Institute?" });
    expect(within(dialog).queryByLabelText(/Reason/)).not.toBeInTheDocument();
    await userEvent.click(within(dialog).getByRole("button", { name: "Activate" }));
    expect(await screen.findByRole("button", { name: "Suspend" })).toBeInTheDocument();
    expect(bodyOf(fetchMock, "PATCH", `${P}/colleges/c1`)).toEqual({ status: "ACTIVE" });
  });

  it("suspends only with a reason", async () => {
    const fetchMock = mockFetch({
      [ME]: signedIn(OPS, PLATFORM),
      [`${P}/colleges/c1`]: (init) => (init?.method === "PATCH" ? detail({ status: "SUSPENDED" }) : detail({ status: "ACTIVE" })),
      [`${P}/colleges`]: () => page([]),
    });
    renderRoute("/platform/colleges/c1");
    await userEvent.click(await screen.findByRole("button", { name: "Suspend" }));
    const dialog = screen.getByRole("dialog", { name: "Suspend Northfield Institute?" });
    await userEvent.click(within(dialog).getByRole("button", { name: "Suspend" }));
    expect(within(dialog).getByText("Give a reason.")).toBeInTheDocument();
    await userEvent.type(within(dialog).getByLabelText(/Reason/), "Fees unpaid");
    await userEvent.click(within(dialog).getByRole("button", { name: "Suspend" }));
    expect(await screen.findByRole("button", { name: "Reactivate" })).toBeInTheDocument();
    expect(bodyOf(fetchMock, "PATCH", `${P}/colleges/c1`)).toEqual({ status: "SUSPENDED", reason: "Fees unpaid" });
  });

  it("invites the first admin and lists the invitation", async () => {
    let invites: unknown[] = [];
    const fetchMock = mockFetch({
      [ME]: signedIn(OPS, PLATFORM),
      [`${P}/colleges/c1`]: () => detail({ admin_invites: invites }),
      [`${P}/colleges/c1/admin-invites`]: () => {
        const invite = { id: "i1", email: "priya@northfield.example", kind: "STAFF", state: "PENDING", created_at: "2026-10-24T05:00:00Z", expires_at: "2026-10-31T05:00:00Z" };
        invites = [invite];
        return json(invite, 201);
      },
    });
    renderRoute("/platform/colleges/c1");
    await userEvent.type(await screen.findByLabelText("Email"), "Priya@Northfield.example");
    await userEvent.click(screen.getByRole("button", { name: "Invite as college admin" }));
    expect(await screen.findByText(/Invitation sent to priya@northfield.example/)).toBeInTheDocument();
    expect(await screen.findByRole("table", { name: "College admin invitations" })).toHaveTextContent("Waiting");
    expect(bodyOf(fetchMock, "POST", `${P}/colleges/c1/admin-invites`)).toEqual({ email: "priya@northfield.example", kind: "STAFF" });
  });

  it("asks for a reason when the college already has an admin", async () => {
    mockFetch({
      [ME]: signedIn(OPS, PLATFORM),
      [`${P}/colleges/c1`]: () => detail(),
      [`${P}/colleges/c1/admin-invites`]: () =>
        envelope(422, "validation_error", "Some fields are invalid.", [
          { field: "reason", message: "This college already has a college admin. Give a reason for inviting another." },
        ]),
    });
    renderRoute("/platform/colleges/c1");
    await userEvent.type(await screen.findByLabelText("Email"), "second@northfield.example");
    await userEvent.click(screen.getByRole("button", { name: "Invite as college admin" }));
    expect(await screen.findByText(/already has a college admin/)).toBeInTheDocument();
  });

  it("says so for a college that doesn't exist", async () => {
    mockFetch({ [ME]: signedIn(OPS, PLATFORM), [`${P}/colleges/nope`]: () => envelope(404, "not_found", "Not found.") });
    renderRoute("/platform/colleges/nope");
    expect(await screen.findByText("That college doesn't exist.")).toBeInTheDocument();
  });
});

describe("users", () => {
  const user = { id: "u1", email: "kabir@northfield.example", display_name: "Kabir Shah", status: "ACTIVE", platform_role: null };

  it("finds an account by exact email, suspends it with a reason and reinstates it", async () => {
    let status = "ACTIVE";
    const fetchMock = mockFetch({
      [ME]: signedIn(OPS, PLATFORM),
      [`${P}/users?email=kabir%40northfield.example`]: () => json({ items: [{ ...user, status }] }),
      [`POST ${P}/users/u1/suspend`]: () => {
        status = "SUSPENDED";
        return json({ ...user, status });
      },
      [`POST ${P}/users/u1/unsuspend`]: () => {
        status = "ACTIVE";
        return json({ ...user, status });
      },
    });
    renderRoute("/platform/users");
    await userEvent.type(await screen.findByLabelText("Find an account by email"), "kabir@northfield.example");
    await userEvent.click(screen.getByRole("button", { name: "Find" }));
    expect(await screen.findByText("Kabir Shah")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Suspend account" }));
    const dialog = screen.getByRole("dialog", { name: "Suspend Kabir Shah?" });
    await userEvent.click(within(dialog).getByRole("button", { name: "Suspend account" }));
    expect(within(dialog).getByText("Give a reason.")).toBeInTheDocument();
    await userEvent.type(within(dialog).getByLabelText(/Reason/), "Report of misuse");
    await userEvent.click(within(dialog).getByRole("button", { name: "Suspend account" }));
    await userEvent.click(await screen.findByRole("button", { name: "Reinstate account" }));
    expect(await screen.findByRole("button", { name: "Suspend account" })).toBeInTheDocument();
    expect(bodyOf(fetchMock, "POST", `${P}/users/u1/suspend`)).toEqual({ reason: "Report of misuse" });
  });

  it("says when nobody has that email", async () => {
    mockFetch({ [ME]: signedIn(OPS, PLATFORM), [`${P}/users?email=nobody%40x.example`]: () => json({ items: [] }) });
    renderRoute("/platform/users");
    await userEvent.type(await screen.findByLabelText("Find an account by email"), "nobody@x.example");
    await userEvent.click(screen.getByRole("button", { name: "Find" }));
    expect(await screen.findByText("No account has this email address.")).toBeInTheDocument();
  });

  it("explains a refusal to suspend yourself", async () => {
    mockFetch({
      [ME]: signedIn(OPS, PLATFORM),
      [`${P}/users?email=ops%40campussignal.example`]: () => json({ items: [{ ...user, email: "ops@campussignal.example", platform_role: "PLATFORM_ADMIN" }] }),
      [`POST ${P}/users/u1/suspend`]: () => envelope(409, "cannot_suspend_self", "You can't suspend your own account."),
    });
    renderRoute("/platform/users");
    await userEvent.type(await screen.findByLabelText("Find an account by email"), "ops@campussignal.example");
    await userEvent.click(screen.getByRole("button", { name: "Find" }));
    expect(await screen.findByText("Platform admin")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Suspend account" }));
    const dialog = screen.getByRole("dialog");
    await userEvent.type(within(dialog).getByLabelText(/Reason/), "test");
    await userEvent.click(within(dialog).getByRole("button", { name: "Suspend account" }));
    expect(await within(dialog).findByRole("alert")).toHaveTextContent("can't suspend your own account");
  });
});

describe("audit log", () => {
  it("names platform actions in words", async () => {
    mockFetch({
      [ME]: signedIn(OPS, PLATFORM),
      [`${P}/audit-log`]: () =>
        page([
          { id: "a1", action: "platform.college_status_changed", actor_user_id: "u9", college_id: "c1", target_type: "college", target_id: "c1", reason: "Fees unpaid", metadata: {}, created_at: "2026-10-22T09:00:00Z" },
        ]),
    });
    renderRoute("/platform/audit");
    const table = await screen.findByRole("table", { name: "Platform audit log" });
    expect(table).toHaveTextContent("College status changed");
    expect(table).toHaveTextContent("Fees unpaid");
    expect(table).toHaveTextContent("22 Oct 2026, 9:00");
  });
});
