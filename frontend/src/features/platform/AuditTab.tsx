import { History } from "lucide-react";

import { DataTable } from "@/components/DataTable";
import { EmptyState } from "@/components/EmptyState";
import { ErrorState } from "@/components/ErrorState";
import { ListLoading, LoadMore } from "@/features/admin/list";
import { useCursorList } from "@/features/admin/useCursorList";
import { formatDateTime } from "@/lib/datetime";
import { usePageTitle } from "@/lib/usePageTitle";

import { fetchPlatformAudit } from "./api";
import { AUDIT_ACTIONS } from "./labels";

/** Platform-level actions (ADMIN-007): colleges, first admins, accounts. Times are UTC. */
export function PlatformAuditTab() {
  usePageTitle("Audit log · Platform");
  const { query, items } = useCursorList(["platform", "audit"], fetchPlatformAudit);
  if (query.isPending) return <ListLoading label="Loading the audit log" />;
  if (query.isError) return <ErrorState title="Couldn't load the audit log." error={query.error} onRetry={() => void query.refetch()} retrying={query.isFetching} />;
  if (items.length === 0) return <EmptyState Icon={History} title="Nothing recorded yet." />;
  return (
    <div className="space-y-4">
      <DataTable
        caption="Platform audit log"
        rows={items}
        rowKey={(e) => e.id}
        columns={[
          { header: "When (UTC)", cell: (e) => <span className="whitespace-nowrap">{formatDateTime(e.created_at, "UTC")}</span> },
          { header: "What", cell: (e) => AUDIT_ACTIONS[e.action] ?? <span className="font-mono">{e.action}</span> },
          { header: "Target", cell: (e) => (e.target_type ? <span className="font-mono">{e.target_type}</span> : <span className="text-muted">None</span>) },
          { header: "Reason", cell: (e) => e.reason ?? <span className="text-muted">None</span> },
        ]}
      />
      <LoadMore shown={items.length} hasMore={query.hasNextPage} loading={query.isFetchingNextPage} onLoad={() => void query.fetchNextPage()} />
    </div>
  );
}
