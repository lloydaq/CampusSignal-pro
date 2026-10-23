import { MutationCache, QueryClient } from "@tanstack/react-query";

import { isSignedOutError, sessionQueryKey } from "@/features/auth/session";
import { ApiError } from "@/lib/api";

const MAX_RETRIES = 2;

/**
 * GET queries retry twice with backoff, except client errors, which won't change (Design.md §7).
 * A 401 from any request means the session ended: the session is cleared, and the signed-in
 * routes send the user to sign in with a return path.
 */
export function createQueryClient(): QueryClient {
  const client: QueryClient = new QueryClient({
    mutationCache: new MutationCache({
      onError: (error) => {
        if (isSignedOutError(error)) client.setQueryData(sessionQueryKey, null);
      },
    }),
    defaultOptions: {
      queries: {
        staleTime: 30_000,
        retry: (failureCount, error) =>
          failureCount < MAX_RETRIES && !(error instanceof ApiError && error.status >= 400 && error.status < 500),
      },
      mutations: { retry: false },
    },
  });
  return client;
}
