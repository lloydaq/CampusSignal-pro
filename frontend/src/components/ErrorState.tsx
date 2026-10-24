import { RotateCw } from "lucide-react";

import { Button } from "@/components/ui/button";
import { ApiError } from "@/lib/api";

/** Design.md §6 ErrorState: a title, the plain cause, Retry, and the request ID for support. */
export function ErrorState({ title, error, onRetry, retrying }: { title: string; error: Error; onRetry: () => void; retrying: boolean }) {
  const requestId = error instanceof ApiError ? error.requestId : null;
  return (
    <div role="alert" className="space-y-3 rounded-sm border border-border p-4">
      <p className="text-sm font-medium text-danger-fg">{title}</p>
      <p className="text-sm text-muted">{error instanceof ApiError ? error.message : "Something went wrong."}</p>
      {requestId && <p className="font-mono text-xs text-subtle">Request ID {requestId}</p>}
      <Button variant="secondary" size="sm" onClick={onRetry} disabled={retrying}>
        <RotateCw aria-hidden="true" strokeWidth={1.5} />
        {retrying ? "Trying again…" : "Try again"}
      </Button>
    </div>
  );
}
