import { Ellipsis } from "lucide-react";
import { useEffect, useId, useState } from "react";
import { NavLink, Outlet, useLocation, useMatches } from "react-router";

import { Wordmark } from "@/components/Wordmark";
import type { Me } from "@/features/auth/api";
import { useMe } from "@/features/auth/session";
import { RailNotificationBell, TopBarNotificationBell } from "@/features/notifications/NotificationBell";
import { cn } from "@/lib/utils";

import { navItems, splitForBar, type NavItem } from "./nav";
import { RouteSuspense } from "@/app/lazy";
import { useTypingFlag } from "@/lib/useTypingFlag";

function CollegeName({ me, className }: { me: Me; className?: string }) {
  const college = me.membership?.status === "ACTIVE" ? me.membership.college : null;
  if (!college) return null;
  return <p className={cn("truncate text-sm text-muted", className)}>{college.name}</p>;
}

/**
 * Signed-in layout (Design.md §4). Desktop (lg+): a one-level navigation rail with the wordmark
 * and college name, notifications at its foot. Mobile: a top bar with the notifications bell and a
 * bottom tab bar. The current item uses primary text
 * on primary-subtle with a 3 px accent marker on its leading edge.
 */
export function AppShell() {
  const me = useMe();
  const items = navItems(me);
  // Tables (Manage) use the content width; reading screens keep the reading measure.
  const wide = useMatches().some((match) => (match.handle as { wide?: boolean } | undefined)?.wide);
  return (
    <div className="min-h-dvh lg:flex">
      <aside className="hidden shrink-0 border-r border-border bg-surface lg:sticky lg:top-0 lg:flex lg:h-dvh lg:w-rail lg:flex-col">
        <div className="space-y-1 px-5 pt-6 pb-8">
          <Wordmark />
          <CollegeName me={me} />
        </div>
        <nav aria-label="Main" className="px-3">
          <ul className="space-y-1">
            {items.map(({ to, label, Icon }) => (
              <li key={to}>
                <NavLink
                  to={to}
                  className={({ isActive }) =>
                    cn(
                      "relative flex h-10 items-center gap-3 rounded-sm px-3 text-sm font-medium transition-colors",
                      isActive
                        ? "bg-primary-subtle text-primary before:absolute before:inset-y-1.5 before:left-0 before:w-0.75 before:rounded-sm before:bg-accent"
                        : "text-muted hover:bg-surface-sunken hover:text-fg",
                    )
                  }
                >
                  <Icon aria-hidden="true" strokeWidth={1.5} className="size-5 shrink-0" />
                  {label}
                </NavLink>
              </li>
            ))}
          </ul>
        </nav>
        <div className="mt-auto border-t border-border px-3 py-3">
          <RailNotificationBell />
        </div>
      </aside>

      <header className="flex items-center justify-between gap-4 border-b border-border bg-surface px-4 py-1.5 lg:hidden">
        <Wordmark />
        <div className="flex min-w-0 items-center gap-2">
          <CollegeName me={me} className="text-right" />
          <TopBarNotificationBell />
        </div>
      </header>

      <main className="flex-1 px-4 pt-8 pb-28 sm:px-6 lg:px-10 lg:pt-10 lg:pb-12">
        <div className={cn("mx-auto", wide ? "max-w-content" : "max-w-reading")}>
          <RouteSuspense>
            <Outlet />
          </RouteSuspense>
        </div>
      </main>

      <BottomBar items={items} />
    </div>
  );
}

const BAR_ITEM = "relative flex min-h-14 w-full flex-col items-center justify-center gap-1 px-2 text-xs font-medium";
const BAR_ACTIVE = "text-primary before:absolute before:inset-x-6 before:top-0 before:h-0.75 before:rounded-sm before:bg-accent";

/**
 * Phones (Design.md §4): four sections in the bar and a "More" sheet for the rest when there
 * are more than five. The sheet closes when a link is chosen, on Escape or on a tap outside it.
 */
function BottomBar({ items }: { items: NavItem[] }) {
  useTypingFlag();
  const { bar, more } = splitForBar(items);
  const location = useLocation();
  const [open, setOpen] = useState(false);
  const sheetId = useId();
  const inMore = more.some((item) => location.pathname.startsWith(item.to));
  useEffect(() => {
    if (!open) return;
    const close = (event: KeyboardEvent) => event.key === "Escape" && setOpen(false);
    document.addEventListener("keydown", close);
    return () => document.removeEventListener("keydown", close);
  }, [open]);
  return (
    <nav aria-label="Main" className="fixed inset-x-0 bottom-0 typing:hidden lg:hidden">
      {open && (
        <>
          {/* The scrim sits behind the sheet and the bar (it paints over the page only). */}
          <button type="button" aria-label="Close menu" tabIndex={-1} className="fixed inset-0 -z-10 cursor-default bg-fg/20" onClick={() => setOpen(false)} />
          <div className="border-t border-border bg-surface">
            <ul id={sheetId} className="mx-auto max-w-reading py-2">
              {more.map(({ to, label, Icon }) => (
                <li key={to}>
                  <NavLink
                    to={to}
                    onClick={() => setOpen(false)}
                    className={({ isActive }) => cn("flex min-h-12 items-center gap-3 px-6 text-sm font-medium", isActive ? "text-primary" : "text-fg")}
                  >
                    <Icon aria-hidden="true" strokeWidth={1.5} className="size-5" />
                    {label}
                  </NavLink>
                </li>
              ))}
            </ul>
          </div>
        </>
      )}
      <div className="border-t border-border bg-surface">
        <ul className="mx-auto flex max-w-reading">
          {bar.map(({ to, label, Icon }) => (
            <li key={to} className="flex-1">
              <NavLink to={to} onClick={() => setOpen(false)} className={({ isActive }) => cn(BAR_ITEM, isActive ? BAR_ACTIVE : "text-muted")}>
                <Icon aria-hidden="true" strokeWidth={1.5} className="size-5" />
                {label}
              </NavLink>
            </li>
          ))}
          {more.length > 0 && (
            <li className="flex-1">
              <button type="button" aria-expanded={open} aria-controls={sheetId} onClick={() => setOpen((o) => !o)} className={cn(BAR_ITEM, inMore ? BAR_ACTIVE : "text-muted")}>
                <Ellipsis aria-hidden="true" strokeWidth={1.5} className="size-5" />
                More
              </button>
            </li>
          )}
        </ul>
      </div>
    </nav>
  );
}
