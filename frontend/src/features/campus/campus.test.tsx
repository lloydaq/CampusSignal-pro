import { act, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { MEMBER, NORTHFIELD_MEMBERSHIP, USER, signedIn, signedOut } from "@/test/auth";
import { envelope, json, mockFetch, requestsTo, sentBody } from "@/test/http";
import { renderRoute } from "@/test/render";

const ME = "/api/v1/me";
const COLLEGES = "/api/v1/colleges";
const MY_REQUESTS = "GET /api/v1/me/membership-requests";
const REQUEST = "POST /api/v1/me/membership-requests";
const ACCEPT = "POST /api/v1/invites/accept";
const PENDING_BODY = { status: "PENDING", message: "Request sent. Northfield Institute will review it." };
const colleges = (...names: string[]) => () =>
  json({ items: names.map((name) => ({ name, slug: name.toLowerCase().split(" ")[0] })) });
const noRequests = () => json({ items: [] });

afterEach(() => {
  window.history.replaceState(null, "", "/");
  window.sessionStorage.clear();
});

describe("navigation", () => {
  it("offers members Home, Notices and Account, marking the current page", async () => {
    mockFetch({ [ME]: signedIn({}, MEMBER) });
    renderRoute("/home");
    const navs = await screen.findAllByRole("navigation", { name: "Main" });
    for (const nav of navs) {
      expect(within(nav).getAllByRole("link").map((l) => l.textContent)).toEqual(["Home", "Notices", "Account"]);
      expect(within(nav).getByRole("link", { name: "Home" })).toHaveAttribute("aria-current", "page");
    }
    expect(screen.getAllByText("Northfield Institute").length).toBeGreaterThan(0);
  });

  it("offers people without a college the join flow instead", async () => {
    mockFetch({ [ME]: signedIn(), [COLLEGES]: colleges("Northfield Institute"), [MY_REQUESTS]: noRequests });
    renderRoute("/join");
    const [nav] = await screen.findAllByRole("navigation", { name: "Main" });
    expect(within(nav!).getAllByRole("link").map((l) => l.textContent)).toEqual(["Join your college", "Account"]);
  });
});

describe("home", () => {
  it("shows the college, the membership and the demo label", async () => {
    mockFetch({ [ME]: signedIn({}, { ...MEMBER, roles: [{ role: "ISSUE_COORDINATOR", department: null }] }) });
    renderRoute("/home");
    expect(await screen.findByRole("heading", { level: 1, name: "Northfield Institute" })).toBeInTheDocument();
    const section = screen.getByRole("region", { name: "Your membership" });
    expect(within(section).getByText("Student")).toBeInTheDocument();
    expect(within(section).getByText("Computer Science (CSE)")).toBeInTheDocument();
    expect(within(section).getByText("Issue coordinator")).toBeInTheDocument();
    expect(screen.getByText(/Demo data/)).toBeInTheDocument();
  });

  it("sends people without campus access to the join flow", async () => {
    mockFetch({ [ME]: signedIn(), [COLLEGES]: colleges("Northfield Institute"), [MY_REQUESTS]: noRequests });
    const { router } = renderRoute("/home");
    await waitFor(() => expect(router.state.location.pathname).toBe("/join"));
  });
});

describe("joining a college", () => {
  async function fill(college: string, roll: string) {
    await userEvent.click(await screen.findByRole("radio", { name: college }));
    await userEvent.type(screen.getByLabelText("Roll number"), roll);
    await userEvent.click(screen.getByRole("button", { name: "Send request" }));
  }

  it("joins at once on a roster match and goes home", async () => {
    let joined = false;
    const fetchMock = mockFetch({
      [ME]: () => (joined ? signedIn({}, MEMBER)() : signedIn()()),
      [COLLEGES]: colleges("Northfield Institute", "Riverside College"),
      [MY_REQUESTS]: noRequests,
      [REQUEST]: () => {
        joined = true;
        return json({ status: "ACTIVE", message: "You've joined Northfield Institute.", membership: NORTHFIELD_MEMBERSHIP }, 201);
      },
    });
    const { router } = renderRoute("/join");
    await fill("Northfield Institute", " n-100 ");
    await waitFor(() => expect(router.state.location.pathname).toBe("/home"));
    const post = fetchMock.mock.calls.find(([url, init]) => url === "/api/v1/me/membership-requests" && init?.method === "POST");
    expect(JSON.parse(post?.[1]?.body as string)).toEqual({ college_slug: "northfield", roll_number: "N-100" });
  });

  it("shows the waiting screen naming the college for every other outcome", async () => {
    let requested = false;
    mockFetch({
      [ME]: () => (requested ? signedIn({}, { membership: { ...NORTHFIELD_MEMBERSHIP, status: "PENDING", department: null } })() : signedIn()()),
      [COLLEGES]: colleges("Northfield Institute"),
      [MY_REQUESTS]: noRequests,
      [REQUEST]: () => {
        requested = true;
        return json(PENDING_BODY, 202);
      },
    });
    renderRoute("/join");
    await fill("Northfield Institute", "N-999");
    expect(await screen.findByRole("heading", { level: 1, name: "Waiting for approval by Northfield Institute" })).toBeInTheDocument();
  });

  it("checks the form before sending", async () => {
    const fetchMock = mockFetch({ [ME]: signedIn(), [COLLEGES]: colleges("Northfield Institute"), [MY_REQUESTS]: noRequests });
    renderRoute("/join");
    await userEvent.click(await screen.findByRole("button", { name: "Send request" }));
    expect(await screen.findByText("Choose your college.")).toBeInTheDocument();
    expect(screen.getByText("Enter your roll number as it appears on your ID card.")).toBeInTheDocument();
    expect(requestsTo(fetchMock, "/api/v1/me/membership-requests").filter((r) => r.method === "POST")).toHaveLength(0);
  });

  it("explains conflicts and the daily limit", async () => {
    let calls = 0;
    mockFetch({
      [ME]: signedIn(),
      [COLLEGES]: colleges("Northfield Institute"),
      [MY_REQUESTS]: noRequests,
      [REQUEST]: () =>
        ++calls === 1
          ? envelope(409, "request_pending", "You already have a request waiting for review.")
          : envelope(429, "rate_limited", "Too many requests.", null, "r", { "Retry-After": "7200" }),
    });
    renderRoute("/join");
    await fill("Northfield Institute", "N-1");
    expect(await screen.findByRole("alert")).toHaveTextContent("You already have a request waiting for review.");
    await userEvent.click(screen.getByRole("button", { name: "Send request" }));
    expect(await screen.findByText("You've made several requests today. Try again in 120 minutes.")).toBeInTheDocument();
  });

  it("shows the reason for the last rejection, never anything about the roster", async () => {
    mockFetch({
      [ME]: signedIn(),
      [COLLEGES]: colleges("Northfield Institute"),
      [MY_REQUESTS]: () =>
        json({
          items: [
            {
              id: "r1",
              college: { name: "Northfield Institute", slug: "northfield" },
              status: "REJECTED",
              decision_reason: "Use your college email.",
              created_at: "2026-10-20T10:00:00Z",
            },
          ],
        }),
    });
    renderRoute("/join");
    const callout = await screen.findByText("Northfield Institute turned down your last request");
    expect(callout.parentElement).toHaveTextContent("Use your college email.");
    expect(screen.getByRole("button", { name: "Send request" })).toBeInTheDocument();
  });

  it("blocks unverified accounts with a way to verify", async () => {
    mockFetch({ [ME]: signedIn({ email_verified: false }) });
    renderRoute("/join");
    expect(await screen.findByRole("heading", { level: 1, name: "Verify your email first" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Send a new link" })).toBeInTheDocument();
  });

  it("tells platform admins they can't join", async () => {
    mockFetch({ [ME]: signedIn({ platform_role: "PLATFORM_ADMIN" }, { capabilities: ["platform"] }) });
    renderRoute("/join");
    expect(await screen.findByRole("heading", { level: 1, name: "Platform admins don't join colleges" })).toBeInTheDocument();
  });

  it("searches when there are many colleges", async () => {
    mockFetch({
      [ME]: signedIn(),
      [COLLEGES]: colleges("Alpha College", "Beta College", "Gamma College", "Delta College", "Epsilon College", "Zeta College", "Eta College", "Northfield Institute"),
      [MY_REQUESTS]: noRequests,
    });
    renderRoute("/join");
    await userEvent.type(await screen.findByLabelText("Search colleges"), "north");
    expect(screen.getAllByRole("radio").map((r) => r.getAttribute("value"))).toEqual(["northfield"]);
  });

  it("offers a retry when the college list can't load", async () => {
    let calls = 0;
    mockFetch({
      [ME]: signedIn(),
      [MY_REQUESTS]: noRequests,
      [COLLEGES]: () => (++calls === 1 ? envelope(500, "internal_error", "Something went wrong on our side.") : colleges("Northfield Institute")()),
    });
    renderRoute("/join");
    await userEvent.click(await screen.findByRole("button", { name: "Try again" }));
    expect(await screen.findByRole("radio", { name: "Northfield Institute" })).toBeInTheDocument();
  });
});

describe("accepting an invitation", () => {
  function openInvite(token = "invite-token") {
    window.history.replaceState(null, "", `/invites/accept#token=${token}`);
  }

  it("asks a signed-out visitor to sign in, then accepts after they come back", async () => {
    openInvite();
    let session = false;
    let accepted = false;
    const fetchMock = mockFetch({
      [ME]: () => (accepted ? signedIn({}, { ...MEMBER, membership: { ...NORTHFIELD_MEMBERSHIP, kind: "FACULTY" } })() : session ? signedIn()() : signedOut()),
      "POST /api/v1/auth/login": () => {
        session = true;
        return json({ user: USER, csrf_token: "t" });
      },
      [ACCEPT]: () => {
        accepted = true;
        return json({ membership: NORTHFIELD_MEMBERSHIP });
      },
    });
    const { router } = renderRoute("/invites/accept");
    expect(await screen.findByRole("heading", { level: 1, name: "You're invited to join your college" })).toBeInTheDocument();
    expect(window.location.hash).toBe("");

    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
    expect(router.state.location.pathname + router.state.location.search).toBe("/sign-in?next=%2Finvites%2Faccept");
    await userEvent.type(screen.getByLabelText("Email"), USER.email);
    await userEvent.type(screen.getByLabelText("Password"), "tidal-quartz-lantern");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));

    await userEvent.click(await screen.findByRole("button", { name: "Accept invitation" }));
    await waitFor(() => expect(router.state.location.pathname).toBe("/home"));
    expect(sentBody(fetchMock, "/api/v1/invites/accept")).toEqual({ token: "invite-token" });
    expect(window.sessionStorage.length).toBe(0); // the token is gone once used
  });

  it("explains a mismatched email and offers to sign out", async () => {
    openInvite();
    mockFetch({
      [ME]: signedIn(),
      [ACCEPT]: () => envelope(403, "invite_email_mismatch", "This invitation is for a different email address."),
      "POST /api/v1/auth/logout": () => new Response(null, { status: 204 }),
    });
    renderRoute("/invites/accept");
    expect(await screen.findByText(USER.email)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Accept invitation" }));
    expect(await screen.findByText("This invitation is for a different email address")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Accept invitation" })).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Sign out" }));
    expect(await screen.findByRole("heading", { level: 1, name: "You're invited to join your college" })).toBeInTheDocument();
  });

  it("keeps the invitee signed in when signing out fails", async () => {
    openInvite();
    mockFetch({
      [ME]: signedIn(),
      [ACCEPT]: () => envelope(403, "invite_email_mismatch", "This invitation is for a different email address."),
      "POST /api/v1/auth/logout": () => envelope(500, "internal_error", "Something went wrong on our side."),
    });
    renderRoute("/invites/accept");
    await userEvent.click(await screen.findByRole("button", { name: "Accept invitation" }));
    await userEvent.click(await screen.findByRole("button", { name: "Sign out" }));
    expect(await screen.findByText(/Couldn't sign out\. You're still signed in on this browser\./)).toBeInTheDocument();
    expect(screen.queryByRole("heading", { level: 1, name: "You're invited to join your college" })).not.toBeInTheDocument();
  });

  it.each([
    ["token_used", "This invitation was already used"],
    ["token_expired", "This invitation has expired"],
  ])("explains a %s link and forgets the token", async (code, title) => {
    openInvite();
    mockFetch({ [ME]: signedIn(), [ACCEPT]: () => envelope(400, code, "x") });
    renderRoute("/invites/accept");
    await userEvent.click(await screen.findByRole("button", { name: "Accept invitation" }));
    expect(await screen.findByRole("heading", { level: 1, name: title })).toBeInTheDocument();
    expect(window.sessionStorage.length).toBe(0);
  });

  it("explains a link without a token", async () => {
    mockFetch({ [ME]: signedIn() });
    renderRoute("/invites/accept");
    expect(await screen.findByRole("heading", { level: 1, name: "This invitation isn't valid" })).toBeInTheDocument();
  });

  it("refuses platform admins with the reason", async () => {
    openInvite();
    mockFetch({
      [ME]: signedIn({ platform_role: "PLATFORM_ADMIN" }, { capabilities: ["platform"] }),
      [ACCEPT]: () => envelope(403, "platform_admin_cannot_join", "x"),
    });
    renderRoute("/invites/accept");
    await act(async () => {
      await userEvent.click(await screen.findByRole("button", { name: "Accept invitation" }));
    });
    expect(await screen.findByText(/Platform admin accounts can't join a college/)).toBeInTheDocument();
  });
});
