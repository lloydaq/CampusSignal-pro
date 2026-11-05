import type { Page, Route } from "@playwright/test";

/**
 * A synthetic community API (backend app/api/v1/community.py) for one signed-in member, Aarav
 * Nair of CSE: college and department feeds, posting, Helpful, comments, editing, deleting and
 * reporting. Mirrors the server's responses, including the `can_*` flags.
 */
const NOW = "2026-10-24T05:30:00Z";
const CSE = { id: "d1", code: "CSE", name: "Computer Science" };
const ME = { name: "Aarav Nair", kind: "STUDENT" };

interface StoredPost {
  id: string;
  body: string;
  visibility: "COLLEGE" | "DEPARTMENT";
  author: { name: string; kind: string };
  created_at: string;
  edited_at: string | null;
  reactions: number;
  reacted: boolean;
  comments: { id: string; body: string; author: { name: string; kind: string }; created_at: string }[];
}

function reply(route: Route, status: number, body?: unknown) {
  return route.fulfill({
    status,
    contentType: "application/json",
    headers: { "X-Request-ID": `e2e-community-${status}` },
    body: body === undefined ? "" : JSON.stringify(body),
  });
}

export async function mockCommunityApi(page: Page) {
  const posts: StoredPost[] = [
    {
      id: "p1",
      body: "The robotics lab is open late on Thursdays this month. Booking sheet: https://northfield.example/robotics",
      visibility: "COLLEGE",
      author: { name: "Ravi Sharma", kind: "FACULTY" },
      created_at: "2026-10-24T04:00:00Z",
      edited_at: null,
      reactions: 4,
      reacted: false,
      comments: [{ id: "c1", body: "Is it open to first years?", author: { name: "Ishita Verma", kind: "STUDENT" }, created_at: "2026-10-24T04:20:00Z" }],
    },
    {
      id: "p2",
      body: "Anyone have notes from Tuesday's compilers lecture?",
      visibility: "DEPARTMENT",
      author: { name: "Kabir Shah", kind: "STUDENT" },
      created_at: "2026-10-24T03:00:00Z",
      edited_at: null,
      reactions: 0,
      reacted: false,
      comments: [],
    },
  ];
  let next = 10;
  const mine = (p: StoredPost) => p.author.name === ME.name;
  const view = (p: StoredPost) => ({
    id: p.id,
    body: p.body,
    visibility: p.visibility,
    department: p.visibility === "DEPARTMENT" ? CSE : null,
    author: p.author,
    status: "VISIBLE",
    hidden_reason: null,
    edited_at: p.edited_at,
    created_at: p.created_at,
    reaction_count: p.reactions,
    comment_count: p.comments.length,
    reacted: p.reacted,
    can_edit: mine(p),
    can_delete: mine(p),
    can_engage: true,
  });
  const commentView = (c: StoredPost["comments"][number]) => ({
    ...c,
    status: "VISIBLE",
    hidden_reason: null,
    edited_at: null,
    can_edit: c.author.name === ME.name,
    can_delete: c.author.name === ME.name,
  });

  await page.route("**/api/v1/campus/{posts,reports,comments}**", (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname.replace("/api/v1/campus", "");
    const method = request.method();

    if (path === "/reports" && method === "POST") return reply(route, 201, { id: "r1", status: "OPEN" });
    if (path === "/posts" && method === "GET") {
      const feed = url.searchParams.get("feed") === "department" ? "DEPARTMENT" : "COLLEGE";
      const items = posts.filter((p) => p.visibility === feed).sort((a, b) => b.created_at.localeCompare(a.created_at));
      return reply(route, 200, { items: items.map(view), next_cursor: null });
    }
    if (path === "/posts" && method === "POST") {
      const input = request.postDataJSON() as { body: string; visibility: "COLLEGE" | "DEPARTMENT" };
      const created: StoredPost = { id: `p${next++}`, ...input, author: ME, created_at: NOW, edited_at: null, reactions: 0, reacted: false, comments: [] };
      posts.push(created);
      return reply(route, 201, view(created));
    }
    const one = path.match(/^\/posts\/(\w+)(?:\/(comments|reaction))?$/);
    const found = one && posts.find((p) => p.id === one[1]);
    if (!one || !found) return reply(route, 404, { error: { code: "not_found", message: "Not found.", details: null, request_id: "x" } });
    if (one[2] === "reaction") {
      const on = method === "PUT";
      if (on !== found.reacted) found.reactions += on ? 1 : -1;
      found.reacted = on;
      return reply(route, 200, { reacted: on, reaction_count: found.reactions });
    }
    if (one[2] === "comments" && method === "POST") {
      const { body } = request.postDataJSON() as { body: string };
      const created = { id: `c${next++}`, body, author: ME, created_at: NOW };
      found.comments.push(created);
      return reply(route, 201, commentView(created));
    }
    if (one[2] === "comments") return reply(route, 200, { items: found.comments.map(commentView), next_cursor: null });
    if (method === "PATCH") {
      Object.assign(found, { body: (request.postDataJSON() as { body: string }).body, edited_at: NOW });
      return reply(route, 200, view(found));
    }
    if (method === "DELETE") {
      posts.splice(posts.indexOf(found), 1);
      return route.fulfill({ status: 204 });
    }
    return reply(route, 200, view(found));
  });
}
