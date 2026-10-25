import type { Page, Route } from "@playwright/test";

/**
 * A synthetic notices API (backend app/api/v1/notices.py) with drafts, publishing, withdrawal
 * and department pages. Readers see published notices only; the college admin manages all.
 */
const CSE = { id: "d1", code: "CSE", name: "Computer Science" };
const MECH = { id: "d2", code: "MECH", name: "Mechanical Engineering" };
const NOW = "2026-10-24T05:30:00Z";

interface StoredNotice {
  id: string;
  title: string;
  body: string;
  category: string;
  priority: string;
  scope: string;
  department: typeof CSE | null;
  status: string;
  published_at: string | null;
  expires_at: string | null;
  edited_at: string | null;
  created_at: string;
  version: number;
}

const LIST_ITEM = /^\s*(?:[-+*]|\d+\.)\s+/;

/** The backend's preview rule (app/schemas/notices.py `excerpt`): markup out, list items apart. */
function previewOf(body: string): string {
  let text = "";
  let previousItem = false;
  for (const line of body.split("\n")) {
    const item = LIST_ITEM.test(line);
    const words = line
      .replace(LIST_ITEM, "")
      .replace(/\[([^\]]*)\]\([^)]*\)/g, "$1")
      .replace(/[*_`#>]/g, "")
      .split(/\s+/)
      .filter(Boolean)
      .join(" ");
    if (!words) continue;
    if (text) text += (item || previousItem) && !/[.!?:;…]$/.test(text) ? " · " : " ";
    text += words;
    previousItem = item;
  }
  return text.length <= 160 ? text : `${text.slice(0, 159).trimEnd()}…`;
}

function reply(route: Route, status: number, body: unknown) {
  return route.fulfill({ status, contentType: "application/json", headers: { "X-Request-ID": `e2e-notices-${status}` }, body: JSON.stringify(body) });
}

export async function mockNoticesApi(page: Page, { manager }: { manager: boolean }) {
  const notices: StoredNotice[] = [
    {
      id: "n1",
      title: "Mid-term timetable",
      body: "Mid-terms run **3 to 7 November**.\n\n- Bring your ID card\n- Arrive 15 minutes early\n\nSee the [exam cell page](https://northfield.example/exams).",
      category: "EXAMINATION",
      priority: "HIGH",
      scope: "DEPARTMENT",
      department: CSE,
      status: "PUBLISHED",
      published_at: "2026-10-23T04:30:00Z",
      expires_at: null,
      edited_at: null,
      created_at: "2026-10-23T04:00:00Z",
      version: 2,
    },
    {
      id: "n2",
      title: "Library hours extended",
      body: "The library stays open until 10 pm during exams.",
      category: "FACILITIES",
      priority: "NORMAL",
      scope: "COLLEGE",
      department: null,
      status: "PUBLISHED",
      published_at: "2026-10-22T09:00:00Z",
      expires_at: null,
      edited_at: null,
      created_at: "2026-10-22T09:00:00Z",
      version: 2,
    },
  ];
  const view = (n: StoredNotice) => {
    const pinned = n.status === "PUBLISHED" && n.priority === "URGENT";
    const excerpt = previewOf(n.body);
    return { ...n, excerpt, pinned, expired: false, can_manage: manager, author_name: manager ? "Aarav Nair" : null };
  };

  await page.route("**/api/v1/campus/**", (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname.replace("/api/v1/campus", "");
    const method = request.method();

    if (path === "/departments" && method === "GET") {
      return reply(route, 200, { items: [CSE, MECH].map((d) => ({ ...d, description: "", archived: false })) });
    }
    const dept = path.match(/^\/departments\/(\w+)$/);
    if (dept && method === "GET") {
      const found = [CSE, MECH].find((d) => d.id === dept[1]);
      if (!found) return reply(route, 404, { error: { code: "not_found", message: "Not found.", details: null, request_id: "x" } });
      return reply(route, 200, { ...found, description: "Labs and lecture halls in block C.", archived: false, admins: ["Ravi Sharma"] });
    }
    if (path === "/notices" && method === "GET") {
      const status = url.searchParams.get("status") ?? "PUBLISHED";
      const department = url.searchParams.get("department_id");
      const category = url.searchParams.get("category");
      const items = notices
        .filter((n) => n.status === status && (manager || n.status === "PUBLISHED"))
        .filter((n) => !department || n.department?.id === department)
        .filter((n) => !category || n.category === category)
        .map(view)
        .sort((a, b) => Number(b.pinned) - Number(a.pinned) || (b.published_at ?? b.created_at).localeCompare(a.published_at ?? a.created_at));
      return reply(route, 200, { items, next_cursor: null });
    }
    if (path === "/notices" && method === "POST") {
      const input = request.postDataJSON() as Record<string, string | boolean | null>;
      const department = [CSE, MECH].find((d) => d.id === input.department_id) ?? null;
      const created: StoredNotice = {
        id: `n${notices.length + 1}`,
        title: String(input.title),
        body: String(input.body),
        category: String(input.category),
        priority: String(input.priority),
        scope: String(input.scope),
        department,
        status: input.publish ? "PUBLISHED" : "DRAFT",
        published_at: input.publish ? NOW : null,
        expires_at: (input.expires_at as string | null) ?? null,
        edited_at: null,
        created_at: NOW,
        version: input.publish ? 2 : 1,
      };
      notices.push(created);
      return reply(route, 201, view(created));
    }
    const one = path.match(/^\/notices\/(\w+)(?:\/(publish|withdraw))?$/);
    if (one) {
      const found = notices.find((n) => n.id === one[1]);
      if (!found || (!manager && found.status !== "PUBLISHED")) {
        return reply(route, 404, { error: { code: "not_found", message: "Not found.", details: null, request_id: "x" } });
      }
      if (one[2] === "publish") Object.assign(found, { status: "PUBLISHED", published_at: NOW, version: found.version + 1 });
      if (one[2] === "withdraw") Object.assign(found, { status: "WITHDRAWN", version: found.version + 1 });
      if (method === "PATCH") Object.assign(found, request.postDataJSON(), { version: found.version + 1, edited_at: found.status === "PUBLISHED" ? NOW : null });
      return reply(route, 200, view(found));
    }
    return route.abort("blockedbyclient");
  });
}
