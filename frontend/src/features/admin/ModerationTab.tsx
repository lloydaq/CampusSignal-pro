import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ShieldCheck } from "lucide-react";
import { useId, useState } from "react";
import { Link, useSearchParams } from "react-router";

import { AudienceBadge } from "@/components/AudienceBadge";
import { Callout } from "@/components/Callout";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import { EmptyState } from "@/components/EmptyState";
import { ErrorState } from "@/components/ErrorState";
import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/select";
import { fetchModerationQueue, resolveReport, type ModerationItem, type ReportStatus } from "@/features/community/api";
import { communityKeys, REPORT_REASONS, roleLabel } from "@/features/community/labels";
import { formatDateTime } from "@/lib/datetime";
import { usePageTitle } from "@/lib/usePageTitle";

import { manageKeys } from "./keys";
import { errorText } from "./labels";
import { ListLoading, LoadMore } from "./list";
import { useCursorList } from "./useCursorList";
import { useCollegeTimezone } from "./tabs";

const VIEWS: { value: ReportStatus; label: string; empty: string; hint?: string }[] = [
  { value: "OPEN", label: "Open reports", empty: "No reports to review.", hint: "Reports from members show up here, oldest first." },
  { value: "ACTIONED", label: "Hidden", empty: "Nothing has been hidden yet." },
  { value: "DISMISSED", label: "Dismissed", empty: "No reports have been dismissed yet." },
];

const REASON_LABEL = Object.fromEntries(REPORT_REASONS.map((r) => [r.value, r.label])) as Record<ModerationItem["reason"], string>;

/**
 * COMMUNITY-007: the reports queue. College admins see every report; department admins those
 * about their departments' posts (the server decides). Hide needs the reason its author reads.
 */
export function ModerationTab() {
  usePageTitle("Moderation · Manage");
  const statusId = useId();
  const [params, setParams] = useSearchParams();
  const view = VIEWS.find((v) => v.value === params.get("status")) ?? VIEWS[0]!;
  const { query, items } = useCursorList([...manageKeys.moderation, view.value], (cursor, signal) => fetchModerationQueue(view.value, cursor, signal));
  const [done, setDone] = useState<string | null>(null);

  return (
    <div className="space-y-4">
      <div className="max-w-xs space-y-1.5">
        <label htmlFor={statusId} className="block text-sm font-medium">
          Show
        </label>
        <Select
          id={statusId}
          value={view.value}
          onChange={(e) => {
            setDone(null);
            setParams(e.target.value === "OPEN" ? {} : { status: e.target.value }, { replace: true });
          }}
        >
          {VIEWS.map((v) => (
            <option key={v.value} value={v.value}>
              {v.label}
            </option>
          ))}
        </Select>
      </div>
      <div aria-live="polite">{done && <Callout tone="success">{done}</Callout>}</div>
      {query.isPending ? (
        <ListLoading label="Loading reports" />
      ) : query.isError ? (
        <ErrorState title="Couldn't load the reports." error={query.error} onRetry={() => void query.refetch()} retrying={query.isFetching} />
      ) : items.length === 0 ? (
        <EmptyState Icon={ShieldCheck} title={view.empty}>
          {view.hint}
        </EmptyState>
      ) : (
        <>
          <ul aria-label={view.label} className="divide-y divide-border rounded-sm border border-border">
            {items.map((item) => (
              <ReportRow key={item.id} item={item} onResolved={setDone} />
            ))}
          </ul>
          <LoadMore shown={items.length} hasMore={query.hasNextPage} loading={query.isFetchingNextPage} onLoad={() => void query.fetchNextPage()} />
        </>
      )}
    </div>
  );
}

function ReportRow({ item, onResolved }: { item: ModerationItem; onResolved: (message: string) => void }) {
  const queryClient = useQueryClient();
  const timeZone = useCollegeTimezone();
  const [deciding, setDeciding] = useState<"HIDE" | "DISMISS" | null>(null);
  const { content } = item;
  const kind = content.type;
  const role = roleLabel(content.author);
  const resolve = useMutation({
    mutationFn: (body: { action: "HIDE" | "DISMISS"; reason?: string }) => resolveReport(item.id, body),
    onSuccess: async (result, body) => {
      setDeciding(null);
      const others = result.closed_reports - 1;
      const closed = others > 0 ? ` ${others === 1 ? "1 other report" : `${others} other reports`} on it closed too.` : "";
      onResolved(body.action === "HIDE" ? `${kind === "post" ? "Post" : "Comment"} hidden. Its author has been told why.${closed}` : `Report dismissed. The ${kind} stays up.${closed}`);
      await queryClient.invalidateQueries({ queryKey: manageKeys.moderation });
      await queryClient.invalidateQueries({ queryKey: manageKeys.audit });
      await queryClient.invalidateQueries({ queryKey: communityKeys.all });
    },
    // Someone else got there first: refresh so the row moves to its history.
    onError: () => void queryClient.invalidateQueries({ queryKey: manageKeys.moderation }),
  });

  return (
    <li className="space-y-3 px-4 py-4">
      <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
        <p className="flex flex-wrap items-center gap-2">
          <span className="font-medium">{REASON_LABEL[item.reason] ?? item.reason}</span>{" "}
          {item.open_reports > 1 && <span className="text-sm text-muted">· {item.open_reports} open reports on this {kind}</span>}
        </p>
        <p className="text-sm text-muted">Reported {formatDateTime(item.created_at, timeZone)}</p>
      </div>
      {item.note && <p className="text-sm text-muted">Reporter's note: {item.note}</p>}
      <figure className="space-y-2 rounded-sm border border-border bg-surface-sunken px-3 py-3">
        <figcaption className="flex flex-wrap items-center gap-2 text-sm">
          <span className="text-muted">{kind === "post" ? "Post" : "Comment"} by</span>{" "}
          <span className="font-medium text-fg">{content.author.name}</span>{" "}
          {role && <span className="rounded-sm bg-surface px-1.5 py-0.5 text-xs font-medium text-muted">{role}</span>}
          <AudienceBadge department={content.visibility === "DEPARTMENT" ? content.department : null} />
        </figcaption>
        <blockquote className="line-clamp-6 text-sm whitespace-pre-line text-fg">{content.body}</blockquote>
      </figure>
      {item.status !== "OPEN" && (
        <p className="text-sm text-muted">
          {item.status === "ACTIONED" ? "Hidden" : "Dismissed"}
          {item.handled_at && ` ${formatDateTime(item.handled_at, timeZone)}`}
          {item.status === "ACTIONED" && content.hidden_reason && <>. Reason given to its author: {content.hidden_reason}</>}
        </p>
      )}
      <div className="flex flex-wrap items-center gap-3">
        {item.status === "OPEN" && (
          <>
            <Button size="sm" variant="destructive" onClick={() => setDeciding("HIDE")}>
              Hide {kind}
            </Button>
            <Button size="sm" variant="secondary" onClick={() => setDeciding("DISMISS")}>
              Dismiss
            </Button>
          </>
        )}
        <Link to={`/community/posts/${content.post_id}`} className="inline-flex min-h-8 items-center text-sm font-medium text-primary hover:underline pointer-coarse:min-h-11">
          Open the post
        </Link>
      </div>
      {deciding === "HIDE" && (
        <ConfirmDialog
          title={`Hide this ${kind}?`}
          description={`Only its author and moderators will see it${kind === "post" ? ", and it takes no new comments or reactions" : ""}. Its author is told, with your reason.`}
          reasonLabel="Reason (its author sees this)"
          confirmLabel={`Hide ${kind}`}
          pendingLabel="Hiding…"
          pending={resolve.isPending}
          error={resolve.isError ? errorText(resolve.error) : null}
          onConfirm={(reason) => resolve.mutate({ action: "HIDE", reason })}
          onCancel={() => {
            setDeciding(null);
            resolve.reset();
          }}
        />
      )}
      {deciding === "DISMISS" && (
        <ConfirmDialog
          title="Dismiss this report?"
          description={`The ${kind} stays up and every open report on it closes. Its author isn't told.`}
          reasonLabel="Why? (optional, for the audit log)"
          reasonOptional
          destructive={false}
          confirmLabel="Dismiss report"
          pendingLabel="Dismissing…"
          pending={resolve.isPending}
          error={resolve.isError ? errorText(resolve.error) : null}
          onConfirm={(reason) => resolve.mutate({ action: "DISMISS", ...(reason ? { reason } : {}) })}
          onCancel={() => {
            setDeciding(null);
            resolve.reset();
          }}
        />
      )}
    </li>
  );
}
