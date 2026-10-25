import AxeBuilder from "@axe-core/playwright";
import { expect, type Page, type Route } from "@playwright/test";

/** Synthetic backend states. Each maps to what the real FastAPI endpoints return. */
export type BackendState =
  | "ready"
  | "migrations_pending"
  | "database_unreachable"
  | "api_unreachable"
  | "server_error";

function json(route: Route, status: number, body: unknown, requestId: string) {
  return route.fulfill({
    status,
    contentType: "application/json",
    headers: { "X-Request-ID": requestId },
    body: JSON.stringify(body),
  });
}

function notReady(route: Route, details: Record<string, string>) {
  return json(
    route,
    503,
    { error: { code: "not_ready", message: "The service is not ready.", details, request_id: "e2e-503" } },
    "e2e-503",
  );
}

/**
 * Route /healthz and /readyz to a synthetic state and answer /api/v1/me as signed out.
 * Any other API call fails the test, so screens can't silently depend on unmocked endpoints.
 */
export async function mockBackend(page: Page, state: BackendState): Promise<void> {
  await page.route("**/api/**", (route) => route.abort("blockedbyclient"));
  await page.route("**/api/v1/me", (route) =>
    json(route, 401, { error: { code: "not_authenticated", message: "Sign in to continue.", details: null, request_id: "e2e-401" } }, "e2e-401"),
  );

  await page.route("**/healthz", (route) => {
    if (state === "api_unreachable") return route.abort("connectionrefused");
    if (state === "server_error") {
      return json(
        route,
        500,
        {
          error: {
            code: "internal_error",
            message: "Something went wrong on our side.",
            details: null,
            request_id: "e2e-req-500",
          },
        },
        "e2e-req-500",
      );
    }
    return json(route, 200, { status: "ok" }, "e2e-health");
  });

  await page.route("**/readyz", (route) => {
    if (state === "migrations_pending") return notReady(route, { migrations: "pending" });
    if (state === "database_unreachable") return notReady(route, { database: "unreachable" });
    return json(route, 200, { status: "ready" }, "e2e-ready");
  });
}

/** WCAG 2.0/2.1/2.2 A and AA rules (PRD NFR-A11Y-001). Fails listing each violation. */
export async function expectNoAxeViolations(page: Page): Promise<void> {
  const results = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"])
    .analyze();
  const summary = results.violations.map((v) => `${v.id} (${v.impact ?? "n/a"}): ${v.nodes.length} node(s) — ${v.help}`);
  expect(summary).toEqual([]);
}

/** Row in the status list, e.g. statusRow(page, "Database"). */
export function statusRow(page: Page, name: "API" | "Database") {
  return page.locator("dl > div").filter({ has: page.locator("dt", { hasText: name }) });
}

export interface FakeAccount {
  signedIn: boolean;
  emailVerified: boolean;
  /** NONE: no college yet; PENDING: request waiting; ACTIVE: member of Northfield (demo). */
  membership: "NONE" | "PENDING" | "ACTIVE";
  /** A college admin of Northfield (staff member); needs membership ACTIVE. */
  admin: boolean;
  /** A platform admin account (no college, can't join one). */
  platform: boolean;
}

const NORTHFIELD = {
  id: "c0000000-0000-4000-8000-000000000001",
  name: "Northfield Institute",
  slug: "northfield",
  timezone: "Asia/Kolkata",
  status: "ACTIVE",
  is_demo: true,
};

const FAKE_USER = {
  id: "8d6c1c55-6a66-4bd7-9b1b-6b8e1d1d0001",
  email: "aarav@northfield.example",
  display_name: "Aarav Nair",
  platform_role: null,
};

function apiError(route: Route, status: number, code: string, message: string, details: unknown = null, headers: Record<string, string> = {}) {
  return route.fulfill({
    status,
    contentType: "application/json",
    headers: { "X-Request-ID": `e2e-${status}`, ...headers },
    body: JSON.stringify({ error: { code, message, details, request_id: `e2e-${status}` } }),
  });
}

/**
 * A synthetic auth API with just enough state for the screens: who is signed in and
 * whether the email is verified. Responses follow the real FastAPI endpoints
 * (backend app/api/v1/auth.py, me.py). The password "wrong-password" fails sign-in.
 */
export async function mockAuthApi(page: Page, initial: Partial<FakeAccount> = {}): Promise<FakeAccount> {
  const account: FakeAccount = { signedIn: false, emailVerified: true, membership: "NONE", admin: false, platform: false, ...initial };
  const user = () => ({
    ...FAKE_USER,
    email_verified: account.emailVerified,
    ...(account.platform ? { email: "ops@campussignal.example", display_name: "Platform Ops", platform_role: "PLATFORM_ADMIN" } : {}),
  });
  const me = () => ({
    user: user(),
    membership:
      account.membership === "NONE"
        ? null
        : {
            id: "5b1c0d5e-0000-4000-8000-000000000001",
            kind: account.admin ? "STAFF" : "STUDENT",
            status: account.membership,
            college: NORTHFIELD,
            department: account.membership === "ACTIVE" && !account.admin ? { id: "d1", code: "CSE", name: "Computer Science" } : null,
          },
    roles: account.admin ? [{ role: "COLLEGE_ADMIN", department: null }] : [],
    capabilities: account.platform ? ["platform"] : account.membership !== "ACTIVE" ? [] : account.admin ? ["campus", "manage_college", "review_memberships"] : ["campus"],
  });
  await mockBackend(page, "ready");

  await page.route("**/api/v1/me", (route) =>
    account.signedIn ? json(route, 200, me(), "e2e-me") : apiError(route, 401, "not_authenticated", "Sign in to continue."),
  );
  // The shell's bell polls this on every signed-in screen; notifications.spec.ts overrides it.
  await page.route("**/api/v1/me/notifications/unread-count", (route) => json(route, 200, { unread: 0 }, "e2e-unread"));
  // Home lists current notices; noticesApi.ts replaces this with real ones where a spec needs them.
  await page.route("**/api/v1/campus/notices", (route) => json(route, 200, { items: [], next_cursor: null }, "e2e-no-notices"));
  await page.route("**/api/v1/colleges", (route) =>
    json(route, 200, { items: [{ name: "Northfield Institute", slug: "northfield" }, { name: "Riverside College", slug: "riverside" }] }, "e2e-colleges"),
  );
  await page.route("**/api/v1/me/membership-requests", (route) => {
    if (route.request().method() === "GET") return json(route, 200, { items: [] }, "e2e-requests");
    const { roll_number } = route.request().postDataJSON() as { roll_number: string };
    if (roll_number.trim().toUpperCase() === "N-100") {
      account.membership = "ACTIVE";
      return json(route, 201, { status: "ACTIVE", message: "You've joined Northfield Institute.", membership: me().membership }, "e2e-join");
    }
    account.membership = "PENDING";
    return json(route, 202, { status: "PENDING", message: "Request sent. Northfield Institute will review it." }, "e2e-join");
  });
  await page.route("**/api/v1/invites/accept", (route) => {
    const { token } = route.request().postDataJSON() as { token: string };
    if (token === "used") return apiError(route, 400, "token_used", "This invitation was already used.");
    account.membership = "ACTIVE";
    return json(route, 200, { membership: me().membership }, "e2e-invite");
  });
  await page.route("**/api/v1/auth/login", (route) => {
    const body = route.request().postDataJSON() as { password?: string };
    if (body.password === "wrong-password") return apiError(route, 401, "invalid_credentials", "Email or password is incorrect.");
    account.signedIn = true;
    return json(route, 200, { user: user(), csrf_token: "e2e-csrf" }, "e2e-login");
  });
  await page.route("**/api/v1/auth/register", (route) => {
    const body = route.request().postDataJSON() as { password?: string };
    if (body.password === "password1234") {
      return apiError(route, 422, "validation_error", "Some fields are invalid.", [
        { field: "password", message: "This password is too common. Choose one that's harder to guess." },
      ]);
    }
    return json(route, 201, { message: "Check your email to finish setting up your account." }, "e2e-register");
  });
  await page.route("**/api/v1/auth/verify-email", (route) => {
    const { token } = route.request().postDataJSON() as { token: string };
    if (token === "expired") return apiError(route, 400, "token_expired", "This link has expired.");
    if (token === "used") return apiError(route, 400, "token_used", "This link was already used.");
    account.emailVerified = true;
    return json(route, 200, { message: "Your email is verified." }, "e2e-verify");
  });
  await page.route("**/api/v1/auth/resend-verification", (route) =>
    json(route, 202, { message: "We've sent a new verification link." }, "e2e-resend"),
  );
  await page.route("**/api/v1/auth/password-reset/request", (route) =>
    json(route, 202, { message: "If an account exists for that email, we've sent a reset link." }, "e2e-reset"),
  );
  await page.route("**/api/v1/auth/password-reset/confirm", (route) => {
    account.signedIn = false;
    return json(route, 200, { message: "Your password was changed. Sign in with your new password." }, "e2e-reset-ok");
  });
  await page.route("**/api/v1/me/password", (route) => json(route, 200, { csrf_token: "e2e-csrf-2" }, "e2e-pw"));
  for (const path of ["logout", "logout-all"]) {
    await page.route(`**/api/v1/auth/${path}`, (route) => {
      account.signedIn = false;
      return route.fulfill({ status: 204 });
    });
  }
  return account;
}

export async function expectNoHorizontalScroll(page: Page): Promise<void> {
  const { scrollWidth, innerWidth } = await page.evaluate(() => ({
    scrollWidth: document.documentElement.scrollWidth,
    innerWidth: window.innerWidth,
  }));
  expect(scrollWidth).toBeLessThanOrEqual(innerWidth);
}
