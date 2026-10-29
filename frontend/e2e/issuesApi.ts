import type { Page, Route } from "@playwright/test";

/**
 * A synthetic issues API (backend app/api/v1/issues.py): report, list (mine or the queue),
 * open one, comment, change status, assign. Mirrors the server's responses, including the
 * `actions` the policies would allow a reporter or, with `staff`, a coordinator.
 */
const NOW = "2026-10-24T05:30:00Z";

interface StoredIssue {
  id: string;
  title: string;
  category: string;
  location: string;
  room: string | null;
  description: string;
  status: string;
  resolved_at: string | null;
  assignee_name: string | null;
  created_at: string;
  version: number;
  updates: Record<string, unknown>[];
}

function reply(route: Route, status: number, body: unknown) {
  return route.fulfill({ status, contentType: "application/json", headers: { "X-Request-ID": `e2e-issues-${status}` }, body: JSON.stringify(body) });
}

const entry = (id: string, over: Record<string, unknown>) => ({
  id,
  kind: "CREATED",
  from_status: null,
  to_status: null,
  body: null,
  is_internal: false,
  actor_name: "Aarav Nair",
  assignee_name: null,
  created_at: NOW,
  ...over,
});

// PRD §9.8.1 for coordinators: (to, needs a note) by current status.
const STAFF_TRANSITIONS: Record<string, [string, boolean][]> = {
  SUBMITTED: [["ACKNOWLEDGED", false], ["REJECTED", true]],
  ACKNOWLEDGED: [["IN_PROGRESS", false], ["REJECTED", true]],
  IN_PROGRESS: [["RESOLVED", true]],
  RESOLVED: [["ACKNOWLEDGED", true]],
  REJECTED: [["ACKNOWLEDGED", true]],
};
const ASSIGNEES = [
  { id: "m-ravi", name: "Ravi Sharma", kind: "FACULTY" },
  { id: "m-meera", name: "Meera Iyer", kind: "STAFF" },
];

export async function mockIssuesApi(page: Page, { staff = false }: { staff?: boolean } = {}) {
  const issues: StoredIssue[] = [
    {
      id: "i1",
      title: "Lab 3 projector flickers",
      category: "CLASSROOM_EQUIPMENT",
      location: "Block C, first floor",
      room: "C-103",
      description: "The image flickers every few seconds.\nWorse when the room lights are on.",
      status: "RESOLVED",
      resolved_at: "2026-10-23T09:00:00Z",
      assignee_name: "Ravi Sharma",
      created_at: "2026-10-21T04:30:00Z",
      version: 5,
      updates: [
        entry("u1", { created_at: "2026-10-21T04:30:00Z" }),
        entry("u2", { kind: "STATUS", from_status: "SUBMITTED", to_status: "ACKNOWLEDGED", actor_name: "Meera Iyer", created_at: "2026-10-21T06:00:00Z" }),
        entry("u3", { kind: "ASSIGNMENT", actor_name: "Meera Iyer", assignee_name: "Ravi Sharma", created_at: "2026-10-21T06:01:00Z" }),
        entry("u4", { kind: "STATUS", from_status: "ACKNOWLEDGED", to_status: "IN_PROGRESS", actor_name: "Ravi Sharma", created_at: "2026-10-22T05:00:00Z" }),
        entry("u5", { kind: "STATUS", from_status: "IN_PROGRESS", to_status: "RESOLVED", body: "Replaced the HDMI cable.", actor_name: "Ravi Sharma", created_at: "2026-10-23T09:00:00Z" }),
      ],
    },
  ];
  if (staff) {
    issues.push({
      id: "i2",
      title: "Wi-Fi drops in the library",
      category: "NETWORK",
      location: "Central library, reading hall",
      room: null,
      description: "The connection drops every few minutes on the second floor.",
      status: "SUBMITTED",
      resolved_at: null,
      assignee_name: null,
      created_at: "2026-10-22T08:00:00Z",
      version: 1,
      updates: [entry("w1", { actor_name: "Ishita Verma", created_at: "2026-10-22T08:00:00Z" })],
    });
  }
  const view = (i: StoredIssue) => {
    const open = i.status !== "REJECTED";
    const reopen = i.status === "RESOLVED" ? [{ to_status: "ACKNOWLEDGED", needs_note: true }] : [];
    const transitions = staff ? (STAFF_TRANSITIONS[i.status] ?? []).map(([to_status, needs_note]) => ({ to_status, needs_note })) : reopen;
    return {
      ...i,
      reporter_name: i.id === "i2" ? "Ishita Verma" : "Aarav Nair",
      updated_at: NOW,
      duplicate_of: null,
      actions: { transitions, assign: staff, comment: staff || open, comment_internal: staff },
    };
  };
  const summary = (i: StoredIssue) => ({
    id: i.id,
    title: i.title,
    category: i.category,
    location: i.location,
    room: i.room,
    status: i.status,
    reporter_name: i.id === "i2" ? "Ishita Verma" : "Aarav Nair",
    assignee_name: i.assignee_name,
    created_at: i.created_at,
    updated_at: NOW,
  });

  await page.route("**/api/v1/campus/issues**", (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname.replace("/api/v1/campus/issues", "");
    const method = request.method();

    if (path === "" && method === "GET") {
      if (url.searchParams.get("scope") === "queue") {
        // ISSUE-009: unacknowledged first, oldest first within each group.
        const rank = (i: StoredIssue) => (i.status === "SUBMITTED" ? 0 : 1);
        const queue = [...issues].sort((a, b) => rank(a) - rank(b) || a.created_at.localeCompare(b.created_at));
        return reply(route, 200, { items: queue.map(summary), next_cursor: null });
      }
      return reply(route, 200, { items: [...issues].reverse().map(summary), next_cursor: null });
    }
    if (path === "" && method === "POST") {
      const input = request.postDataJSON() as Record<string, string>;
      const created: StoredIssue = {
        id: `i${issues.length + 1}`,
        title: input.title ?? "",
        category: input.category ?? "OTHER",
        location: input.location ?? "",
        room: input.room ?? null,
        description: input.description ?? "",
        status: "SUBMITTED",
        resolved_at: null,
        assignee_name: null,
        created_at: NOW,
        version: 1,
        updates: [entry(`u${Date.now()}`, {})],
      };
      issues.push(created);
      return reply(route, 201, view(created));
    }
    const one = path.match(/^\/(\w+)(?:\/(transitions|updates|assignment))?$/);
    const found = one && issues.find((i) => i.id === one[1]);
    if (!one || !found) return reply(route, 404, { error: { code: "not_found", message: "Not found.", details: null, request_id: "x" } });
    if (one[2] === "updates" && method === "POST") {
      const { body, is_internal } = request.postDataJSON() as { body: string; is_internal: boolean };
      found.updates.push(entry(`c${found.updates.length + 1}`, { kind: "COMMENT", body, is_internal, actor_name: staff ? "Priya Menon" : "Aarav Nair" }));
      return reply(route, 201, view(found));
    }
    if (one[2] === "transitions" && method === "POST") {
      const { to_status, note } = request.postDataJSON() as { to_status: string; note: string };
      found.updates.push(entry(`s${found.updates.length + 1}`, { kind: "STATUS", from_status: found.status, to_status, body: note ?? null, actor_name: staff ? "Priya Menon" : "Aarav Nair" }));
      Object.assign(found, { status: to_status, resolved_at: to_status === "RESOLVED" ? NOW : null, version: found.version + 1 });
      return reply(route, 200, view(found));
    }
    if (one[2] === "assignment" && method === "POST") {
      const { assignee_id } = request.postDataJSON() as { assignee_id: string | null };
      const assignee = ASSIGNEES.find((a) => a.id === assignee_id) ?? null;
      found.updates.push(entry(`a${found.updates.length + 1}`, { kind: "ASSIGNMENT", actor_name: "Priya Menon", assignee_name: assignee?.name ?? null }));
      Object.assign(found, { assignee_name: assignee?.name ?? null, version: found.version + 1 });
      return reply(route, 200, view(found));
    }
    return reply(route, 200, view(found));
  });
}

/** GET /campus/assignees: ACTIVE faculty and staff by name. */
export async function mockAssigneesApi(page: Page) {
  await page.route("**/api/v1/campus/assignees**", (route) => {
    const query = (new URL(route.request().url()).searchParams.get("query") ?? "").toLowerCase();
    return reply(route, 200, { items: ASSIGNEES.filter((a) => a.name.toLowerCase().includes(query)), next_cursor: null });
  });
}
