import { CalendarOff, FlaskConical } from "lucide-react";
import type { ReactNode } from "react";
import { Navigate, NavLink, Outlet } from "react-router";

import { EmptyState } from "@/components/EmptyState";
import { landingPath } from "@/features/auth/landing";
import { useMe } from "@/features/auth/session";
import { cn } from "@/lib/utils";

import type { TermRef } from "./api";
import { RouteSuspense } from "@/app/lazy";

const TABS = [
  { to: "timetable", label: "Timetable" },
  { to: "attendance", label: "Attendance" },
  { to: "results", label: "Results" },
];

/** Design.md §5 screen 4: Timetable · Attendance · Results, for students only (PRD §11). */
export function AcademicsLayout() {
  const me = useMe();
  if (!me.capabilities.includes("academics")) return <Navigate to={landingPath(me)} replace />;
  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold text-fg sm:text-3xl">Academics</h1>
      <nav aria-label="Academics" className="-mx-4 overflow-x-auto border-b border-border px-4 sm:mx-0 sm:px-0">
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
      <RouteSuspense>
        <Outlet />
      </RouteSuspense>
    </div>
  );
}

/** The term the figures belong to, and the "Demo data" label for synthetic colleges. */
export function TermLine({ term, isDemo, children }: { term: TermRef; isDemo: boolean; children?: ReactNode }) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-2">
      <p className="text-sm text-muted">
        <span className="font-medium text-fg">{term.name}</span>
        {children}
      </p>
      {isDemo && <DemoBadge />}
    </div>
  );
}

export function DemoBadge() {
  return (
    <span className="inline-flex items-center gap-1.5 rounded-sm border border-warning bg-warning-subtle px-2 py-0.5 text-xs font-medium text-warning-fg">
      <FlaskConical aria-hidden="true" strokeWidth={1.5} className="size-3.5" />
      Demo data
    </span>
  );
}

/** Design.md §5 screen 4: no current term. */
export function NoTerm() {
  return <EmptyState Icon={CalendarOff} title="Your college hasn't set up the current term yet." />;
}
