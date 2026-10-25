import { vi } from "vitest";

/** Keyed by "METHOD /path" or just "/path" (any method). Handlers see the request init. */
export type Route = Record<string, (init?: RequestInit) => Response | Promise<Response>>;

export function json(body: unknown, status = 200, requestId = "req-test", headers: Record<string, string> = {}): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json", "X-Request-ID": requestId, ...headers },
  });
}

export function envelope(
  status: number,
  code: string,
  message: string,
  details: unknown = null,
  requestId = "req-env",
  headers: Record<string, string> = {},
): Response {
  return json({ error: { code, message, details, request_id: requestId } }, status, requestId, headers);
}

export function noContent(): Response {
  return new Response(null, { status: 204 });
}

/** Every signed-in screen polls the unread count (the shell's bell); tests may override it. */
const SHELL_ROUTES: Route = { "/api/v1/me/notifications/unread-count": () => json({ unread: 0 }) };

/** Replace global fetch with a route table; unknown requests fail the test loudly. */
export function mockFetch(overrides: Route) {
  const routes: Route = { ...SHELL_ROUTES, ...overrides };
  const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === "string" ? input : input instanceof URL ? input.pathname : input.url;
    const method = (init?.method ?? "GET").toUpperCase();
    const handler = routes[`${method} ${url}`] ?? routes[url];
    if (!handler) throw new Error(`Unexpected fetch: ${method} ${url}`);
    return Promise.resolve(handler(init));
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

/** The JSON body of the n-th call to `path` (any method). */
export function sentBody(fetchMock: ReturnType<typeof mockFetch>, path: string, index = 0): unknown {
  const call = fetchMock.mock.calls.filter(([input]) => input === path)[index];
  const body = call?.[1]?.body;
  return typeof body === "string" ? (JSON.parse(body) as unknown) : undefined;
}

/** Requests to `path` (any method), as [method, headers] pairs. */
export function requestsTo(fetchMock: ReturnType<typeof mockFetch>, path: string): { method: string; headers: Headers }[] {
  return fetchMock.mock.calls
    .filter(([input]) => input === path)
    .map(([, init]) => ({ method: (init?.method ?? "GET").toUpperCase(), headers: new Headers(init?.headers) }));
}
