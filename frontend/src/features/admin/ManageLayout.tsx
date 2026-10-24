import type { ReactNode } from "react";
import { Navigate, NavLink, Outlet } from "react-router";

import type { Capability } from "@/features/auth/api";
import { landingPath } from "@/features/auth/landing";
import { useMe } from "@/features/auth/session";
import { cn } from "@/lib/utils";

import { MANAGE_TABS } from "./tabs";

/** Hides what the account can't use; the backend enforces it (Rules §2). */
export function ManageLayout() {
  const me = useMe();
  if (!me.capabilities.includes("review_memberships")) return <Navigate to={landingPath(me)} replace />;
  const tabs = MANAGE_TABS.filter((tab) => me.capabilities.includes(tab.needs));
  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold text-fg sm:text-3xl">Manage</h1>
      <nav aria-label="Manage" className="-mx-4 overflow-x-auto border-b border-border px-4 sm:mx-0 sm:px-0">
        <ul className="flex gap-1">
          {tabs.map((tab) => (
            <li key={tab.to}>
              <NavLink
                to={tab.to}
                className={({ isActive }) =>
                  cn(
                    "relative flex h-10 items-center px-3 text-sm font-medium whitespace-nowrap pointer-coarse:min-h-11",
                    isActive
                      ? "text-primary after:absolute after:inset-x-2 after:bottom-0 after:h-0.75 after:rounded-sm after:bg-accent"
                      : "text-muted hover:text-fg",
                  )
                }
              >
                {tab.label}
              </NavLink>
            </li>
          ))}
        </ul>
      </nav>
      <Outlet />
    </div>
  );
}

/** Guards a tab route for direct visits (e.g. a department admin opening /manage/roster). */
export function RequireCapability({ needs, children }: { needs: Capability; children: ReactNode }) {
  const me = useMe();
  if (!me.capabilities.includes(needs)) return <Navigate to="/manage/requests" replace />;
  return children;
}
