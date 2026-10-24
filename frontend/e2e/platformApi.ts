import type { Page, Route } from "@playwright/test";

/**
 * A synthetic platform API (backend app/api/v1/platform.py): colleges that can be created,
 * activated and suspended, first-admin invitations, an account lookup and an audit log.
 */
const NOW = "2026-10-24T05:30:00Z";

function reply(route: Route, status: number, body: unknown) {
  return route.fulfill({
    status,
    contentType: "application/json",
    headers: { "X-Request-ID": `e2e-platform-${status}` },
    body: JSON.stringify(body),
  });
}

function problem(route: Route, status: number, code: string, message: string, details: unknown = null) {
  return reply(route, status, { error: { code, message, details, request_id: `e2e-platform-${status}` } });
}

export async function mockPlatformApi(page: Page) {
  const colleges: Record<string, unknown>[] = [
    { id: "c2", name: "Riverside College", slug: "riverside", timezone: "Asia/Kolkata", status: "ACTIVE", email_domains: ["riverside.example"], is_demo: true, created_at: "2026-10-01T05:00:00Z", active_member_count: 42, admin_invites: [] },
  ];
  const user = { id: "u1", email: "kabir.shah@northfield.example", display_name: "Kabir Shah", status: "ACTIVE", platform_role: null as string | null };
  const audit: unknown[] = [];
  const record = (action: string, reason: string | null = null) =>
    audit.unshift({ id: `a${audit.length + 1}`, action, actor_user_id: "ops", college_id: null, target_type: "college", target_id: null, reason, metadata: {}, created_at: NOW });
  const summary = ({ admin_invites: _ignored, ...rest }: Record<string, unknown>) => rest;

  await page.route("**/api/v1/platform/**", (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname.replace("/api/v1/platform", "");
    const method = request.method();
    const body = () => request.postDataJSON() as Record<string, string>;

    if (path === "/colleges" && method === "GET") return reply(route, 200, { items: colleges.map(summary), next_cursor: null });
    if (path === "/colleges" && method === "POST") {
      const input = request.postDataJSON() as { name: string; slug: string };
      if (colleges.some((c) => c.slug === input.slug)) return problem(route, 409, "slug_taken", "A college with this slug already exists.");
      const created = { id: `c${colleges.length + 2}`, ...input, timezone: "Asia/Kolkata", status: "ONBOARDING", email_domains: [], is_demo: false, created_at: NOW, active_member_count: 0, admin_invites: [] };
      colleges.unshift(created);
      record("platform.college_created");
      return reply(route, 201, summary(created));
    }
    const college = path.match(/^\/colleges\/(\w+)$/);
    if (college) {
      const found = colleges.find((c) => c.id === college[1]);
      if (!found) return problem(route, 404, "not_found", "Not found.");
      if (method === "PATCH") {
        const { status, reason } = body();
        if (status === "SUSPENDED" && !reason) return problem(route, 422, "validation_error", "Some fields are invalid.", [{ field: "reason", message: "Give a reason for suspending the college." }]);
        found.status = status;
        record("platform.college_status_changed", reason ?? null);
      }
      return reply(route, 200, found);
    }
    const invite = path.match(/^\/colleges\/(\w+)\/admin-invites$/);
    if (invite && method === "POST") {
      const found = colleges.find((c) => c.id === invite[1]);
      if (!found) return problem(route, 404, "not_found", "Not found.");
      const { email, kind } = body();
      const created = { id: `i${(found.admin_invites as unknown[]).length + 1}`, email, kind, state: "PENDING", created_at: NOW, expires_at: "2026-10-31T05:30:00Z" };
      (found.admin_invites as unknown[]).unshift(created);
      record("platform.admin_invited");
      return reply(route, 201, created);
    }
    if (path === "/users" && method === "GET") {
      return reply(route, 200, { items: url.searchParams.get("email") === user.email ? [user] : [] });
    }
    const change = path.match(/^\/users\/u1\/(suspend|unsuspend)$/);
    if (change && method === "POST") {
      user.status = change[1] === "suspend" ? "SUSPENDED" : "ACTIVE";
      record(change[1] === "suspend" ? "platform.user_suspended" : "platform.user_unsuspended", body().reason ?? null);
      return reply(route, 200, user);
    }
    if (path === "/audit-log" && method === "GET") return reply(route, 200, { items: audit, next_cursor: null });
    return route.abort("blockedbyclient");
  });
}
