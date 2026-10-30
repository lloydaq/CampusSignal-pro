import { useQuery } from "@tanstack/react-query";
import { ClipboardList, Plus } from "lucide-react";
import { useId, type ReactNode } from "react";
import { Link, Navigate, NavLink, useSearchParams } from "react-router";

import { DataTable, type Column } from "@/components/DataTable";
import { EmptyState } from "@/components/EmptyState";
import { ErrorState } from "@/components/ErrorState";
import { Select } from "@/components/ui/select";
import { ListLoading, LoadMore } from "@/features/admin/list";
import { useCursorList } from "@/features/admin/useCursorList";
import { useMe } from "@/features/auth/session";
import { usePageTitle } from "@/lib/usePageTitle";
import { cn } from "@/lib/utils";

import { fetchAssignees, fetchIssues, type IssueCategory, type IssueScope, type IssueStatus, type IssueSummary, type QueueFilters } from "./api";
import { CATEGORIES, CATEGORY_LABEL, STATUS_LABEL, ageText, issueKeys, issueViews } from "./labels";
import { StatusBadge } from "./StatusBadge";

const NEW_ISSUE_LINK =
  "inline-flex h-10 items-center gap-2 rounded-sm bg-primary px-4 text-sm font-medium text-on-primary hover:bg-primary-hover pointer-coarse:min-h-11";

const VIEW_LABEL: Record<IssueScope, string> = { mine: "Mine", assigned: "Assigned to me", queue: "Queue" };

const VIEW_PATH: Record<IssueScope, string> = { mine: "/issues", assigned: "/issues?view=assigned", queue: "/issues/queue" };

/** Design.md §5 screen 14: Mine, Assigned to me, and the coordinator queue (its own wide route,
 * /issues/queue, since it's a table). */
export function IssuesPage({ queue = false }: { queue?: boolean }) {
  const me = useMe();
  const views = issueViews(me);
  const [params] = useSearchParams();
  const asked: IssueScope | null = queue ? "queue" : params.get("view") === "assigned" ? "assigned" : null;
  const view: IssueScope = asked && views.includes(asked) ? asked : "mine";
  const tabbed = views.length > 1;
  usePageTitle(tabbed ? `Issues: ${VIEW_LABEL[view]}` : "My issues");
  if (queue && view !== "queue") return <Navigate to="/issues" replace />;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-semibold text-fg sm:text-3xl">{tabbed ? "Issues" : "My issues"}</h1>
        <Link to="/issues/new" className={NEW_ISSUE_LINK}>
          <Plus aria-hidden="true" strokeWidth={1.5} className="size-4" />
          Report an issue
        </Link>
      </div>
      {tabbed && (
        <nav aria-label="Issue lists" className="-mx-4 overflow-x-auto border-b border-border px-4 sm:mx-0 sm:px-0">
          <ul className="flex gap-1">
            {views.map((v) => (
              <li key={v}>
                <NavLink
                  to={VIEW_PATH[v]}
                  aria-current={view === v ? "page" : undefined}
                  className={cn(
                    "relative flex h-10 items-center px-3 text-sm font-medium whitespace-nowrap pointer-coarse:min-h-11",
                    view === v ? "text-primary after:absolute after:inset-x-2 after:bottom-0 after:h-0.75 after:rounded-sm after:bg-accent" : "text-muted hover:text-fg",
                  )}
                >
                  {VIEW_LABEL[v]}
                </NavLink>
              </li>
            ))}
          </ul>
        </nav>
      )}
      {view === "queue" ? <Queue /> : <PersonalList scope={view} />}
    </div>
  );
}

function PersonalList({ scope }: { scope: "mine" | "assigned" }) {
  const { query, items } = useCursorList(issueKeys.list(scope), (cursor, signal) => fetchIssues(scope, cursor, signal));
  const mine = scope === "mine";
  const label = mine ? "My issues" : "Issues assigned to me";

  if (query.isPending) return <ListLoading label={`Loading ${label.toLowerCase()}`} />;
  if (query.isError) {
    return <ErrorState title={mine ? "Couldn't load your issues." : "Couldn't load your assigned issues."} error={query.error} onRetry={() => void query.refetch()} retrying={query.isFetching} />;
  }
  if (items.length === 0) {
    return mine ? (
      <EmptyState Icon={ClipboardList} title="You haven't reported any issues.">
        <p>Something broken on campus? Report it and follow its progress here.</p>
      </EmptyState>
    ) : (
      <EmptyState Icon={ClipboardList} title="Nothing is assigned to you.">
        <p>Issues a coordinator hands to you appear here, and you're notified when they do.</p>
      </EmptyState>
    );
  }
  return (
    <div className="space-y-4">
      <ul aria-label={label} className="overflow-hidden rounded-sm border border-border bg-surface">
        {items.map((issue) => (
          <IssueRow key={issue.id} issue={issue} />
        ))}
      </ul>
      <LoadMore shown={items.length} hasMore={query.hasNextPage} loading={query.isFetchingNextPage} onLoad={() => void query.fetchNextPage()} />
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

const STATUSES: IssueStatus[] = ["SUBMITTED", "ACKNOWLEDGED", "IN_PROGRESS", "RESOLVED", "REJECTED"];
const AGES = ["1", "3", "7", "14", "30"];

const COLUMNS: Column<IssueSummary>[] = [
  {
    header: "Issue",
    cell: (i) => (
      <Link to={`/issues/${i.id}`} className="font-medium text-fg underline-offset-2 hover:underline">
        {i.title}
      </Link>
    ),
  },
  { header: "Status", cell: (i) => <StatusBadge status={i.status} /> },
  { header: "Category", cell: (i) => CATEGORY_LABEL[i.category] },
  { header: "Where", cell: (i) => (i.room ? `${i.location} · Room ${i.room}` : i.location) },
  { header: "Reported by", cell: (i) => i.reporter_name },
  { header: "Assignee", cell: (i) => i.assignee_name ?? <span className="text-muted">Nobody</span> },
  { header: "Age", cell: (i) => <time dateTime={i.created_at}>{ageText(i.created_at)}</time>, className: "whitespace-nowrap" },
];

/** ISSUE-009: the whole college, oldest unacknowledged first, filtered by status, category,
 * assignee and age. Filters live in the URL so a filtered queue can be shared or reloaded. */
function Queue() {
  const [params, setParams] = useSearchParams();
  const filters: QueueFilters = {
    status: (params.get("status") ?? "") as IssueStatus | "",
    category: (params.get("category") ?? "") as IssueCategory | "",
    assigneeId: params.get("assignee") ?? "",
    olderThanDays: params.get("older_than") ?? "",
  };
  const { query, items } = useCursorList(issueKeys.list({ scope: "queue", ...filters }), (cursor, signal) => fetchIssues("queue", cursor, signal, filters));
  const assignees = useQuery({ queryKey: [...issueKeys.all, "assignees", ""], queryFn: ({ signal }) => fetchAssignees("", null, signal) });
  const ids = { status: useId(), category: useId(), assignee: useId(), age: useId() };
  const filtered = Object.values(filters).some(Boolean);

  const setFilter = (key: string, value: string) => {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value);
    else next.delete(key);
    setParams(next, { replace: true });
  };

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3 sm:flex sm:flex-wrap">
        <Filter id={ids.status} label="Status" value={filters.status} onChange={(v) => setFilter("status", v)}>
          <option value="">Any status</option>
          {STATUSES.map((s) => (
            <option key={s} value={s}>
              {STATUS_LABEL[s]}
            </option>
          ))}
        </Filter>
        <Filter id={ids.category} label="Category" value={filters.category} onChange={(v) => setFilter("category", v)}>
          <option value="">Any category</option>
          {CATEGORIES.map((c) => (
            <option key={c.value} value={c.value}>
              {c.label}
            </option>
          ))}
        </Filter>
        <Filter id={ids.assignee} label="Assignee" value={filters.assigneeId} onChange={(v) => setFilter("assignee", v)}>
          <option value="">Anyone or nobody</option>
          {assignees.data?.items.map((a) => (
            <option key={a.id} value={a.id}>
              {a.name}
            </option>
          ))}
        </Filter>
        <Filter id={ids.age} label="Reported" value={filters.olderThanDays} onChange={(v) => setFilter("older_than", v)}>
          <option value="">Any time</option>
          {AGES.map((d) => (
            <option key={d} value={d}>
              {d === "1" ? "Over a day ago" : `Over ${d} days ago`}
            </option>
          ))}
        </Filter>
      </div>

      {query.isPending ? (
        <ListLoading label="Loading the queue" />
      ) : query.isError ? (
        <ErrorState title="Couldn't load the queue." error={query.error} onRetry={() => void query.refetch()} retrying={query.isFetching} />
      ) : items.length === 0 ? (
        <EmptyState Icon={ClipboardList} title={filtered ? "No issues match these filters." : "No issues reported yet."} />
      ) : (
        <div className="space-y-4">
          <p className="text-sm text-muted">New reports first, oldest at the top; then the rest, oldest first.</p>
          <DataTable caption="Issue queue" columns={COLUMNS} rows={items} rowKey={(i) => i.id} />
          <LoadMore shown={items.length} hasMore={query.hasNextPage} loading={query.isFetchingNextPage} onLoad={() => void query.fetchNextPage()} />
        </div>
      )}
    </div>
  );
}

function Filter({ id, label, value, onChange, children }: { id: string; label: string; value: string; onChange: (value: string) => void; children: ReactNode }) {
  return (
    <div className="min-w-0 space-y-1.5">
      <label htmlFor={id} className="block text-sm font-medium">
        {label}
      </label>
      <Select id={id} value={value} onChange={(e) => onChange(e.target.value)} className="w-full sm:w-auto sm:min-w-44">
        {children}
      </Select>
    </div>
  );
}
