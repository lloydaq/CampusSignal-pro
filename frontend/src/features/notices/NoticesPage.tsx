import { useQuery } from "@tanstack/react-query";
import { Megaphone, Plus } from "lucide-react";
import { useId } from "react";
import { Link, NavLink, useSearchParams } from "react-router";

import { EmptyState } from "@/components/EmptyState";
import { ErrorState } from "@/components/ErrorState";
import { Select } from "@/components/ui/select";
import { fetchDepartments } from "@/features/admin/api";
import { ListLoading, LoadMore } from "@/features/admin/list";
import { useCollegeTimezone } from "@/features/admin/tabs";
import { useCursorList } from "@/features/admin/useCursorList";
import { useMe } from "@/features/auth/session";
import { usePageTitle } from "@/lib/usePageTitle";
import { cn } from "@/lib/utils";

import { fetchNotices, type Category, type NoticeFilters, type NoticeSummary } from "./api";
import { CATEGORY_LABEL, canPublish, noticeKeys } from "./labels";
import { NoticeItem } from "./NoticeItem";

type View = "current" | "past" | "drafts" | "withdrawn";

const VIEWS: { view: View; label: string; publishersOnly: boolean }[] = [
  { view: "current", label: "Current", publishersOnly: false },
  { view: "past", label: "Past notices", publishersOnly: false },
  { view: "drafts", label: "Drafts", publishersOnly: true },
  { view: "withdrawn", label: "Withdrawn", publishersOnly: true },
];

const EMPTY: Record<View, string> = {
  current: "No current notices.",
  past: "No past notices.",
  drafts: "No drafts.",
  withdrawn: "No withdrawn notices.",
};

function asView(value: string | null): View {
  return value === "past" || value === "drafts" || value === "withdrawn" ? value : "current";
}

/** Design.md §5 screen 8: "What has the college officially said?" */
export function NoticesPage() {
  usePageTitle("Notices");
  const me = useMe();
  const timeZone = useCollegeTimezone();
  const collegeName = me.membership?.college.name ?? "";
  const publisher = canPublish(me);
  const [params, setParams] = useSearchParams();
  const view = publisher ? asView(params.get("view")) : asView(params.get("view") === "past" ? "past" : null);
  const category = (params.get("category") ?? "") as Category | "";
  const departmentId = params.get("department") ?? "";
  const filters: NoticeFilters = {
    status: view === "drafts" ? "DRAFT" : view === "withdrawn" ? "WITHDRAWN" : "PUBLISHED",
    past: view === "past",
    category,
    departmentId,
  };
  const { query, items } = useCursorList(noticeKeys.list(filters), (cursor, signal) => fetchNotices(filters, cursor, signal));
  const departments = useQuery({ queryKey: ["departments", "list"], queryFn: ({ signal }) => fetchDepartments(false, signal) });
  const categoryId = useId();
  const departmentSelectId = useId();

  const setFilter = (key: string, value: string) => {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value);
    else next.delete(key);
    setParams(next, { replace: true });
  };
  const viewLink = (v: View) => {
    const next = new URLSearchParams(params);
    if (v === "current") next.delete("view");
    else next.set("view", v);
    const text = next.toString();
    return `/notices${text ? `?${text}` : ""}`;
  };

  const pinned = view === "current" ? items.filter((n) => n.pinned) : [];
  const rest = view === "current" ? items.filter((n) => !n.pinned) : items;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-semibold text-fg sm:text-3xl">Notices</h1>
        {publisher && (
          <Link to="/notices/new" className="inline-flex h-10 items-center gap-2 rounded-sm bg-primary px-4 text-sm font-medium text-on-primary hover:bg-primary-hover pointer-coarse:min-h-11">
            <Plus aria-hidden="true" strokeWidth={1.5} className="size-4" />
            New notice
          </Link>
        )}
      </div>

      <nav aria-label="Notice views" className="-mx-4 overflow-x-auto border-b border-border px-4 sm:mx-0 sm:px-0">
        <ul className="flex gap-1">
          {VIEWS.filter((v) => publisher || !v.publishersOnly).map((v) => (
            <li key={v.view}>
              <NavLink
                to={viewLink(v.view)}
                aria-current={view === v.view ? "page" : undefined}
                className={cn(
                  "relative flex h-10 items-center px-3 text-sm font-medium whitespace-nowrap pointer-coarse:min-h-11",
                  view === v.view ? "text-primary after:absolute after:inset-x-2 after:bottom-0 after:h-0.75 after:rounded-sm after:bg-accent" : "text-muted hover:text-fg",
                )}
              >
                {v.label}
              </NavLink>
            </li>
          ))}
        </ul>
      </nav>

      <div className="grid grid-cols-2 gap-3 sm:flex sm:flex-wrap">
        <div className="min-w-0 space-y-1.5">
          <label htmlFor={categoryId} className="block text-sm font-medium">
            Category
          </label>
          <Select id={categoryId} value={category} onChange={(e) => setFilter("category", e.target.value)} className="w-full sm:w-auto sm:min-w-44">
            <option value="">All categories</option>
            {(Object.keys(CATEGORY_LABEL) as Category[]).map((c) => (
              <option key={c} value={c}>
                {CATEGORY_LABEL[c]}
              </option>
            ))}
          </Select>
        </div>
        <div className="min-w-0 space-y-1.5">
          <label htmlFor={departmentSelectId} className="block text-sm font-medium">
            Department
          </label>
          <Select id={departmentSelectId} value={departmentId} onChange={(e) => setFilter("department", e.target.value)} className="w-full sm:w-auto sm:min-w-44">
            <option value="">All notices</option>
            {departments.data?.items.map((d) => (
              <option key={d.id} value={d.id}>
                {d.name}
              </option>
            ))}
          </Select>
        </div>
      </div>

      {query.isPending ? (
        <ListLoading label="Loading notices" />
      ) : query.isError ? (
        <ErrorState title="Couldn't load notices." error={query.error} onRetry={() => void query.refetch()} retrying={query.isFetching} />
      ) : items.length === 0 ? (
        <EmptyState Icon={Megaphone} title={category || departmentId ? "No notices match these filters." : EMPTY[view]} />
      ) : (
        <div className="space-y-6">
          {pinned.length > 0 && <NoticeGroup title="Urgent" notices={pinned} collegeName={collegeName} timeZone={timeZone} />}
          {rest.length > 0 && <NoticeGroup title={pinned.length > 0 ? "Latest" : null} notices={rest} collegeName={collegeName} timeZone={timeZone} />}
          <LoadMore shown={items.length} hasMore={query.hasNextPage} loading={query.isFetchingNextPage} onLoad={() => void query.fetchNextPage()} />
        </div>
      )}
    </div>
  );
}

function NoticeGroup({ title, notices, collegeName, timeZone }: { title: string | null; notices: NoticeSummary[]; collegeName: string; timeZone: string }) {
  const id = useId();
  return (
    <section aria-labelledby={title ? id : undefined} aria-label={title ? undefined : "Notices"} className="space-y-2">
      {title && (
        <h2 id={id} className="text-sm font-semibold tracking-wide text-muted uppercase">
          {title}
        </h2>
      )}
      <ul className="overflow-hidden rounded-sm border border-border bg-surface">
        {notices.map((n) => (
          <NoticeItem key={n.id} notice={n} collegeName={collegeName} timeZone={timeZone} />
        ))}
      </ul>
    </section>
  );
}
