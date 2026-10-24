import { Button } from "@/components/ui/button";
import { useDelayedFlag } from "@/lib/useDelayedFlag";

/** Design.md §6 Pagination: "Showing N" and "Load more"; no page numbers or fake totals. */
export function LoadMore({
  shown,
  hasMore,
  loading,
  onLoad,
}: {
  shown: number;
  hasMore: boolean;
  loading: boolean;
  onLoad: () => void;
}) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-3">
      <p className="text-sm text-muted" aria-live="polite">
        Showing {shown}
      </p>
      {hasMore && (
        <Button variant="secondary" size="sm" onClick={onLoad} disabled={loading}>
          {loading ? "Loading…" : "Load more"}
        </Button>
      )}
    </div>
  );
}

/** Row blocks shaped like the table, after the 150 ms delay (Design.md §6 Skeleton). */
export function ListLoading({ label }: { label: string }) {
  const show = useDelayedFlag(true);
  return (
    <div role="status" aria-label={label} className="space-y-2">
      {show && [0, 1, 2].map((i) => <div key={i} className="h-12 animate-pulse rounded-sm bg-surface-sunken motion-reduce:animate-none" />)}
    </div>
  );
}
