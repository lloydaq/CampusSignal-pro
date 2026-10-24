import { History } from "lucide-react";
import { useId, useState } from "react";

import { DataTable } from "@/components/DataTable";
import { EmptyState } from "@/components/EmptyState";
import { ErrorState } from "@/components/ErrorState";
import { Select } from "@/components/ui/select";
import { formatDateTime } from "@/lib/datetime";
import { usePageTitle } from "@/lib/usePageTitle";

import { fetchAudit } from "./api";
import { manageKeys } from "./keys";
import { AUDIT_ACTIONS } from "./labels";
import { ListLoading, LoadMore } from "./list";
import { useCursorList } from "./useCursorList";
import { useCollegeTimezone } from "./tabs";

/** The college's audit log (ADMIN-004): who did what, newest first, filterable by action. */
export function AuditTab() {
  usePageTitle("Audit log · Manage");
  const timeZone = useCollegeTimezone();
  const actionId = useId();
  const [action, setAction] = useState("");
  const { query, items } = useCursorList([...manageKeys.audit, action], (cursor, signal) => fetchAudit(action, cursor, signal));

  return (
    <div className="space-y-4">
      <div className="max-w-xs space-y-1.5">
        <label htmlFor={actionId} className="block text-sm font-medium">
          Action
        </label>
        <Select id={actionId} value={action} onChange={(e) => setAction(e.target.value)}>
          <option value="">All actions</option>
          {Object.entries(AUDIT_ACTIONS).map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </Select>
      </div>
      {query.isPending ? (
        <ListLoading label="Loading the audit log" />
      ) : query.isError ? (
        <ErrorState title="Couldn't load the audit log." error={query.error} onRetry={() => void query.refetch()} retrying={query.isFetching} />
      ) : items.length === 0 ? (
        <EmptyState Icon={History} title="Nothing recorded yet." />
      ) : (
        <>
          <DataTable
            caption="Audit log"
            rows={items}
            rowKey={(e) => e.id}
            columns={[
              { header: "When", cell: (e) => <span className="whitespace-nowrap">{formatDateTime(e.created_at, timeZone)}</span> },
              { header: "Who", cell: (e) => e.actor?.display_name ?? <span className="text-muted">System</span> },
              { header: "What", cell: (e) => AUDIT_ACTIONS[e.action] ?? <span className="font-mono">{e.action}</span> },
              { header: "Reason", cell: (e) => e.reason ?? <span className="text-muted">None</span> },
            ]}
          />
          <LoadMore shown={items.length} hasMore={query.hasNextPage} loading={query.isFetchingNextPage} onLoad={() => void query.fetchNextPage()} />
        </>
      )}
    </div>
  );
}
