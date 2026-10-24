import { Navigate, NavLink, Outlet } from "react-router";

import { landingPath } from "@/features/auth/landing";
import { useMe } from "@/features/auth/session";
import { cn } from "@/lib/utils";

const TABS = [
  { to: "colleges", label: "Colleges" },
  { to: "users", label: "Users" },
  { to: "audit", label: "Audit log" },
];

/** Platform administration (Design.md §5 screen 18): colleges as tenants and accounts, never college content. */
export function PlatformLayout() {
  const me = useMe();
  if (!me.capabilities.includes("platform")) return <Navigate to={landingPath(me)} replace />;
  return (
    <div className="space-y-6">
      <div className="space-y-1">
        <p className="text-sm font-medium tracking-wide text-muted uppercase">Platform</p>
        <h1 className="text-2xl font-semibold text-fg sm:text-3xl">Platform administration</h1>
      </div>
      <nav aria-label="Platform" className="-mx-4 overflow-x-auto border-b border-border px-4 sm:mx-0 sm:px-0">
        <ul className="flex gap-1">
          {TABS.map((tab) => (
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
