import { ClipboardList, Plus } from "lucide-react";
import { Link } from "react-router";

import { EmptyState } from "@/components/EmptyState";
import { ErrorState } from "@/components/ErrorState";
import { ListLoading, LoadMore } from "@/features/admin/list";
import { useCursorList } from "@/features/admin/useCursorList";
import { usePageTitle } from "@/lib/usePageTitle";

import { fetchIssues, type IssueSummary } from "./api";
import { CATEGORY_LABEL, ageText, issueKeys } from "./labels";
import { StatusBadge } from "./StatusBadge";

const NEW_ISSUE_LINK =
  "inline-flex h-10 items-center gap-2 rounded-sm bg-primary px-4 text-sm font-medium text-on-primary hover:bg-primary-hover pointer-coarse:min-h-11";

/** Design.md §5 screen 14, Mine list: status badge, title, location, age (ISSUE-003). */
export function IssuesPage() {
  usePageTitle("My issues");
  const { query, items } = useCursorList(issueKeys.list("mine"), (cursor, signal) => fetchIssues("mine", cursor, signal));

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-semibold text-fg sm:text-3xl">My issues</h1>
        <Link to="/issues/new" className={NEW_ISSUE_LINK}>
          <Plus aria-hidden="true" strokeWidth={1.5} className="size-4" />
          Report an issue
        </Link>
      </div>
      {query.isPending ? (
        <ListLoading label="Loading your issues" />
      ) : query.isError ? (
        <ErrorState title="Couldn't load your issues." error={query.error} onRetry={() => void query.refetch()} retrying={query.isFetching} />
      ) : items.length === 0 ? (
        <EmptyState Icon={ClipboardList} title="You haven't reported any issues.">
          <p>Something broken on campus? Report it and follow its progress here.</p>
        </EmptyState>
      ) : (
        <div className="space-y-4">
          <ul aria-label="My issues" className="overflow-hidden rounded-sm border border-border bg-surface">
            {items.map((issue) => (
              <IssueRow key={issue.id} issue={issue} />
            ))}
          </ul>
          <LoadMore shown={items.length} hasMore={query.hasNextPage} loading={query.isFetchingNextPage} onLoad={() => void query.fetchNextPage()} />
        </div>
      )}
    </div>
  );
}

export function IssueRow({ issue }: { issue: IssueSummary }) {
  return (
    <li className="border-b border-border last:border-b-0">
      <Link to={`/issues/${issue.id}`} className="block space-y-1.5 px-4 py-3 hover:bg-surface-sunken focus-visible:bg-surface-sunken">
        <div className="flex flex-wrap items-center gap-1.5">
          <StatusBadge status={issue.status} />
          <span className="text-xs text-subtle">{CATEGORY_LABEL[issue.category]}</span>
        </div>
        <p className="font-medium text-fg">{issue.title}</p>
        <p className="text-sm text-muted">
          {issue.location}
          {issue.room && <> · Room {issue.room}</>} · <time dateTime={issue.created_at}>{ageText(issue.created_at)}</time>
        </p>
      </Link>
    </li>
  );
}
