import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { USER, signedIn, signedOut } from "@/test/auth";
import { envelope, json, mockFetch, noContent, requestsTo, sentBody } from "@/test/http";
import { renderRoute } from "@/test/render";

const ME = "/api/v1/me";
const PASSWORD = "tidal-quartz-lantern";

const heading = () => screen.getByRole("heading", { level: 1 });

afterEach(() => {
  window.history.replaceState(null, "", "/");
});

describe("routing by session", () => {
  it("sends signed-out visitors from / to sign in", async () => {
    mockFetch({ [ME]: signedOut });
    const { router } = renderRoute("/");
    expect(await screen.findByRole("heading", { level: 1, name: "Sign in" })).toBeInTheDocument();
    expect(router.state.location.pathname).toBe("/sign-in");
    expect(document.title).toBe("Sign in · CampusSignal");
  });

  it("sends signed-in visitors from / and /sign-in to their account", async () => {
    mockFetch({ [ME]: signedIn() });
    const { router } = renderRoute("/sign-in?next=%2Faccount");
    expect(await screen.findByRole("heading", { level: 1, name: "Your account" })).toBeInTheDocument();
    expect(router.state.location.pathname).toBe("/account");
  });

  it("asks for sign-in with a return path when /account is opened signed out", async () => {
    mockFetch({ [ME]: signedOut });
    const { router } = renderRoute("/account");
    expect(await screen.findByText("Sign in to continue.")).toBeInTheDocument();
    expect(router.state.location.pathname + router.state.location.search).toBe("/sign-in?next=%2Faccount");
  });

  it("shows an error with retry when the session can't be checked", async () => {
    let calls = 0;
    mockFetch({ [ME]: () => (++calls === 1 ? envelope(500, "internal_error", "Something went wrong on our side.", null, "req-500") : signedIn()()) });
    renderRoute("/account");
    expect(await screen.findByRole("heading", { level: 1, name: "Couldn't load your account" })).toBeInTheDocument();
    expect(screen.getByText("Request ID req-500")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByRole("heading", { level: 1, name: "Your account" })).toBeInTheDocument();
  });
});

describe("sign in", () => {
  it("validates on submit without calling the server and focuses the first problem", async () => {
    const fetchMock = mockFetch({ [ME]: signedOut });
    renderRoute("/sign-in");
    await userEvent.click(await screen.findByRole("button", { name: "Sign in" }));
    expect(await screen.findByText("Enter your email address.")).toBeInTheDocument();
    expect(screen.getByText("Enter your password.")).toBeInTheDocument();
    expect(screen.getByLabelText("Email")).toHaveFocus();
    expect(screen.getByLabelText("Email")).toHaveAttribute("aria-invalid", "true");
    expect(screen.getByLabelText("Email")).toHaveAccessibleDescription("Enter your email address.");
    expect(requestsTo(fetchMock, "/api/v1/auth/login")).toHaveLength(0);
  });

  it("signs in, sends the normalised email and continues to the return path", async () => {
    const fetchMock = mockFetch({ [ME]: signedOut, "POST /api/v1/auth/login": () => json({ user: USER, csrf_token: "t" }) });
    const { router } = renderRoute("/sign-in?next=%2Faccount%3Ftab%3Dsecurity");
    await userEvent.type(await screen.findByLabelText("Email"), " Aarav@Northfield.Example ");
    await userEvent.type(screen.getByLabelText("Password"), PASSWORD);
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
    await waitFor(() => expect(router.state.location.pathname).toBe("/account"));
    expect(router.state.location.search).toBe("?tab=security");
    expect(sentBody(fetchMock, "/api/v1/auth/login")).toEqual({ email: "aarav@northfield.example", password: PASSWORD });
  });

  it("ignores an off-site return path", async () => {
    mockFetch({ [ME]: signedOut, "POST /api/v1/auth/login": () => json({ user: USER, csrf_token: "t" }) });
    const { router } = renderRoute("/sign-in?next=https%3A%2F%2Fevil.example%2F");
    await userEvent.type(await screen.findByLabelText("Email"), USER.email);
    await userEvent.type(screen.getByLabelText("Password"), PASSWORD);
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
    await waitFor(() => expect(router.state.location.pathname).toBe("/account"));
  });

  it("shows the one generic failure message and clears the password", async () => {
    mockFetch({
      [ME]: signedOut,
      "POST /api/v1/auth/login": () => envelope(401, "invalid_credentials", "Email or password is incorrect."),
    });
    renderRoute("/sign-in");
    await userEvent.type(await screen.findByLabelText("Email"), USER.email);
    await userEvent.type(screen.getByLabelText("Password"), "wrong-password-123");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Email or password is incorrect.");
    expect(screen.getByLabelText("Password")).toHaveValue("");
  });

  it("says how long to wait when sign-in is rate limited", async () => {
    mockFetch({
      [ME]: signedOut,
      "POST /api/v1/auth/login": () => envelope(429, "rate_limited", "Too many requests. Try again later.", null, "r", { "Retry-After": "170" }),
    });
    renderRoute("/sign-in");
    await userEvent.type(await screen.findByLabelText("Email"), USER.email);
    await userEvent.type(screen.getByLabelText("Password"), PASSWORD);
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Too many sign-in attempts. Try again in 3 minutes.");
  });

  it("keeps the button disabled with a pending label while signing in", async () => {
    mockFetch({ [ME]: signedOut, "POST /api/v1/auth/login": () => new Promise<Response>(() => undefined) });
    renderRoute("/sign-in");
    await userEvent.type(await screen.findByLabelText("Email"), USER.email);
    await userEvent.type(screen.getByLabelText("Password"), PASSWORD);
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByRole("button", { name: "Signing in…" })).toBeDisabled();
  });
});

describe("register", () => {
  it("shows the password rules up front and checks length before sending", async () => {
    const fetchMock = mockFetch({ [ME]: signedOut });
    renderRoute("/register");
    const password = await screen.findByLabelText("Password");
    expect(password).toHaveAccessibleDescription("At least 10 characters. Avoid common passwords and your email address.");
    await userEvent.type(screen.getByLabelText("Your name"), "Aarav");
    await userEvent.type(screen.getByLabelText("Email"), USER.email);
    await userEvent.type(password, "short");
    await userEvent.click(screen.getByRole("button", { name: "Create account" }));
    expect(await screen.findByText("Use at least 10 characters.")).toBeInTheDocument();
    expect(requestsTo(fetchMock, "/api/v1/auth/register")).toHaveLength(0);
  });

  it("puts the server's password verdict on the password field (US-01: password1234)", async () => {
    mockFetch({
      [ME]: signedOut,
      "POST /api/v1/auth/register": () =>
        envelope(422, "validation_error", "Some fields are invalid.", [
          { field: "password", message: "This password is too common. Choose one that's harder to guess." },
        ]),
    });
    renderRoute("/register");
    await userEvent.type(await screen.findByLabelText("Your name"), "Aarav");
    await userEvent.type(screen.getByLabelText("Email"), USER.email);
    await userEvent.type(screen.getByLabelText("Password"), "password1234");
    await userEvent.click(screen.getByRole("button", { name: "Create account" }));
    expect(await screen.findByText("This password is too common. Choose one that's harder to guess.")).toBeInTheDocument();
    expect(screen.getByLabelText("Password")).toHaveAttribute("aria-invalid", "true");
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("ends on the same check-your-email screen whatever the server knows", async () => {
    const fetchMock = mockFetch({ [ME]: signedOut, "POST /api/v1/auth/register": () => json({ message: "Check your email to finish setting up your account." }, 201) });
    const { router } = renderRoute("/register");
    await userEvent.type(await screen.findByLabelText("Your name"), "  Aarav   Nair ");
    await userEvent.type(screen.getByLabelText("Email"), USER.email);
    await userEvent.type(screen.getByLabelText("Password"), PASSWORD);
    await userEvent.click(screen.getByRole("button", { name: "Create account" }));
    expect(await screen.findByRole("heading", { level: 1, name: "Check your email" })).toBeInTheDocument();
    expect(router.state.location.pathname).toBe("/check-email");
    expect(screen.getByRole("link", { name: "sign in to send a new link" })).toHaveAttribute("href", "/sign-in?next=%2Faccount");
    expect(sentBody(fetchMock, "/api/v1/auth/register")).toEqual({ display_name: "Aarav Nair", email: USER.email, password: PASSWORD });
  });
});

describe("verify email", () => {
  function openLink(hash: string) {
    window.history.replaceState(null, "", `/verify-email${hash}`);
  }

  it("verifies once from the link fragment and removes the token from the address bar", async () => {
    openLink("#token=abc_DEF-123");
    const fetchMock = mockFetch({ [ME]: signedOut, "POST /api/v1/auth/verify-email": () => json({ message: "Your email is verified." }) });
    renderRoute("/verify-email");
    expect(await screen.findByRole("heading", { level: 1, name: "Your email is verified" })).toBeInTheDocument();
    expect(window.location.hash).toBe("");
    expect(requestsTo(fetchMock, "/api/v1/auth/verify-email")).toHaveLength(1);
    expect(sentBody(fetchMock, "/api/v1/auth/verify-email")).toEqual({ token: "abc_DEF-123" });
    expect(screen.getByRole("link", { name: "Sign in" })).toBeInTheDocument();
  });

  it("doesn't let a /me answer that predates the verification win", async () => {
    openLink("#token=fresh");
    let verified = false;
    let releaseFirst: () => void = () => undefined;
    let meCalls = 0;
    mockFetch({
      [ME]: () => {
        meCalls += 1;
        if (meCalls > 1) return signedIn({ email_verified: verified })();
        // The first /me is answered (as unverified) only after the verification succeeded.
        return new Promise<Response>((resolve) => {
          releaseFirst = () => resolve(signedIn({ email_verified: false })());
        });
      },
      "POST /api/v1/auth/verify-email": () => {
        verified = true;
        setTimeout(() => releaseFirst(), 0);
        return json({ message: "Your email is verified." });
      },
    });
    renderRoute("/verify-email");
    await userEvent.click(await screen.findByRole("link", { name: "Go to your account" }));
    const profile = await screen.findByRole("region", { name: "Profile" });
    expect(within(profile).getByText("Verified")).toBeInTheDocument();
  });

  it("says a used link was already used (US-01)", async () => {
    openLink("#token=used");
    mockFetch({ [ME]: signedOut, "POST /api/v1/auth/verify-email": () => envelope(400, "token_used", "This link was already used.") });
    renderRoute("/verify-email");
    expect(await screen.findByRole("heading", { level: 1, name: "This link was already used" })).toBeInTheDocument();
  });

  it("offers sign-in for a new link when an expired link is opened signed out", async () => {
    openLink("#token=old");
    mockFetch({ [ME]: signedOut, "POST /api/v1/auth/verify-email": () => envelope(400, "token_expired", "This link has expired.") });
    renderRoute("/verify-email");
    expect(await screen.findByRole("heading", { level: 1, name: "This link has expired" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Sign in to get a new link" })).toHaveAttribute("href", "/sign-in?next=%2Faccount");
  });

  it("offers a resend button when an expired link is opened signed in (US-01)", async () => {
    openLink("#token=old");
    const fetchMock = mockFetch({
      [ME]: signedIn({ email_verified: false }),
      "POST /api/v1/auth/verify-email": () => envelope(400, "token_expired", "This link has expired."),
      "POST /api/v1/auth/resend-verification": () => json({ message: "We've sent a new verification link." }, 202),
    });
    renderRoute("/verify-email");
    await userEvent.click(await screen.findByRole("button", { name: "Send a new link" }));
    expect(await screen.findByText("We've sent a new verification link. It works for 24 hours.")).toBeInTheDocument();
    expect(requestsTo(fetchMock, "/api/v1/auth/resend-verification")).toHaveLength(1);
  });

  it("explains a link without a token without calling the server", async () => {
    openLink("");
    const fetchMock = mockFetch({ [ME]: signedOut });
    renderRoute("/verify-email");
    expect(await screen.findByRole("heading", { level: 1, name: "This link isn't valid" })).toBeInTheDocument();
    expect(requestsTo(fetchMock, "/api/v1/auth/verify-email")).toHaveLength(0);
  });
});

describe("password reset", () => {
  it("sends the same confirmation whether or not the account exists", async () => {
    mockFetch({ "POST /api/v1/auth/password-reset/request": () => json({ message: "If an account exists for that email, we've sent a reset link." }, 202) });
    renderRoute("/forgot-password");
    await userEvent.type(screen.getByLabelText("Email"), USER.email);
    await userEvent.click(screen.getByRole("button", { name: "Send reset link" }));
    expect(await screen.findByRole("heading", { level: 1, name: "Check your email" })).toBeInTheDocument();
    expect(screen.getByText(/If an account exists for that email/)).toBeInTheDocument();
  });

  it("sets a new password from the link and returns to sign-in with a notice", async () => {
    window.history.replaceState(null, "", "/reset-password#token=reset-token");
    const fetchMock = mockFetch({
      [ME]: signedOut,
      "POST /api/v1/auth/password-reset/confirm": () => json({ message: "Your password was changed. Sign in with your new password." }),
    });
    const { router } = renderRoute("/reset-password");
    await userEvent.type(screen.getByLabelText("New password"), "copper-meadow-harbour");
    await userEvent.type(screen.getByLabelText("Repeat new password"), "copper-meadow-harbour");
    await userEvent.click(screen.getByRole("button", { name: "Save new password" }));
    expect(await screen.findByText("Your password was changed. Sign in with your new password.")).toBeInTheDocument();
    expect(router.state.location.pathname).toBe("/sign-in");
    expect(window.location.hash).toBe("");
    expect(sentBody(fetchMock, "/api/v1/auth/password-reset/confirm")).toEqual({ token: "reset-token", new_password: "copper-meadow-harbour" });
  });

  it("catches a mismatched repeat before sending", async () => {
    window.history.replaceState(null, "", "/reset-password#token=reset-token");
    const fetchMock = mockFetch({});
    renderRoute("/reset-password");
    await userEvent.type(screen.getByLabelText("New password"), "copper-meadow-harbour");
    await userEvent.type(screen.getByLabelText("Repeat new password"), "copper-meadow-harbor");
    await userEvent.click(screen.getByRole("button", { name: "Save new password" }));
    expect(await screen.findByText("The passwords don't match.")).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("replaces the form with a way forward when the link expired", async () => {
    window.history.replaceState(null, "", "/reset-password#token=old");
    mockFetch({ "POST /api/v1/auth/password-reset/confirm": () => envelope(400, "token_expired", "This link has expired.") });
    renderRoute("/reset-password");
    await userEvent.type(screen.getByLabelText("New password"), "copper-meadow-harbour");
    await userEvent.type(screen.getByLabelText("Repeat new password"), "copper-meadow-harbour");
    await userEvent.click(screen.getByRole("button", { name: "Save new password" }));
    expect(await screen.findByRole("heading", { level: 1, name: "This link has expired" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Get a new reset link" })).toHaveAttribute("href", "/forgot-password");
  });
});

describe("account", () => {
  it("shows the profile and, when unverified, resend with a visible cooldown", async () => {
    mockFetch({
      [ME]: signedIn({ email_verified: false }),
      "POST /api/v1/auth/resend-verification": () => json({ message: "We've sent a new verification link." }, 202),
    });
    renderRoute("/account");
    const profile = await screen.findByRole("region", { name: "Profile" });
    expect(within(profile).getByText(USER.email)).toBeInTheDocument();
    expect(within(profile).getByText("Not verified")).toBeInTheDocument();
    await userEvent.click(within(profile).getByRole("button", { name: "Send a new link" }));
    expect(await within(profile).findByRole("button", { name: /^Send again in (60|59) s$/ })).toBeDisabled();
  });

  it("starts the cooldown from Retry-After when resending is rate limited", async () => {
    mockFetch({
      [ME]: signedIn({ email_verified: false }),
      "POST /api/v1/auth/resend-verification": () =>
        envelope(429, "rate_limited", "Too many requests. Try again later.", null, "r", { "Retry-After": "1800" }),
    });
    renderRoute("/account");
    await userEvent.click(await screen.findByRole("button", { name: "Send a new link" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Try again in 30 minutes.");
    expect(screen.getByRole("button", { name: "Send again in 30 min" })).toBeDisabled();
  });

  it("puts a wrong current password on its field and confirms a change", async () => {
    let attempts = 0;
    mockFetch({
      [ME]: signedIn(),
      "POST /api/v1/me/password": () =>
        ++attempts === 1
          ? envelope(400, "bad_request", "Your current password is incorrect.", [{ field: "current_password", message: "Your current password is incorrect." }])
          : json({ csrf_token: "new" }),
    });
    renderRoute("/account");
    const section = await screen.findByRole("region", { name: "Change password" });
    await userEvent.type(within(section).getByLabelText("Current password"), "not-my-password");
    await userEvent.type(within(section).getByLabelText("New password"), "copper-meadow-harbour");
    await userEvent.type(within(section).getByLabelText("Repeat new password"), "copper-meadow-harbour");
    await userEvent.click(within(section).getByRole("button", { name: "Change password" }));
    expect(await within(section).findByText("Your current password is incorrect.")).toBeInTheDocument();
    expect(within(section).getByLabelText("Current password")).toHaveFocus();

    await userEvent.clear(within(section).getByLabelText("Current password"));
    await userEvent.type(within(section).getByLabelText("Current password"), PASSWORD);
    await userEvent.click(within(section).getByRole("button", { name: "Change password" }));
    expect(await within(section).findByText(/Your password was changed/)).toBeInTheDocument();
    expect(within(section).getByLabelText("New password")).toHaveValue("");
  });

  it("sends the user to sign in with a return path when the session ended meanwhile", async () => {
    mockFetch({ [ME]: signedIn(), "POST /api/v1/me/password": signedOut });
    const { router } = renderRoute("/account");
    const section = await screen.findByRole("region", { name: "Change password" });
    await userEvent.type(within(section).getByLabelText("Current password"), PASSWORD);
    await userEvent.type(within(section).getByLabelText("New password"), "copper-meadow-harbour");
    await userEvent.type(within(section).getByLabelText("Repeat new password"), "copper-meadow-harbour");
    await userEvent.click(within(section).getByRole("button", { name: "Change password" }));
    await waitFor(() => expect(router.state.location.pathname + router.state.location.search).toBe("/sign-in?next=%2Faccount"));
  });

  it("signs out and says so on the sign-in screen", async () => {
    const fetchMock = mockFetch({ [ME]: signedIn(), "POST /api/v1/auth/logout": noContent });
    const { router } = renderRoute("/account");
    await userEvent.click(await screen.findByRole("button", { name: "Sign out" }));
    expect(await screen.findByText("You've signed out.")).toBeInTheDocument();
    expect(router.state.location.pathname).toBe("/sign-in");
    expect(requestsTo(fetchMock, "/api/v1/auth/logout")).toHaveLength(1);
  });

  it("asks before signing out everywhere, and can be cancelled", async () => {
    const fetchMock = mockFetch({ [ME]: signedIn(), "POST /api/v1/auth/logout-all": noContent });
    renderRoute("/account");
    await userEvent.click(await screen.findByRole("button", { name: "Sign out of all devices" }));
    await userEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(requestsTo(fetchMock, "/api/v1/auth/logout-all")).toHaveLength(0);

    await userEvent.click(screen.getByRole("button", { name: "Sign out of all devices" }));
    await userEvent.click(screen.getByRole("button", { name: "Sign out everywhere" }));
    expect(await screen.findByText("You've signed out on all devices.")).toBeInTheDocument();
    expect(requestsTo(fetchMock, "/api/v1/auth/logout-all")).toHaveLength(1);
  });

  it("treats a failed sign-out as signed out on this browser", async () => {
    mockFetch({ [ME]: signedIn(), "POST /api/v1/auth/logout": signedOut });
    renderRoute("/account");
    await userEvent.click(await screen.findByRole("button", { name: "Sign out" }));
    expect(await screen.findByRole("heading", { level: 1, name: "Sign in" })).toBeInTheDocument();
  });
});

it("never offers an h1 other than the page's own", async () => {
  mockFetch({ [ME]: signedOut });
  renderRoute("/sign-in");
  await screen.findByRole("heading", { level: 1, name: "Sign in" });
  expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
  expect(heading()).toHaveTextContent("Sign in");
});
