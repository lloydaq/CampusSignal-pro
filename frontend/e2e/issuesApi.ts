import type { Page, Route } from "@playwright/test";

/**
 * A synthetic issues API (backend app/api/v1/issues.py) for the reporter's screens: report,
 * list mine, open one, comment, and reopen a resolved one. Mirrors the server's responses,
 * including the `actions` the policies would allow a reporter.
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

export async function mockIssuesApi(page: Page) {
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
  const view = (i: StoredIssue) => {
    const open = i.status !== "REJECTED";
    const reopen = i.status === "RESOLVED" ? [{ to_status: "ACKNOWLEDGED", needs_note: true }] : [];
    return {
      ...i,
      reporter_name: "Aarav Nair",
      updated_at: NOW,
      duplicate_of: null,
      actions: { transitions: reopen, assign: false, comment: open, comment_internal: false },
    };
  };
  const summary = (i: StoredIssue) => ({
    id: i.id,
    title: i.title,
    category: i.category,
    location: i.location,
    room: i.room,
    status: i.status,
    reporter_name: "Aarav Nair",
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
    const one = path.match(/^\/(\w+)(?:\/(transitions|updates))?$/);
    const found = one && issues.find((i) => i.id === one[1]);
    if (!one || !found) return reply(route, 404, { error: { code: "not_found", message: "Not found.", details: null, request_id: "x" } });
    if (one[2] === "updates" && method === "POST") {
      const { body } = request.postDataJSON() as { body: string };
      found.updates.push(entry(`c${found.updates.length + 1}`, { kind: "COMMENT", body }));
      return reply(route, 201, view(found));
    }
    if (one[2] === "transitions" && method === "POST") {
      const { to_status, note } = request.postDataJSON() as { to_status: string; note: string };
      found.updates.push(entry(`s${found.updates.length + 1}`, { kind: "STATUS", from_status: found.status, to_status, body: note }));
      Object.assign(found, { status: to_status, resolved_at: null, version: found.version + 1 });
      return reply(route, 200, view(found));
    }
    return reply(route, 200, view(found));
  });
}
