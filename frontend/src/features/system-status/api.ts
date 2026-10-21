import { ApiError, apiGet, NETWORK_ERROR } from "@/lib/api";

/**
 * Service status from the backend's operational endpoints (architecture.md §16):
 * `/healthz` (process up) and `/readyz` (database reachable and migrated, else 503
 * `not_ready` with `details.database` or `details.migrations`).
 */

export type ApiState = "running" | "unreachable";
export type DatabaseState = "ready" | "migrations_pending" | "unreachable" | "unknown";

export interface ServiceStatus {
  api: ApiState;
  database: DatabaseState;
}

export const serviceStatusQueryKey = ["system", "service-status"] as const;

function isUnreachable(error: unknown): boolean {
  return error instanceof ApiError && error.code === NETWORK_ERROR;
}

async function fetchDatabaseState(signal?: AbortSignal): Promise<DatabaseState> {
  try {
    await apiGet<{ status: string }>("/readyz", signal);
    return "ready";
  } catch (error) {
    if (error instanceof ApiError && error.status === 503 && error.code === "not_ready") {
      const details = (error.details ?? {}) as Record<string, unknown>;
      if (details.migrations === "pending") return "migrations_pending";
      if (details.database === "unreachable") return "unreachable";
    }
    throw error;
  }
}

/** Expected outages become states; anything else is an error for the UI's error state. */
export async function fetchServiceStatus(signal?: AbortSignal): Promise<ServiceStatus> {
  try {
    await apiGet<{ status: string }>("/healthz", signal);
  } catch (error) {
    if (isUnreachable(error)) return { api: "unreachable", database: "unknown" };
    throw error;
  }
  return { api: "running", database: await fetchDatabaseState(signal) };
}
