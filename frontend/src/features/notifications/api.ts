import { useQuery } from "@tanstack/react-query";

import type { Page } from "@/features/admin/api";
import { apiGet, apiPost } from "@/lib/api";

/** The signed-in user's notifications (backend app/api/v1/notifications.py; architecture.md §15). */

const BASE = "/api/v1/me/notifications";

/** References and non-sensitive titles only (NOTIF-004): the subject is a type and an id. */
export interface Notification {
  id: string;
  type: string;
  title: string;
  subject_type: string;
  subject_id: string;
  read: boolean;
  created_at: string;
}

export const notificationKeys = {
  all: ["me", "notifications"] as const,
  list: ["me", "notifications", "list"] as const,
  unread: ["me", "notifications", "unread-count"] as const,
};

export const fetchNotifications = (cursor: string | null, signal?: AbortSignal) =>
  apiGet<Page<Notification>>(`${BASE}${cursor ? `?cursor=${encodeURIComponent(cursor)}` : ""}`, signal);

export const markRead = (id: string) => apiPost<Notification>(`${BASE}/${id}/read`);

export const markAllRead = () => apiPost<{ marked: number }>(`${BASE}/read-all`);

export const POLL_MS = 60_000;

/**
 * The unread count (NOTIF-005): refetched every 60 s while the tab is visible (TanStack Query
 * pauses intervals in background tabs) and, never being fresh, whenever the window regains focus.
 */
export function useUnreadCount(): number {
  const { data } = useQuery({
    queryKey: notificationKeys.unread,
    queryFn: ({ signal }) => apiGet<{ unread: number }>(`${BASE}/unread-count`, signal),
    staleTime: 0,
    refetchInterval: POLL_MS,
  });
  return data?.unread ?? 0;
}

/** Where a notification leads; unknown subjects (later phases) lead nowhere. */
export function notificationHref(n: Notification): string | null {
  if (n.subject_type === "NOTICE") return `/notices/${n.subject_id}`;
  if (n.subject_type === "ISSUE") return `/issues/${n.subject_id}`;
  // A join decision: /home for the new member, or /join (via the landing redirect) after a rejection.
  if (n.subject_type === "MEMBERSHIP") return "/home";
  return null;
}
