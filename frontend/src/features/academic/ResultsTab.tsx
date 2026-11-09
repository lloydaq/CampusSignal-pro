import { useQuery } from "@tanstack/react-query";
import { FileCheck2 } from "lucide-react";

import { EmptyState } from "@/components/EmptyState";
import { ErrorState } from "@/components/ErrorState";
import { ListLoading } from "@/features/admin/list";
import { usePageTitle } from "@/lib/usePageTitle";

import { NoTerm, TermLine } from "./AcademicsLayout";
import { academicKeys, fetchMyResults, type MyResult } from "./api";
import { formatDay, formatScore } from "./format";

const KIND: Record<string, string> = {
  QUIZ: "Quiz",
  ASSIGNMENT: "Assignment",
  LAB: "Lab",
  MIDTERM: "Mid-term",
  ENDTERM: "End-term",
  OTHER: "Other",
};

function Score({ result }: { result: MyResult }) {
  if (result.absent) return <span className="font-medium text-muted">Absent</span>;
  if (result.score === null) return <span className="text-muted">—</span>;
  return (
    <span className="font-mono">
      <span className="font-medium text-fg">{formatScore(result.score)}</span>
      <span className="text-muted"> / {formatScore(result.max_score)}</span>
    </span>
  );
}

/**
 * Design.md §5 screen 6: "How did I do?" Published assessments only, grouped by subject;
 * "Revised" where a published score changed. No totals or GPA in the MVP.
 */
export function ResultsTab() {
  usePageTitle("Results · Academics");
  const query = useQuery({ queryKey: academicKeys.results, queryFn: ({ signal }) => fetchMyResults(signal) });

  if (query.isPending) return <ListLoading label="Loading your results" />;
  if (query.isError) return <ErrorState title="Couldn't load your results." error={query.error} onRetry={() => void query.refetch()} retrying={query.isFetching} />;
  const { term, is_demo, items } = query.data;
  if (!term) return <NoTerm />;

  return (
    <div className="space-y-4">
      <TermLine term={term} isDemo={is_demo} />
      {items.length === 0 ? (
        <EmptyState Icon={FileCheck2} title="No results have been published yet." />
      ) : (
        items.map((group) => (
          <section key={group.section.id} aria-labelledby={`results-${group.section.id}`} className="space-y-2">
            <h2 id={`results-${group.section.id}`} className="text-base font-semibold">
              <span className="font-mono">{group.subject.code}</span> {group.subject.name}
            </h2>
            <div className="overflow-x-auto rounded-sm border border-border">
              <table className="w-full text-left text-sm tabular-nums">
                <caption className="sr-only">{group.subject.code} results</caption>
                <thead className="bg-surface-sunken">
                  <tr>
                    <th scope="col" className="px-4 py-2 font-medium text-muted">
                      Assessment
                    </th>
                    <th scope="col" className="hidden px-3 py-2 font-medium text-muted sm:table-cell">
                      Date
                    </th>
                    <th scope="col" className="px-4 py-2 text-right font-medium text-muted">
                      Score
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {group.assessments.map((a) => (
                    <tr key={a.id} className="border-t border-border">
                      <th scope="row" className="px-4 py-3 text-left font-normal">
                        <span className="flex flex-wrap items-center gap-2">
                          <span className="font-medium text-fg">{a.name}</span>
                          {a.revised && (
                            <span className="rounded-sm border border-border-strong px-1.5 py-0.5 text-xs font-medium text-muted" title="This score was changed after it was published.">
                              Revised
                            </span>
                          )}
                        </span>
                        <span className="block text-xs text-muted">
                          {KIND[a.kind] ?? a.kind}
                          <span className="sm:hidden"> · {formatDay(a.held_on)}</span>
                        </span>
                      </th>
                      <td className="hidden px-3 py-3 whitespace-nowrap text-muted sm:table-cell">{formatDay(a.held_on)}</td>
                      <td className="px-4 py-3 text-right whitespace-nowrap">
                        <Score result={a} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        ))
      )}
    </div>
  );
}
