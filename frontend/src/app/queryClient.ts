import { MutationCache, QueryCache, QueryClient } from "@tanstack/react-query";

import { isSignedOutError, markSessionEnded } from "@/features/auth/session";
import { ApiError } from "@/lib/api";

const MAX_RETRIES = 2;

/**
 * GET queries retry twice with backoff, except client errors, which won't change (Design.md §7).
 * A 401 from any request means the session ended: it is cleared and marked as ended, and the
 * signed-in screens show the "Your session ended" dialog (or, on a fresh visit, go to sign-in).
 */
export function createQueryClient(): QueryClient {
  const onError = (error: unknown) => {
    if (isSignedOutError(error)) markSessionEnded(client);
  };
  const client: QueryClient = new QueryClient({
    queryCache: new QueryCache({ onError }),
    mutationCache: new MutationCache({ onError }),
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
