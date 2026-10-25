import { Bell } from "lucide-react";
import { NavLink } from "react-router";

import { cn } from "@/lib/utils";

import { useUnreadCount } from "./api";

function label(unread: number): string {
  return unread === 0 ? "Notifications" : `Notifications, ${unread} unread`;
}

/** The count as a signal pill (Design.md §6 NavItem); 99+ keeps it narrow. */
function UnreadPill({ unread, className }: { unread: number; className?: string }) {
  if (unread === 0) return null;
  return (
    <span aria-hidden="true" className={cn("inline-flex min-w-5 justify-center rounded-full bg-accent-subtle px-1.5 text-xs leading-5 font-semibold text-accent-fg tabular-nums", className)}>
      {unread > 99 ? "99+" : unread}
    </span>
  );
}

/** Desktop: the bell at the foot of the navigation rail, styled as a rail item (Design.md §4). */
export function RailNotificationBell() {
  const unread = useUnreadCount();
  return (
    <NavLink
      to="/notifications"
      className={({ isActive }) =>
        cn(
          "relative flex h-10 items-center gap-3 rounded-sm px-3 text-sm font-medium transition-colors",
          isActive
            ? "bg-primary-subtle text-primary before:absolute before:inset-y-1.5 before:left-0 before:w-0.75 before:rounded-sm before:bg-accent"
            : "text-muted hover:bg-surface-sunken hover:text-fg",
        )
      }
    >
      <Bell aria-hidden="true" strokeWidth={1.5} className="size-5 shrink-0" />
      Notifications
      {/* Visible text starts the accessible name (WCAG 2.5.3); the pill itself is hidden. */}
      {unread > 0 && <span className="sr-only">, {unread} unread</span>}
      <UnreadPill unread={unread} className="ml-auto" />
    </NavLink>
  );
}

/** Mobile: an icon button in the top bar with the count over its corner. */
export function TopBarNotificationBell() {
  const unread = useUnreadCount();
  return (
    <NavLink
      to="/notifications"
      aria-label={label(unread)}
      className={({ isActive }) =>
        cn("relative inline-flex size-11 shrink-0 items-center justify-center rounded-sm hover:bg-surface-sunken", isActive ? "text-primary" : "text-muted")
      }
    >
      <Bell aria-hidden="true" strokeWidth={1.5} className="size-5" />
      <UnreadPill unread={unread} className="absolute top-0.5 right-0" />
    </NavLink>
  );
}
