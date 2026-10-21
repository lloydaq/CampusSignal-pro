/**
 * Typed fetch wrapper for the CampusSignal API (architecture.md §6, error envelope §12).
 *
 * Requests use relative URLs (same origin; the dev server proxies to uvicorn) and send
 * cookies with `credentials: "same-origin"`. Every failure becomes an `ApiError` carrying
 * the server's error code and request ID; raw response bodies are never surfaced.
 * CSRF headers for state-changing requests arrive with sessions in Phase 2.
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

  constructor(status: number, code: string, message: string, details: unknown, requestId: string | null) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.details = details;
    this.requestId = requestId;
  }
}

export const NETWORK_ERROR = "network_error";
const UNEXPECTED_RESPONSE = "unexpected_response";

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

export async function apiRequest<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (!headers.has("Accept")) headers.set("Accept", "application/json");

  let response: Response;
  try {
    response = await fetch(path, { ...init, credentials: "same-origin", headers });
  } catch (cause) {
    if (cause instanceof DOMException && cause.name === "AbortError") throw cause;
    throw new ApiError(0, NETWORK_ERROR, "Can't reach the server. Check your connection.", null, null);
  }

  const headerRequestId = response.headers.get("X-Request-ID");
  const body = await readJson(response);

  if (!response.ok) {
    if (isErrorEnvelope(body)) {
      const { code, message, details, request_id } = body.error;
      throw new ApiError(response.status, code, message, details, request_id ?? headerRequestId);
    }
    throw new ApiError(
      response.status,
      UNEXPECTED_RESPONSE,
      "The server returned an unexpected response.",
      null,
      headerRequestId,
    );
  }

  if (body === undefined) {
    throw new ApiError(response.status, UNEXPECTED_RESPONSE, "The server returned an unexpected response.", null, headerRequestId);
  }
  return body as T;
}

export function apiGet<T>(path: string, signal?: AbortSignal): Promise<T> {
  return apiRequest<T>(path, signal ? { method: "GET", signal } : { method: "GET" });
}
