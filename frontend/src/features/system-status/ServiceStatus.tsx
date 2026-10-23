import { useQuery } from "@tanstack/react-query";
import { CircleAlert, CircleCheck, CircleHelp, CircleX, RotateCw, type LucideIcon } from "lucide-react";

import { Button } from "@/components/ui/button";
import { ApiError } from "@/lib/api";
import { useDelayedFlag } from "@/lib/useDelayedFlag";
import { cn } from "@/lib/utils";

import { fetchServiceStatus, serviceStatusQueryKey, type ApiState, type DatabaseState } from "./api";

type Tone = "success" | "warning" | "danger" | "neutral";

interface StateView {
  label: string;
  Icon: LucideIcon;
  tone: Tone;
}

const API_VIEW: Record<ApiState, StateView> = {
  running: { label: "Running", Icon: CircleCheck, tone: "success" },
  unreachable: { label: "Unreachable", Icon: CircleX, tone: "danger" },
};

const DATABASE_VIEW: Record<DatabaseState, StateView> = {
  ready: { label: "Ready", Icon: CircleCheck, tone: "success" },
  migrations_pending: { label: "Migrations pending", Icon: CircleAlert, tone: "warning" },
  unreachable: { label: "Unreachable", Icon: CircleX, tone: "danger" },
  unknown: { label: "Unknown while the API is unreachable", Icon: CircleHelp, tone: "neutral" },
};

const TONE_CLASS: Record<Tone, string> = {
  success: "text-success-fg",
  warning: "text-warning-fg",
  danger: "text-danger-fg",
  neutral: "text-muted",
};

function StatusRow({ name, view }: { name: string; view: StateView }) {
  const { label, Icon, tone } = view;
  return (
    <div className="flex items-center justify-between gap-4 py-3">
      <dt className="text-sm text-muted">{name}</dt>
      <dd className={cn("flex items-center gap-1.5 text-right text-sm font-medium", TONE_CLASS[tone])}>
        <Icon aria-hidden="true" strokeWidth={1.5} className="size-4 shrink-0" />
        {label}
      </dd>
    </div>
  );
}

/** Live API and database status. Every state is spelled out in words, not colour alone. */
export function ServiceStatus() {
  const query = useQuery({
    queryKey: serviceStatusQueryKey,
    queryFn: ({ signal }) => fetchServiceStatus(signal),
  });
  const showSkeleton = useDelayedFlag(query.isPending);

  return (
    <section aria-labelledby="service-status-heading" aria-busy={query.isFetching}>
      <div className="flex items-center justify-between gap-4">
        <h2 id="service-status-heading" className="text-base font-semibold text-fg">
          Current status
        </h2>
        {query.isSuccess && (
          <Button
            variant="ghost"
            size="sm"
            onClick={() => void query.refetch()}
            disabled={query.isFetching}
          >
            <RotateCw aria-hidden="true" strokeWidth={1.5} />
            {query.isFetching ? "Checking…" : "Check again"}
          </Button>
        )}
      </div>

      <div aria-live="polite" className="mt-2 border-t border-border">
        {query.isPending &&
          (showSkeleton ? (
            <div className="space-y-3 py-3" role="status">
              <span className="sr-only">Checking service status…</span>
              <div aria-hidden="true" className="h-5 rounded-sm bg-surface-sunken" />
              <div aria-hidden="true" className="h-5 rounded-sm bg-surface-sunken" />
            </div>
          ) : (
            <span className="sr-only" role="status">
              Checking service status…
            </span>
          ))}

        {query.isError && <StatusError error={query.error} onRetry={() => void query.refetch()} retrying={query.isFetching} />}

        {query.isSuccess && (
          <dl className="divide-y divide-border">
            <StatusRow name="API" view={API_VIEW[query.data.api]} />
            <StatusRow name="Database" view={DATABASE_VIEW[query.data.database]} />
          </dl>
        )}
      </div>
    </section>
  );
}

function StatusError({ error, onRetry, retrying }: { error: Error; onRetry: () => void; retrying: boolean }) {
  const requestId = error instanceof ApiError ? error.requestId : null;
  const message = error instanceof ApiError ? error.message : "Something went wrong while checking.";
  return (
    <div role="alert" className="space-y-3 py-3">
      <p className="text-sm font-medium text-danger-fg">Couldn't check service status</p>
      <p className="text-sm text-muted">{message}</p>
      {requestId && <p className="font-mono text-xs text-subtle">Request ID {requestId}</p>}
      <Button variant="secondary" size="sm" onClick={onRetry} disabled={retrying}>
        <RotateCw aria-hidden="true" strokeWidth={1.5} />
        {retrying ? "Trying again…" : "Try again"}
      </Button>
    </div>
  );
}
