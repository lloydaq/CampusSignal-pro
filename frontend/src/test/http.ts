import { vi } from "vitest";

export type Route = Record<string, () => Response | Promise<Response>>;

export function json(body: unknown, status = 200, requestId = "req-test"): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json", "X-Request-ID": requestId },
  });
}

export function envelope(status: number, code: string, message: string, details: unknown = null, requestId = "req-env"): Response {
  return json({ error: { code, message, details, request_id: requestId } }, status, requestId);
}

/** Replace global fetch with a path → response table; unknown paths fail the test loudly. */
export function mockFetch(routes: Route) {
  const fetchMock = vi.fn((input: RequestInfo | URL, _init?: RequestInit) => {
    const url = typeof input === "string" ? input : input instanceof URL ? input.pathname : input.url;
    const handler = routes[url];
    if (!handler) throw new Error(`Unexpected fetch: ${url}`);
    return Promise.resolve(handler());
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}
