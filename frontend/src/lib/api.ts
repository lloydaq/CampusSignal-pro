/**
 * Typed fetch wrapper for the CampusSignal API (architecture.md §6, error envelope §12).
 *
 * Requests use relative URLs (same origin; the dev server proxies to uvicorn) and send
 * cookies with `credentials: "same-origin"`. Every failure becomes an `ApiError` carrying
 * the server's error code and request ID; raw response bodies are never surfaced.
 *
 * State-changing requests echo the `cs_csrf` cookie in `X-CSRF-Token` (double-submit,
 * PRD AUTH-008). If the server rejects the token (`csrf_failed`, e.g. after the session
 * rotated in another tab), the client fetches a fresh one once and retries.
 */

export interface ErrorEnvelope {
  error: {
    code: string;
    message: string;
    details: unknown;
    request_id: string | null;
  };
}

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly details: unknown;
  readonly requestId: string | null;
  /** Seconds from the `Retry-After` header of a 429, else null. */
  readonly retryAfterSeconds: number | null;

  constructor(
    status: number,
    code: string,
    message: string,
    details: unknown,
    requestId: string | null,
    retryAfterSeconds: number | null = null,
  ) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.details = details;
    this.requestId = requestId;
    this.retryAfterSeconds = retryAfterSeconds;
  }
}

export const NETWORK_ERROR = "network_error";
const UNEXPECTED_RESPONSE = "unexpected_response";
const CSRF_FAILED = "csrf_failed";

export const CSRF_COOKIE = "cs_csrf";
export const CSRF_HEADER = "X-CSRF-Token";
const CSRF_REFRESH_PATH = "/api/v1/auth/csrf";
const SAFE_METHODS = new Set(["GET", "HEAD", "OPTIONS"]);

export function readCookie(name: string): string | null {
  for (const part of document.cookie.split(";")) {
    const [key, ...rest] = part.trim().split("=");
    if (key === name) return decodeURIComponent(rest.join("="));
  }
  return null;
}

function parseRetryAfter(value: string | null): number | null {
  if (value === null || !/^\d+$/.test(value.trim())) return null;
  return Number(value.trim());
}

function isErrorEnvelope(body: unknown): body is ErrorEnvelope {
  if (typeof body !== "object" || body === null || !("error" in body)) return false;
  const { error } = body;
  return (
    typeof error === "object" &&
    error !== null &&
    typeof (error as { code?: unknown }).code === "string" &&
    typeof (error as { message?: unknown }).message === "string"
  );
}

async function readJson(response: Response): Promise<unknown> {
  try {
    return (await response.json()) as unknown;
  } catch {
    return undefined;
  }
}

async function send(path: string, init: RequestInit): Promise<Response> {
  const headers = new Headers(init.headers);
  if (!headers.has("Accept")) headers.set("Accept", "application/json");
  const method = (init.method ?? "GET").toUpperCase();
  if (!SAFE_METHODS.has(method)) {
    const csrf = readCookie(CSRF_COOKIE);
    if (csrf) headers.set(CSRF_HEADER, csrf);
  }

  try {
    return await fetch(path, { ...init, credentials: "same-origin", headers });
  } catch (cause) {
    if (cause instanceof DOMException && cause.name === "AbortError") throw cause;
    throw new ApiError(0, NETWORK_ERROR, "Can't reach the server. Check your connection.", null, null);
  }
}

export async function apiRequest<T>(path: string, init: RequestInit = {}): Promise<T> {
  try {
    return await parse<T>(await send(path, init));
  } catch (error) {
    const method = (init.method ?? "GET").toUpperCase();
    if (!(error instanceof ApiError && error.code === CSRF_FAILED) || SAFE_METHODS.has(method)) throw error;
  }
  // The CSRF token was stale: fetching it again re-sets the cookie for the current session.
  await parse<unknown>(await send(CSRF_REFRESH_PATH, { method: "GET" }));
  return parse<T>(await send(path, init));
}

async function parse<T>(response: Response): Promise<T> {
  const headerRequestId = response.headers.get("X-Request-ID");
  const body = await readJson(response);

  if (!response.ok) {
    if (isErrorEnvelope(body)) {
      const { code, message, details, request_id } = body.error;
      const retryAfter = parseRetryAfter(response.headers.get("Retry-After"));
      throw new ApiError(response.status, code, message, details, request_id ?? headerRequestId, retryAfter);
    }
    throw new ApiError(
      response.status,
      UNEXPECTED_RESPONSE,
      "The server returned an unexpected response.",
      null,
      headerRequestId,
    );
  }

  if (response.status === 204) return undefined as T;
  if (body === undefined) {
    throw new ApiError(response.status, UNEXPECTED_RESPONSE, "The server returned an unexpected response.", null, headerRequestId);
  }
  return body as T;
}

export function apiGet<T>(path: string, signal?: AbortSignal): Promise<T> {
  return apiRequest<T>(path, signal ? { method: "GET", signal } : { method: "GET" });
}

export function apiPost<T>(path: string, body?: unknown): Promise<T> {
  const init: RequestInit = { method: "POST" };
  if (body !== undefined) {
    init.body = JSON.stringify(body);
    init.headers = { "Content-Type": "application/json" };
  }
  return apiRequest<T>(path, init);
}

/** Field-level messages from an error's `details` ([{field, message}]), keyed by field. */
export function fieldErrors(error: unknown): Record<string, string> {
  if (!(error instanceof ApiError) || !Array.isArray(error.details)) return {};
  const result: Record<string, string> = {};
  for (const item of error.details as unknown[]) {
    if (typeof item !== "object" || item === null) continue;
    const { field, message } = item as { field?: unknown; message?: unknown };
    if (typeof field === "string" && typeof message === "string" && !(field in result)) result[field] = message;
  }
  return result;
}
