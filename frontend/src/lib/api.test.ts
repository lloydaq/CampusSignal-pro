import { envelope, json, mockFetch } from "@/test/http";

import { ApiError, apiGet, NETWORK_ERROR } from "./api";

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
