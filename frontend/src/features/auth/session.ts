import { useQuery } from "@tanstack/react-query";

import { ApiError } from "@/lib/api";

import { fetchMe, type User } from "./api";

/** The signed-in user, or null when signed out. Cleared on any 401 (see queryClient.ts). */
export const sessionQueryKey = ["auth", "session"] as const;

export const NOT_AUTHENTICATED = "not_authenticated";

export function isSignedOutError(error: unknown): boolean {
  return error instanceof ApiError && error.status === 401 && error.code === NOT_AUTHENTICATED;
}

async function fetchSession(signal?: AbortSignal): Promise<User | null> {
  try {
    return (await fetchMe(signal)).user;
  } catch (error) {
    if (isSignedOutError(error)) return null;
    throw error;
  }
}

export function useSession() {
  return useQuery({ queryKey: sessionQueryKey, queryFn: ({ signal }) => fetchSession(signal) });
}
