import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Megaphone } from "lucide-react";
import { useId, useState } from "react";
import { useParams } from "react-router";

import { Callout } from "@/components/Callout";
import { EmptyState } from "@/components/EmptyState";
import { ErrorState } from "@/components/ErrorState";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { errorText } from "@/features/admin/labels";
import { ListLoading, LoadMore } from "@/features/admin/list";
import { useCollegeTimezone } from "@/features/admin/tabs";
import { useCursorList } from "@/features/admin/useCursorList";
import { useMe } from "@/features/auth/session";
import { ApiError } from "@/lib/api";
import { usePageTitle } from "@/lib/usePageTitle";

import { fetchDepartmentPage, fetchNotices, updateDepartmentDescription, type DepartmentPage as Department, type NoticeFilters } from "./api";
import { noticeKeys, publishing } from "./labels";
import { NoticeItem } from "./NoticeItem";

/** Design.md §5 screen 11: "What's happening in my department?" No metrics. */
export function DepartmentPage() {
  const { departmentId = "" } = useParams();
  const department = useQuery({ queryKey: noticeKeys.department(departmentId), queryFn: ({ signal }) => fetchDepartmentPage(departmentId, signal) });
  usePageTitle(department.data?.name ?? "Department");

  if (department.isPending) return <ListLoading label="Loading the department" />;
  if (department.isError) {
    return department.error instanceof ApiError && department.error.status === 404 ? (
      <Callout tone="info" title="This department doesn't exist" />
    ) : (
      <ErrorState title="Couldn't load the department." error={department.error} onRetry={() => void department.refetch()} retrying={department.isFetching} />
    );
  }
  return <DepartmentView department={department.data} />;
}

function DepartmentView({ department }: { department: Department }) {
  const me = useMe();
  const rights = publishing(me);
  const canEdit = !department.archived && (rights.college || rights.departmentIds.includes(department.id));
  return (
    <div className="space-y-8">
      <header className="space-y-3">
        <p className="font-mono text-sm text-subtle">{department.code}</p>
        <h1 className="text-2xl font-semibold text-fg sm:text-3xl">{department.name}</h1>
        {department.archived && (
          <Callout tone="info" title="This department is archived">
            <p>It's kept for reference. New notices can't be posted to it.</p>
          </Callout>
        )}
        <Description department={department} canEdit={canEdit} />
        <p className="text-sm text-muted">
          {department.admins.length === 0 ? (
            "No department admins yet."
          ) : (
            <>
              Department {department.admins.length === 1 ? "admin" : "admins"}: <span className="font-medium text-fg">{department.admins.join(", ")}</span>
            </>
          )}
        </p>
      </header>
      <DepartmentNotices department={department} />
    </div>
  );
}

function Description({ department, canEdit }: { department: Department; canEdit: boolean }) {
  const queryClient = useQueryClient();
  const id = useId();
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(department.description);
  const save = useMutation({
    mutationFn: () => updateDepartmentDescription(department.id, draft.trim()),
    onSuccess: async () => {
      setEditing(false);
      await queryClient.invalidateQueries({ queryKey: noticeKeys.department(department.id) });
    },
  });

  if (!editing) {
    return (
      <div className="space-y-2">
        {department.description ? <p className="max-w-reading text-base whitespace-pre-line text-fg">{department.description}</p> : <p className="text-base text-muted">No description yet.</p>}
        {canEdit && (
          <Button size="sm" variant="secondary" onClick={() => setEditing(true)}>
            Edit description
          </Button>
        )}
      </div>
    );
  }
  return (
    <form
      className="max-w-reading space-y-2"
      onSubmit={(event) => {
        event.preventDefault();
        save.mutate();
      }}
    >
      <label htmlFor={id} className="block text-sm font-medium">
        Description
      </label>
      <Textarea id={id} maxLength={2000} value={draft} onChange={(e) => setDraft(e.target.value)} />
      {save.isError && <Callout tone="danger">{errorText(save.error)}</Callout>}
      <div className="flex gap-3">
        <Button type="submit" size="sm" disabled={save.isPending}>
          {save.isPending ? "Saving…" : "Save description"}
        </Button>
        <Button
          size="sm"
          variant="ghost"
          onClick={() => {
            setEditing(false);
            setDraft(department.description);
            save.reset();
          }}
        >
          Cancel
        </Button>
      </div>
    </form>
  );
}

function DepartmentNotices({ department }: { department: Department }) {
  const me = useMe();
  const timeZone = useCollegeTimezone();
  const headingId = useId();
  const filters: NoticeFilters = { status: "PUBLISHED", past: false, category: "", departmentId: department.id };
  const { query, items } = useCursorList(noticeKeys.list(filters), (cursor, signal) => fetchNotices(filters, cursor, signal));
  return (
    <section aria-labelledby={headingId} className="space-y-3">
      <h2 id={headingId} className="text-lg font-semibold">
        Department notices
      </h2>
      {query.isPending ? (
        <ListLoading label="Loading department notices" />
      ) : query.isError ? (
        <ErrorState title="Couldn't load notices." error={query.error} onRetry={() => void query.refetch()} retrying={query.isFetching} />
      ) : items.length === 0 ? (
        <EmptyState Icon={Megaphone} title="No current notices for this department." />
      ) : (
        <>
          <ul className="overflow-hidden rounded-sm border border-border bg-surface">
            {items.map((n) => (
              <NoticeItem key={n.id} notice={n} collegeName={me.membership?.college.name ?? ""} timeZone={timeZone} />
            ))}
          </ul>
          <LoadMore shown={items.length} hasMore={query.hasNextPage} loading={query.isFetchingNextPage} onLoad={() => void query.fetchNextPage()} />
        </>
      )}
    </section>
  );
}
