import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Bell, CheckCheck } from "lucide-react";
import { Link } from "react-router";

import { Callout } from "@/components/Callout";
import { EmptyState } from "@/components/EmptyState";
import { ErrorState } from "@/components/ErrorState";
import { Button } from "@/components/ui/button";
import { ListLoading, LoadMore } from "@/features/admin/list";
import { useCursorList } from "@/features/admin/useCursorList";
import { useMe } from "@/features/auth/session";
import { ApiError } from "@/lib/api";
import { formatDateTime } from "@/lib/datetime";
import { usePageTitle } from "@/lib/usePageTitle";
import { cn } from "@/lib/utils";

import { fetchNotifications, markAllRead, markRead, notificationHref, notificationKeys, useUnreadCount, type Notification } from "./api";

/** NOTIF-001/003: newest first, unread rows marked, opening one marks it read, or all at once. */
export function NotificationsPage() {
  usePageTitle("Notifications");
  const me = useMe();
  // A rejection has no college, so someone without one sees times in their own zone.
  const timeZone = me.membership?.status === "ACTIVE" ? me.membership.college.timezone : Intl.DateTimeFormat().resolvedOptions().timeZone;
  const unread = useUnreadCount();
  const queryClient = useQueryClient();
  const { query, items } = useCursorList(notificationKeys.list, fetchNotifications);
  const refresh = () => queryClient.invalidateQueries({ queryKey: notificationKeys.all });
  const readOne = useMutation({ mutationFn: markRead, onSettled: refresh });
  const readAll = useMutation({ mutationFn: markAllRead, onSettled: refresh });

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-semibold text-fg sm:text-3xl">Notifications</h1>
        {unread > 0 && (
          <Button variant="secondary" size="sm" onClick={() => readAll.mutate()} disabled={readAll.isPending}>
            <CheckCheck aria-hidden="true" strokeWidth={1.5} />
            {readAll.isPending ? "Marking…" : "Mark all as read"}
          </Button>
        )}
      </div>

      {readAll.isError && (
        <Callout tone="danger" title="Couldn't mark notifications as read.">
          {readAll.error instanceof ApiError ? readAll.error.message : "Something went wrong."} Try again.
        </Callout>
      )}

      {query.isPending ? (
        <ListLoading label="Loading notifications" />
      ) : query.isError ? (
        <ErrorState title="Couldn't load notifications." error={query.error} onRetry={() => void query.refetch()} retrying={query.isFetching} />
      ) : items.length === 0 ? (
        <EmptyState Icon={Bell} title="No notifications.">
          Urgent and important notices, and decisions about your requests, show up here.
        </EmptyState>
      ) : (
        <div className="space-y-6">
          <ul aria-label="Notifications" className="overflow-hidden rounded-sm border border-border bg-surface">
            {items.map((n) => (
              <NotificationRow key={n.id} notification={n} timeZone={timeZone} onOpen={() => !n.read && readOne.mutate(n.id)} />
            ))}
          </ul>
          <LoadMore shown={items.length} hasMore={query.hasNextPage} loading={query.isFetchingNextPage} onLoad={() => void query.fetchNextPage()} />
        </div>
      )}
    </div>
  );
}

function NotificationRow({ notification: n, timeZone, onOpen }: { notification: Notification; timeZone: string; onOpen: () => void }) {
  const href = notificationHref(n);
  const content = (
    <>
      <span aria-hidden="true" className={cn("mt-1.5 size-2 shrink-0 rounded-full", n.read ? "bg-transparent" : "bg-accent")} />
      <span className="min-w-0 space-y-1">
        <span className={cn("block text-sm text-fg", !n.read && "font-semibold")}>
          {!n.read && <span className="sr-only">Unread: </span>}
          {n.title}
        </span>
        <time dateTime={n.created_at} className="block text-xs text-subtle">
          {formatDateTime(n.created_at, timeZone)}
        </time>
      </span>
    </>
  );
  const box = cn("flex gap-3 px-4 py-3", !n.read && "bg-accent-subtle");
  return (
    <li className="border-b border-border last:border-b-0">
      {href ? (
        <Link to={href} onClick={onOpen} className={cn(box, "hover:bg-surface-sunken focus-visible:bg-surface-sunken")}>
          {content}
        </Link>
      ) : (
        <div className={box}>{content}</div>
      )}
    </li>
  );
}
