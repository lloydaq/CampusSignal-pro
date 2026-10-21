import { QueryClient } from "@tanstack/react-query";

import { ApiError } from "@/lib/api";

const MAX_RETRIES = 2;

/** GET queries retry twice with backoff, except client errors, which won't change (Design.md §7). */
export function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 30_000,
        retry: (failureCount, error) =>
          failureCount < MAX_RETRIES && !(error instanceof ApiError && error.status >= 400 && error.status < 500),
      },
      mutations: { retry: false },
    },
  });
}
