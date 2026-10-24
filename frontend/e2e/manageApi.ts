import type { Page, Route } from "@playwright/test";

/**
 * A synthetic college-administration API (backend app/api/v1/campus.py) with just enough
 * state for the Manage screens: one request waiting, two members, two departments, an
 * empty roster that a valid CSV fills, and an audit log that records decisions.
 */
const CSE = { id: "d1", code: "CSE", name: "Computer Science" };
const MECH = { id: "d2", code: "MECH", name: "Mechanical Engineering" };
const NOW = "2026-10-24T05:30:00Z";

function reply(route: Route, status: number, body?: unknown) {
  return route.fulfill({
    status,
    contentType: "application/json",
    headers: { "X-Request-ID": `e2e-manage-${status}` },
    ...(body === undefined ? {} : { body: JSON.stringify(body) }),
  });
}

function problem(route: Route, status: number, code: string, message: string, details: unknown = null) {
  return reply(route, status, { error: { code, message, details, request_id: `e2e-manage-${status}` } });
}

export async function mockManageApi(page: Page) {
  const requests = [
    {
      id: "r1",
      requester: { display_name: "Meera Iyer", email: "meera.iyer@mail.example" },
      flag: "EMAIL_MISMATCH",
      roll_number: "CSE2025007",
      roster: { full_name: "Meera Iyer", program: "B.Tech Computer Science", admission_year: 2025, department: CSE },
      status: "PENDING",
      decision_reason: null,
      created_at: "2026-10-23T09:15:00Z",
    },
    {
      id: "r2",
      requester: { display_name: "Rohan Gupta", email: "rohan.g@mail.example" },
      flag: "NO_ROSTER_MATCH",
      roll_number: "ME2025999",
      roster: null,
      status: "PENDING",
      decision_reason: null,
      created_at: "2026-10-23T11:40:00Z",
    },
  ];
  const members = [
    { id: "m1", user_id: "u1", display_name: "Kabir Shah", kind: "STUDENT", status: "ACTIVE", department: CSE, email: "kabir.shah@northfield.example", roll_number: "CSE2024001", roles: [] as unknown[], joined_at: "2026-09-01T05:00:00Z" },
    { id: "m2", user_id: "u2", display_name: "Dr. Lakshmi Pillai", kind: "FACULTY", status: "ACTIVE", department: MECH, email: "lakshmi.pillai@northfield.example", roll_number: null, roles: [{ id: "g1", role: "DEPARTMENT_ADMIN", department: MECH }], joined_at: "2026-08-20T05:00:00Z" },
  ];
  const departments = [
    { ...CSE, description: "", archived: false },
    { ...MECH, description: "", archived: false },
  ];
  const roster: unknown[] = [];
  const invites: unknown[] = [];
  const audit: unknown[] = [];
  const record = (action: string, reason: string | null = null) =>
    audit.unshift({ id: `a${audit.length + 1}`, action, actor: { id: "admin", display_name: "Aarav Nair" }, target_type: null, target_id: null, reason, metadata: {}, created_at: NOW });

  await page.route("**/api/v1/campus/**", (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname.replace("/api/v1/campus", "");
    const method = request.method();
    const body = () => request.postDataJSON() as Record<string, string>;

    if (path === "/membership-requests" && method === "GET") return reply(route, 200, { items: requests, next_cursor: null });
    const decision = path.match(/^\/membership-requests\/(\w+)\/(approve|reject)$/);
    if (decision && method === "POST") {
      const [, id, verb] = decision;
      const index = requests.findIndex((r) => r.id === id);
      if (index < 0) return problem(route, 404, "not_found", "Not found.");
      if (verb === "approve" && requests[index]!.roster === null) {
        return problem(route, 409, "no_roster_entry", "Add this roll number to the roster first, or reject the request.");
      }
      requests.splice(index, 1);
      record(verb === "approve" ? "membership.approved" : "membership.rejected", verb === "reject" ? body().reason ?? null : null);
      return reply(route, 200, { id, status: verb === "approve" ? "ACTIVE" : "REJECTED" });
    }
    if (path === "/members" && method === "GET") {
      const kind = url.searchParams.get("kind");
      const status = url.searchParams.get("status");
      const items = members.filter((m) => (!kind || m.kind === kind) && (!status || m.status === status));
      return reply(route, 200, { items, next_cursor: null });
    }
    const member = path.match(/^\/members\/(\w+)$/);
    if (member && method === "PATCH") {
      const target = members.find((m) => m.id === member[1]);
      if (!target) return problem(route, 404, "not_found", "Not found.");
      const { status, reason } = body();
      if (status) {
        target.status = status;
        record(`college.membership_${status === "SUSPENDED" ? "suspended" : status === "ENDED" ? "ended" : "reactivated"}`, reason ?? null);
      }
      return reply(route, 200, target);
    }
    if (path === "/departments" && method === "GET") {
      const all = url.searchParams.get("include_archived") === "true";
      return reply(route, 200, { items: departments.filter((d) => all || !d.archived) });
    }
    if (path === "/departments" && method === "POST") {
      const { code, name, description } = body();
      if (departments.some((d) => d.code === code)) return problem(route, 409, "code_taken", "A department with this code already exists.");
      const created = { id: `d${departments.length + 1}`, code: code!, name: name!, description: description ?? "", archived: false };
      departments.push(created);
      record("college.department_created");
      return reply(route, 201, created);
    }
    if (path === "/invites" && method === "GET") return reply(route, 200, { items: invites });
    if (path === "/invites" && method === "POST") {
      const { email, kind } = body();
      const invite = { id: `i${invites.length + 1}`, email, kind, state: "PENDING", created_at: NOW, expires_at: "2026-10-31T05:30:00Z" };
      invites.unshift(invite);
      record("college.invite_sent");
      return reply(route, 201, invite);
    }
    if (path === "/roster" && method === "GET") return reply(route, 200, { items: roster, next_cursor: null });
    if (path === "/roster/import" && method === "POST") {
      const lines = (body().csv ?? "").trim().split("\n").slice(1);
      const problems = lines.flatMap((line, i) => {
        const department = line.split(",")[2];
        return departments.some((d) => d.code === department) ? [] : [{ row: i + 2, column: "department_code", message: "No current department has this code." }];
      });
      if (problems.length) return problem(route, 422, "roster_invalid", "The roster file has problems. Nothing was imported.", problems);
      for (const line of lines) {
        const [roll_number, full_name, code, program, year, email] = line.split(",");
        roster.push({ id: roll_number, roll_number, full_name, email: email || null, program, admission_year: Number(year), department: departments.find((d) => d.code === code), claimed: false });
      }
      record("college.roster_imported");
      return reply(route, 201, { imported: lines.length });
    }
    if (path === "/audit-log" && method === "GET") {
      const action = url.searchParams.get("action");
      return reply(route, 200, { items: audit.filter((e) => !action || (e as { action: string }).action === action), next_cursor: null });
    }
    return route.abort("blockedbyclient");
  });
}
