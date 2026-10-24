import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Inbox, TriangleAlert } from "lucide-react";
import { useState } from "react";

import { Callout } from "@/components/Callout";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import { EmptyState } from "@/components/EmptyState";
import { ErrorState } from "@/components/ErrorState";
import { Button } from "@/components/ui/button";
import { formatDateTime } from "@/lib/datetime";
import { usePageTitle } from "@/lib/usePageTitle";

import { manageKeys } from "./keys";
import { approveRequest, fetchQueue, rejectRequest, type QueueItem } from "./api";
import { errorText, FLAG_TEXT } from "./labels";
import { ListLoading, LoadMore } from "./list";
import { useCursorList } from "./useCursorList";
import { useCollegeTimezone } from "./tabs";

/** The approval queue (MEMBER-006): the account next to the roster's record, then a decision. */
export function RequestsTab() {
  usePageTitle("Requests · Manage");
  const { query, items } = useCursorList(manageKeys.requests, fetchQueue);

  if (query.isPending) return <ListLoading label="Loading requests" />;
  if (query.isError) return <ErrorState title="Couldn't load the requests." error={query.error} onRetry={() => void query.refetch()} retrying={query.isFetching} />;
  if (items.length === 0) {
    return (
      <EmptyState Icon={Inbox} title="No requests waiting.">
        Requests that can't be matched to the roster automatically show up here.
      </EmptyState>
    );
  }
  return (
    <div className="space-y-4">
      <ul className="divide-y divide-border rounded-sm border border-border">
        {items.map((item) => (
          <RequestRow key={item.id} item={item} />
        ))}
      </ul>
      <LoadMore shown={items.length} hasMore={query.hasNextPage} loading={query.isFetchingNextPage} onLoad={() => void query.fetchNextPage()} />
    </div>
  );
}

function RequestRow({ item }: { item: QueueItem }) {
  const queryClient = useQueryClient();
  const timeZone = useCollegeTimezone();
  const [rejecting, setRejecting] = useState(false);
  const done = async () => {
    await queryClient.invalidateQueries({ queryKey: manageKeys.requests });
    await queryClient.invalidateQueries({ queryKey: manageKeys.members });
  };
  const approve = useMutation({ mutationFn: () => approveRequest(item.id), onSuccess: done });
  const reject = useMutation({
    mutationFn: (reason: string) => rejectRequest(item.id, reason),
    onSuccess: async () => {
      setRejecting(false);
      await done();
    },
  });
  const approveError = approve.isError ? errorText(approve.error) : null;

  return (
    <li className="space-y-4 px-4 py-4">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <p className="font-medium">{item.requester.display_name}</p>
        <p className="text-sm text-muted">Asked {formatDateTime(item.created_at, timeZone)}</p>
      </div>
      {item.flag && (
        <p className="flex items-start gap-2 text-sm text-warning-fg">
          <TriangleAlert aria-hidden="true" strokeWidth={1.5} className="mt-0.5 size-4 shrink-0" />
          {FLAG_TEXT[item.flag]}
        </p>
      )}
      <div className="grid gap-4 text-sm sm:grid-cols-2">
        <dl className="space-y-1">
          <dt className="text-xs font-medium tracking-wide text-muted uppercase">Account</dt>
          <dd>{item.requester.email}</dd>
          <dd className="font-mono">{item.roll_number ?? "No roll number"}</dd>
        </dl>
        <dl className="space-y-1">
          <dt className="text-xs font-medium tracking-wide text-muted uppercase">Roster</dt>
          {item.roster ? (
            <>
              <dd>{item.roster.full_name}</dd>
              <dd>
                {item.roster.program} · {item.roster.admission_year}
                {item.roster.department && ` · ${item.roster.department.code}`}
              </dd>
            </>
          ) : (
            <dd className="text-muted">Not on the roster</dd>
          )}
        </dl>
      </div>
      {approveError && <Callout tone="danger">{approveError}</Callout>}
      <div className="flex flex-wrap gap-3">
        <Button size="sm" onClick={() => approve.mutate()} disabled={approve.isPending || reject.isPending}>
          {approve.isPending ? "Approving…" : "Approve"}
        </Button>
        <Button size="sm" variant="secondary" onClick={() => setRejecting(true)} disabled={approve.isPending}>
          Reject
        </Button>
      </div>
      {rejecting && (
        <ConfirmDialog
          title={`Reject ${item.requester.display_name}'s request?`}
          description="They'll see your reason and can send a new request."
          reasonLabel="Reason"
          confirmLabel="Reject request"
          pendingLabel="Rejecting…"
          pending={reject.isPending}
          error={reject.isError ? errorText(reject.error) : null}
          onConfirm={(reason) => reject.mutate(reason)}
          onCancel={() => {
            setRejecting(false);
            reject.reset();
          }}
        />
      )}
    </li>
  );
}
