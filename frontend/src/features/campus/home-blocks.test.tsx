import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { MEMBER, NORTHFIELD_MEMBERSHIP, signedIn } from "@/test/auth";
import { envelope, json, mockFetch } from "@/test/http";
import { renderRoute } from "@/test/render";

const ME = "/api/v1/me";
const HOME = "/api/v1/campus/home";
const NOTICES = "/api/v1/campus/notices";
const TERM = { id: "t1", name: "2026-27 Odd semester", is_current: true };
const CS301 = { id: "s1", code: "CS301", name: "Compilers" };
const SECTION = { id: "sec1", name: "A" };
const noNotices = () => json({ items: [], next_cursor: null });
const base = { today: "2026-10-21", is_demo: false, classes: null, attendance: null, needs_attendance: null, my_issues: { status: "ok", open_count: 0, items: [] }, queues: null };
const cls = { starts_at: "09:00:00", ends_at: "10:00:00", room: "C-103", section: SECTION, subject: CS301 };

afterEach(() => window.history.replaceState(null, "", "/"));

describe("Home blocks", () => {
  it("shows a student today's classes, attendance and their open issues, and no queues", async () => {
    mockFetch({
      [ME]: signedIn({}, { ...MEMBER, capabilities: ["campus", "academics"] }),
      [NOTICES]: noNotices,
      [HOME]: () =>
        json({
          ...base,
          classes: { status: "ok", term: TERM, items: [cls] },
          attendance: { status: "ok", term: TERM, items: [{ section: SECTION, subject: CS301, held: 4, attended: 3, excused: 0, percentage: 75 }] },
          my_issues: { status: "ok", open_count: 4, items: [{ id: "i1", title: "Projector flickers", status: "ACKNOWLEDGED", created_at: "2026-10-20T05:00:00Z" }] },
        }),
    });
    renderRoute("/home");
    const classes = await screen.findByRole("list", { name: "Today's classes" });
    expect(classes).toHaveTextContent("09:00–10:00CS301 CompilersC-103 · Section A");
    expect(within(classes).queryByRole("link", { name: "Take attendance" })).not.toBeInTheDocument();
    expect(screen.getByRole("list", { name: "Attendance by subject" })).toHaveTextContent("CS301 Compilers75%");
    const issues = screen.getByRole("list", { name: "My open issues" });
    expect(within(issues).getByRole("link", { name: /Projector flickers/ })).toHaveAttribute("href", "/issues/i1");
    expect(screen.getByRole("link", { name: "All 4" })).toHaveAttribute("href", "/issues");
    expect(screen.queryByRole("heading", { name: "Needs your attention" })).not.toBeInTheDocument();
    // Blocks come before the latest notices (Design.md §5 screen 3).
    const headings = screen.getAllByRole("heading", { level: 2 }).map((h) => h.textContent);
    expect(headings.slice(0, 4)).toEqual(["Today's classes", "Attendance", "My open issues", "Latest notices"]);
  });

  it("gives faculty Take attendance on today's classes and on classes missing attendance", async () => {
    mockFetch({
      [ME]: signedIn({}, { ...MEMBER, membership: { ...NORTHFIELD_MEMBERSHIP, kind: "FACULTY" }, capabilities: ["campus", "teaching"] }),
      [NOTICES]: noNotices,
      [HOME]: () =>
        json({
          ...base,
          classes: { status: "ok", term: TERM, items: [cls] },
          needs_attendance: { status: "ok", items: [{ section: SECTION, subject: CS301, held_on: "2026-10-19", starts_at: "09:00:00" }] },
        }),
    });
    renderRoute("/home");
    const classes = await screen.findByRole("list", { name: "Today's classes" });
    expect(within(classes).getByRole("link", { name: "Take attendance" })).toHaveAttribute("href", "/teaching/sections/sec1/attendance/new");
    const missing = screen.getByRole("list", { name: "Attendance not taken" });
    expect(missing).toHaveTextContent("CS301 Section A · Mon, 19 Oct, 2026, 09:00");
    expect(within(missing).getByRole("link", { name: "Take attendance" })).toHaveAttribute("href", "/teaching/sections/sec1/attendance/new?date=2026-10-19");
  });

  it("lists only an admin's waiting queues, with links", async () => {
    mockFetch({
      [ME]: signedIn({}, { ...MEMBER, capabilities: ["campus", "manage_college", "review_memberships", "moderate_community", "manage_academics"] }),
      [NOTICES]: noNotices,
      [HOME]: () =>
        json({
          ...base,
          queues: {
            status: "ok",
            items: [
              { kind: "membership_requests", count: 2 },
              { kind: "content_reports", count: 0 },
              { kind: "unacknowledged_issues", count: 1 },
            ],
          },
        }),
    });
    renderRoute("/home");
    const waiting = await screen.findByRole("list", { name: "Waiting for you" });
    expect(within(waiting).getAllByRole("link").map((l) => [l.textContent, l.getAttribute("href")])).toEqual([
      ["2 requests to join→", "/manage/requests"],
      ["1 issue not yet acknowledged→", "/issues/queue"],
    ]);
  });

  it("says when nothing is waiting", async () => {
    mockFetch({ [ME]: signedIn({}, MEMBER), [NOTICES]: noNotices, [HOME]: () => json({ ...base, queues: { status: "ok", items: [{ kind: "content_reports", count: 0 }] } }) });
    renderRoute("/home");
    expect(await screen.findByText("Nothing is waiting for you.")).toBeInTheDocument();
  });

  it("keeps the other blocks when one fails, and the notices when the home fails", async () => {
    mockFetch({
      [ME]: signedIn({}, { ...MEMBER, capabilities: ["campus", "academics"] }),
      [NOTICES]: noNotices,
      [HOME]: () => json({ ...base, classes: { status: "ok", term: TERM, items: [] }, attendance: { status: "error", term: null, items: [] } }),
    });
    renderRoute("/home");
    expect(await screen.findByText("No classes today.")).toBeInTheDocument();
    expect(screen.getByText(/Couldn't load attendance just now/)).toBeInTheDocument();
    expect(screen.getByText("You have no open issues.")).toBeInTheDocument();
  });

  it("shows retry on each block when the whole home request fails", async () => {
    mockFetch({ [ME]: signedIn({}, MEMBER), [NOTICES]: noNotices, [HOME]: () => envelope(500, "internal_error", "Something went wrong on our side.") });
    renderRoute("/home");
    expect(await screen.findByText("Couldn't load your issues.")).toBeInTheDocument();
    expect(screen.getByText("No current notices.")).toBeInTheDocument();
  });
});

describe("Changing the display name", () => {
  it("saves a new name and shows it; the server's 422 stays on the field", async () => {
    let calls = 0;
    const fetchMock = mockFetch({
      [ME]: (init) => {
        if (init?.method !== "PATCH") return signedIn({}, MEMBER)();
        calls += 1;
        if (calls === 1) return envelope(422, "validation_error", "Check the highlighted fields.", [{ field: "display_name", message: "Use 1 to 60 characters for your name." }]);
        return json({ id: "u1", email: "aarav@northfield.example", display_name: "Aarav N.", email_verified: true, platform_role: null });
      },
    });
    renderRoute("/account");
    await userEvent.click(await screen.findByRole("button", { name: "Change" }));
    const field = screen.getByLabelText("Name");
    await userEvent.clear(field);
    await userEvent.type(field, "Aarav N.");
    await userEvent.click(screen.getByRole("button", { name: "Save name" }));
    expect(await screen.findByText("Use 1 to 60 characters for your name.")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Save name" }));
    expect(await screen.findByText("Saved.")).toBeInTheDocument();
    expect(screen.getByText("Aarav N.")).toBeInTheDocument();
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(ME, expect.objectContaining({ method: "PATCH", body: JSON.stringify({ display_name: "Aarav N." }) })));
  });
});
