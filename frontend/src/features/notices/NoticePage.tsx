import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft } from "lucide-react";
import { useState } from "react";
import { Link, useLocation, useNavigate, useParams } from "react-router";

import { AudienceBadge } from "@/components/AudienceBadge";
import { Callout } from "@/components/Callout";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import { ErrorState } from "@/components/ErrorState";
import { Button } from "@/components/ui/button";
import { errorText } from "@/features/admin/labels";
import { ListLoading } from "@/features/admin/list";
import { useCollegeTimezone } from "@/features/admin/tabs";
import { useMe } from "@/features/auth/session";
import { ApiError } from "@/lib/api";
import { formatDateTime } from "@/lib/datetime";
import { usePageTitle } from "@/lib/usePageTitle";

import { fetchNotice, publishNotice, withdrawNotice, type Notice } from "./api";
import { CATEGORY_LABEL, issuer, noticeKeys } from "./labels";
import { LazyNoticeBody as NoticeBody } from "./LazyNoticeBody";
import { PriorityBadge, StateBadge } from "./NoticeItem";

export interface NoticeFlash {
  flash?: string;
}

/** Design.md §5 screen 8, detail: reading width, issuer block, dates (published, updated, expires). */
export function NoticePage() {
  const { noticeId = "" } = useParams();
  const notice = useQuery({ queryKey: noticeKeys.one(noticeId), queryFn: ({ signal }) => fetchNotice(noticeId, signal) });
  usePageTitle(notice.data?.title ?? "Notice");

  return (
    <article className="mx-auto max-w-reading space-y-6">
      <Link to="/notices" className="inline-flex items-center gap-1.5 text-sm text-muted hover:text-fg">
        <ArrowLeft aria-hidden="true" strokeWidth={1.5} className="size-4" />
        All notices
      </Link>
      {notice.isPending ? (
        <ListLoading label="Loading the notice" />
      ) : notice.isError ? (
        notice.error instanceof ApiError && notice.error.status === 404 ? (
          <Callout tone="info" title="This notice isn't available">
            <p>It may have been withdrawn, or it isn't meant for you.</p>
          </Callout>
        ) : (
          <ErrorState title="Couldn't load the notice." error={notice.error} onRetry={() => void notice.refetch()} retrying={notice.isFetching} />
        )
      ) : (
        <NoticeView notice={notice.data} />
      )}
    </article>
  );
}

function NoticeView({ notice }: { notice: Notice }) {
  const me = useMe();
  const timeZone = useCollegeTimezone();
  const location = useLocation();
  const flash = (location.state as NoticeFlash | null)?.flash;
  const collegeName = me.membership?.college.name ?? "";

  return (
    <>
      {flash && <Callout tone="success">{flash}</Callout>}
      <header className="space-y-3 border-l-3 border-primary pl-4">
        <div className="flex flex-wrap items-center gap-1.5">
          <PriorityBadge priority={notice.priority} />
          <AudienceBadge department={notice.department} />
          <StateBadge notice={notice} />
          <span className="text-xs text-subtle">{CATEGORY_LABEL[notice.category]}</span>
        </div>
        <h1 className="text-2xl font-semibold text-fg sm:text-3xl">{notice.title}</h1>
        <p className="text-sm text-muted">
          <span className="font-medium text-fg">Official</span> · {issuer(notice, collegeName)}
          {notice.author_name && <> · posted by {notice.author_name}</>}
        </p>
        <dl className="flex flex-wrap gap-x-6 gap-y-1 text-sm">
          {notice.published_at && <Fact label="Published" iso={notice.published_at} timeZone={timeZone} />}
          {notice.edited_at && <Fact label="Updated" iso={notice.edited_at} timeZone={timeZone} />}
          {notice.expires_at && <Fact label={notice.expired ? "Expired" : "Expires"} iso={notice.expires_at} timeZone={timeZone} />}
        </dl>
      </header>
      {notice.status === "WITHDRAWN" && (
        <Callout tone="info" title="Withdrawn">
          <p>Readers can no longer see this notice.</p>
        </Callout>
      )}
      {notice.status === "DRAFT" && (
        <Callout tone="info" title="Draft">
          <p>Only people who can publish here can see it. {notice.priority !== "NORMAL" && "Members in its audience are notified when it's published."}</p>
        </Callout>
      )}
      <NoticeBody markdown={notice.body} />
      {notice.can_manage && notice.status !== "WITHDRAWN" && <ManageActions notice={notice} />}
    </>
  );
}

function Fact({ label, iso, timeZone }: { label: string; iso: string; timeZone: string }) {
  return (
    <div className="flex gap-1.5">
      <dt className="text-muted">{label}</dt>
      <dd className="font-medium text-fg">
        <time dateTime={iso}>{formatDateTime(iso, timeZone)}</time>
      </dd>
    </div>
  );
}

function ManageActions({ notice }: { notice: Notice }) {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [withdrawing, setWithdrawing] = useState(false);
  const done = async (updated: Notice, flash: string) => {
    queryClient.setQueryData(noticeKeys.one(updated.id), updated);
    await queryClient.invalidateQueries({ queryKey: [...noticeKeys.all, "list"] });
    await navigate(".", { replace: true, state: { flash } satisfies NoticeFlash });
  };
  const publish = useMutation({ mutationFn: () => publishNotice(notice.id, notice.version), onSuccess: (n) => done(n, "Notice published.") });
  const withdraw = useMutation({
    mutationFn: (reason: string) => withdrawNotice(notice.id, reason),
    onSuccess: async (n) => {
      setWithdrawing(false);
      await done(n, "Notice withdrawn.");
    },
  });
  const conflict = publish.error instanceof ApiError && publish.error.code === "version_conflict";

  return (
    <section aria-label="Manage this notice" className="space-y-3 border-t border-border pt-6">
      {publish.isError && (
        <Callout tone="danger">
          <p>{errorText(publish.error)}</p>
          {conflict && (
            <Button size="sm" variant="secondary" onClick={() => void queryClient.invalidateQueries({ queryKey: noticeKeys.one(notice.id) }).then(() => publish.reset())}>
              Reload the notice
            </Button>
          )}
        </Callout>
      )}
      <div className="flex flex-wrap gap-3">
        {notice.status === "DRAFT" && (
          <Button onClick={() => publish.mutate()} disabled={publish.isPending}>
            {publish.isPending ? "Publishing…" : "Publish"}
          </Button>
        )}
        <Link to={`/notices/${notice.id}/edit`} className="inline-flex h-10 items-center rounded-sm border border-border-strong bg-surface px-4 text-sm font-medium text-fg hover:bg-surface-sunken pointer-coarse:min-h-11">
          Edit
        </Link>
        {notice.status === "PUBLISHED" && (
          <Button variant="ghost" className="text-danger-fg" onClick={() => setWithdrawing(true)}>
            Withdraw
          </Button>
        )}
      </div>
      {withdrawing && (
        <ConfirmDialog
          title="Withdraw this notice?"
          description="Readers stop seeing it at once, and its notifications are removed. This can't be undone."
          reasonLabel="Reason (recorded in the audit log)"
          confirmLabel="Withdraw notice"
          pendingLabel="Withdrawing…"
          pending={withdraw.isPending}
          error={withdraw.isError ? errorText(withdraw.error) : null}
          onConfirm={(reason) => withdraw.mutate(reason)}
          onCancel={() => {
            setWithdrawing(false);
            withdraw.reset();
          }}
        />
      )}
    </section>
  );
}
