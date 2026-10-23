import { envelope, json, mockFetch, noContent, sentBody } from "@/test/http";

import { ApiError, apiGet, apiPost, fieldErrors, NETWORK_ERROR } from "./api";

async function caught(promise: Promise<unknown>): Promise<ApiError> {
  try {
    await promise;
  } catch (error) {
    if (error instanceof ApiError) return error;
    throw error;
  }
  throw new Error("expected an ApiError");
}

describe("apiGet", () => {
  it("returns parsed JSON and sends same-origin credentials with an Accept header", async () => {
    const fetchMock = mockFetch({ "/healthz": () => json({ status: "ok" }) });
    await expect(apiGet("/healthz")).resolves.toEqual({ status: "ok" });
    const init = fetchMock.mock.calls[0]?.[1];
    expect(init?.credentials).toBe("same-origin");
    expect(new Headers(init?.headers).get("Accept")).toBe("application/json");
  });

  it("turns the error envelope into an ApiError with code, details and request ID", async () => {
    mockFetch({
      "/readyz": () => envelope(503, "not_ready", "The service is not ready.", { database: "unreachable" }, "abc123"),
    });
    const error = await caught(apiGet("/readyz"));
    expect(error).toMatchObject({
      status: 503,
      code: "not_ready",
      message: "The service is not ready.",
      details: { database: "unreachable" },
      requestId: "abc123",
    });
  });

  it("uses the X-Request-ID header when the envelope has no request ID", async () => {
    mockFetch({
      "/x": () =>
        json({ error: { code: "not_found", message: "Not found.", details: null, request_id: null } }, 404, "from-header"),
    });
    expect((await caught(apiGet("/x"))).requestId).toBe("from-header");
  });

  it("never surfaces a non-envelope error body", async () => {
    mockFetch({
      "/x": () => new Response("<html>Traceback: secret internals</html>", { status: 502, headers: { "X-Request-ID": "r1" } }),
    });
    const error = await caught(apiGet("/x"));
    expect(error.code).toBe("unexpected_response");
    expect(error.status).toBe(502);
    expect(error.message).not.toContain("Traceback");
    expect(error.requestId).toBe("r1");
  });

  it("rejects a successful response that is not JSON", async () => {
    mockFetch({ "/x": () => new Response("ok", { status: 200 }) });
    expect((await caught(apiGet("/x"))).code).toBe("unexpected_response");
  });

  it("reports network failures as network_error with status 0", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.reject(new TypeError("Failed to fetch"))));
    const error = await caught(apiGet("/healthz"));
    expect(error).toMatchObject({ status: 0, code: NETWORK_ERROR, requestId: null });
  });

  it("lets aborts propagate instead of reporting them as network errors", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.reject(new DOMException("aborted", "AbortError"))));
    await expect(apiGet("/healthz")).rejects.toMatchObject({ name: "AbortError" });
  });
});

describe("state-changing requests", () => {
  afterEach(() => {
    document.cookie = "cs_csrf=; max-age=0; path=/";
  });

  it("send the CSRF cookie as X-CSRF-Token on POST but never on GET", async () => {
    document.cookie = "cs_csrf=tok%2Fen; path=/";
    const fetchMock = mockFetch({ "POST /api/v1/x": () => json({ ok: true }), "/healthz": () => json({ status: "ok" }) });
    await apiPost("/api/v1/x", { a: 1 });
    await apiGet("/healthz");
    const [post, get] = fetchMock.mock.calls.map(([, init]) => new Headers(init?.headers));
    expect(post?.get("X-CSRF-Token")).toBe("tok/en");
    expect(post?.get("Content-Type")).toBe("application/json");
    expect(get?.has("X-CSRF-Token")).toBe(false);
    expect(sentBody(fetchMock, "/api/v1/x")).toEqual({ a: 1 });
  });

  it("refresh a stale CSRF token once and retry", async () => {
    let attempts = 0;
    const fetchMock = mockFetch({
      "POST /api/v1/x": () => (++attempts === 1 ? envelope(403, "csrf_failed", "Reload the page and try again.") : json({ ok: true })),
      "GET /api/v1/auth/csrf": () => json({ csrf_token: "fresh" }),
    });
    await expect(apiPost("/api/v1/x")).resolves.toEqual({ ok: true });
    expect(fetchMock.mock.calls.map(([url, init]) => `${init?.method} ${url as string}`)).toEqual([
      "POST /api/v1/x",
      "GET /api/v1/auth/csrf",
      "POST /api/v1/x",
    ]);
  });

  it("give up after one CSRF retry", async () => {
    const fetchMock = mockFetch({
      "POST /api/v1/x": () => envelope(403, "csrf_failed", "Reload the page and try again."),
      "GET /api/v1/auth/csrf": () => json({ csrf_token: null }),
    });
    await expect(caught(apiPost("/api/v1/x"))).resolves.toMatchObject({ status: 403, code: "csrf_failed" });
    expect(fetchMock).toHaveBeenCalledTimes(3);
  });

  it("don't retry other 403s", async () => {
    const fetchMock = mockFetch({ "POST /api/v1/x": () => envelope(403, "forbidden", "You don't have access to this.") });
    await expect(caught(apiPost("/api/v1/x"))).resolves.toMatchObject({ code: "forbidden" });
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("resolve 204 responses to undefined", async () => {
    mockFetch({ "POST /api/v1/auth/logout": () => noContent() });
    await expect(apiPost("/api/v1/auth/logout")).resolves.toBeUndefined();
  });

  it("expose Retry-After on 429s and field details", async () => {
    mockFetch({
      "POST /api/v1/x": () =>
        envelope(429, "rate_limited", "Too many requests. Try again later.", null, "r", { "Retry-After": "120" }),
      "POST /api/v1/y": () =>
        envelope(422, "validation_error", "Some fields are invalid.", [
          { field: "password", message: "Use at least 10 characters." },
          { field: "password", message: "second message is ignored" },
          { nonsense: true },
        ]),
    });
    await expect(caught(apiPost("/api/v1/x"))).resolves.toMatchObject({ status: 429, retryAfterSeconds: 120 });
    expect(fieldErrors(await caught(apiPost("/api/v1/y")))).toEqual({ password: "Use at least 10 characters." });
    expect(fieldErrors(new Error("plain"))).toEqual({});
  });
});
