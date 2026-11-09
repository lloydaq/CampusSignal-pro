import { useQuery } from "@tanstack/react-query";
import { BookOpen } from "lucide-react";
import { Link, Navigate } from "react-router";

import { EmptyState } from "@/components/EmptyState";
import { ErrorState } from "@/components/ErrorState";
import { ListLoading } from "@/features/admin/list";
import { landingPath } from "@/features/auth/landing";
import { useMe } from "@/features/auth/session";
import { usePageTitle } from "@/lib/usePageTitle";

import { DemoBadge, NoTerm } from "./AcademicsLayout";
import { fetchTeachingSections, teachingKeys } from "./teachingApi";

/** Design.md §5 screen 16: "Which classes need me?" The faculty member's sections this term. */
export function TeachingPage() {
  usePageTitle("Teaching");
  const me = useMe();
  const query = useQuery({ queryKey: teachingKeys.sections, queryFn: ({ signal }) => fetchTeachingSections(signal), enabled: me.capabilities.includes("teaching") });
  if (!me.capabilities.includes("teaching")) return <Navigate to={landingPath(me)} replace />;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-2xl font-semibold text-fg sm:text-3xl">Teaching</h1>
        {me.membership?.college.is_demo && <DemoBadge />}
      </div>
      {query.isPending ? (
        <ListLoading label="Loading your sections" />
      ) : query.isError ? (
        <ErrorState title="Couldn't load your sections." error={query.error} onRetry={() => void query.refetch()} retrying={query.isFetching} />
      ) : !query.data.term ? (
        <NoTerm />
      ) : query.data.items.length === 0 ? (
        <EmptyState Icon={BookOpen} title="You aren't teaching any sections this term.">
          Your department admin assigns faculty to sections.
        </EmptyState>
      ) : (
        <section aria-labelledby="sections-heading" className="space-y-2">
          <h2 id="sections-heading" className="text-sm text-muted">
            <span className="font-medium text-fg">{query.data.term.name}</span> · your sections
          </h2>
          <ul aria-label="Your sections" className="divide-y divide-border rounded-sm border border-border">
            {query.data.items.map((s) => (
              <li key={s.id}>
                <Link to={`/teaching/sections/${s.id}`} className="flex items-center justify-between gap-4 px-4 py-4 hover:bg-surface-sunken">
                  <span className="min-w-0">
                    <span className="block font-medium text-fg">
                      <span className="font-mono">{s.subject.code}</span> {s.subject.name}
                    </span>
                    <span className="block text-sm text-muted">
                      Section {s.name} · {s.department.code}
                    </span>
                  </span>
                  <span className="shrink-0 text-sm text-muted tabular-nums">{s.enrollment_count === 1 ? "1 student" : `${s.enrollment_count} students`}</span>
                </Link>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}
