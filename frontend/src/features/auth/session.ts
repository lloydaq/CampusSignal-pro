import { useQuery, useQueryClient, type QueryClient } from "@tanstack/react-query";
import { createContext, useContext } from "react";

import { ApiError } from "@/lib/api";

import { fetchMe, type Me } from "./api";

/** The signed-in user's /me (user, membership, roles, capabilities), or null when signed out. */
export const sessionQueryKey = ["auth", "session"] as const;

/**
 * Set when a session ends while someone was signed in (any 401), naming who it was. Signed-in
 * screens then show the "Your session ended" dialog over the current page, so unsaved input
 * survives (Design.md §7). Signing out on purpose never sets it.
 */
export const sessionEndedKey = ["auth", "session-ended"] as const;

export interface SessionEnded {
  /** The /me that was signed in: the page underneath keeps rendering with it. */
  me: Me;
}

export const NOT_AUTHENTICATED = "not_authenticated";

export function isSignedOutError(error: unknown): boolean {
  return error instanceof ApiError && error.status === 401 && error.code === NOT_AUTHENTICATED;
}

/** A request answered 401: the session is gone. Remember who was signed in, then clear it. */
export function markSessionEnded(client: QueryClient): void {
  const previous = client.getQueryData<Me | null>(sessionQueryKey);
  if (previous) client.setQueryData(sessionEndedKey, { me: previous } satisfies SessionEnded);
  client.setQueryData(sessionQueryKey, null);
}

export function clearSessionEnded(client: QueryClient): void {
  client.setQueryData(sessionEndedKey, null);
}

async function fetchSession(client: QueryClient, signal?: AbortSignal): Promise<Me | null> {
  try {
    return await fetchMe(signal);
  } catch (error) {
    if (!isSignedOutError(error)) throw error;
    const previous = client.getQueryData<Me | null>(sessionQueryKey);
    if (previous) client.setQueryData(sessionEndedKey, { me: previous } satisfies SessionEnded);
    return null;
  }
}

export function useSession() {
  const client = useQueryClient();
  return useQuery({ queryKey: sessionQueryKey, queryFn: ({ signal }) => fetchSession(client, signal) });
}

/**
 * The signed-in /me for screens inside RequireAuth. While the "session ended" dialog is open it
 * is the last known /me, so the page underneath (and its unsaved input) stays as it was.
 */
export const MeContext = createContext<Me | null>(null);

export function useMe(): Me {
  const me = useContext(MeContext);
  if (!me) throw new Error("useMe outside a signed-in route");
  return me;
}

export function useSessionEnded(): SessionEnded | null {
  return (
    useQuery({
      queryKey: sessionEndedKey,
      queryFn: () => null,
      initialData: null as SessionEnded | null,
      staleTime: Infinity,
      enabled: false,
    }).data ?? null
  );
}

/**
 * After signing in: load the full /me (sign-in returns only the user) before moving on. The
 * "session ended" marker is cleared only once /me is back; clearing it first would leave a
 * moment with neither a session nor the dialog, and the page would redirect away.
 */
export async function refreshSession(client: QueryClient): Promise<Me | null> {
  const me = await client.fetchQuery({
    queryKey: sessionQueryKey,
    queryFn: ({ signal }) => fetchSession(client, signal),
    staleTime: 0,
  });
  clearSessionEnded(client);
  return me;
}
