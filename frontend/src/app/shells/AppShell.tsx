import { NavLink, Outlet, useMatches } from "react-router";

import { Wordmark } from "@/components/Wordmark";
import type { Me } from "@/features/auth/api";
import { useMe } from "@/features/auth/session";
import { cn } from "@/lib/utils";

import { navItems } from "./nav";

function CollegeName({ me, className }: { me: Me; className?: string }) {
  const college = me.membership?.status === "ACTIVE" ? me.membership.college : null;
  if (!college) return null;
  return <p className={cn("truncate text-sm text-muted", className)}>{college.name}</p>;
}

/**
 * Signed-in layout (Design.md §4). Desktop (lg+): a one-level navigation rail with the wordmark
 * and college name. Mobile: a top bar and a bottom tab bar. The current item uses primary text
 * on primary-subtle with a 3 px accent marker on its leading edge.
 */
export function AppShell() {
  const me = useMe();
  const items = navItems(me);
  // Tables (Manage) use the content width; reading screens keep the reading measure.
  const wide = useMatches().some((match) => (match.handle as { wide?: boolean } | undefined)?.wide);
  return (
    <div className="min-h-dvh lg:flex">
      <aside className="hidden shrink-0 border-r border-border bg-surface lg:flex lg:w-rail lg:flex-col">
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
      </aside>

      <header className="flex items-center justify-between gap-4 border-b border-border bg-surface px-4 py-3 lg:hidden">
        <Wordmark />
        <CollegeName me={me} className="max-w-1/2 text-right" />
      </header>

      <main className="flex-1 px-4 pt-8 pb-28 sm:px-6 lg:px-10 lg:pt-10 lg:pb-12">
        <div className={cn("mx-auto", wide ? "max-w-content" : "max-w-reading")}>
          <Outlet />
        </div>
      </main>

      <nav aria-label="Main" className="fixed inset-x-0 bottom-0 border-t border-border bg-surface lg:hidden">
        <ul className="mx-auto flex max-w-reading">
          {items.map(({ to, label, Icon }) => (
            <li key={to} className="flex-1">
              <NavLink
                to={to}
                className={({ isActive }) =>
                  cn(
                    "relative flex min-h-14 flex-col items-center justify-center gap-1 px-2 text-xs font-medium",
                    isActive
                      ? "text-primary before:absolute before:inset-x-6 before:top-0 before:h-0.75 before:rounded-sm before:bg-accent"
                      : "text-muted",
                  )
                }
              >
                <Icon aria-hidden="true" strokeWidth={1.5} className="size-5" />
                {label}
              </NavLink>
            </li>
          ))}
        </ul>
      </nav>
    </div>
  );
}
