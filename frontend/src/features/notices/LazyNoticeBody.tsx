import { lazy, Suspense } from "react";

import { useDelayedFlag } from "@/lib/useDelayedFlag";

// The Markdown renderer is most of this feature's weight (react-markdown + rehype-sanitize), so
// it loads only when a notice body is shown, keeping it out of the main bundle (NFR-PERF-002).
const NoticeBody = lazy(() => import("./NoticeBody").then((m) => ({ default: m.NoticeBody })));

/** Grey lines shaped like a paragraph while the renderer loads; never the Markdown source (Design.md §8). */
function BodyLoading() {
  const show = useDelayedFlag(true);
  return (
    <div role="status" aria-label="Loading the notice text" className="space-y-3">
      {show && ["w-full", "w-full", "w-11/12", "w-2/3"].map((width, i) => <div key={i} className={`h-4 ${width} animate-pulse rounded-sm bg-surface-sunken motion-reduce:animate-none`} />)}
    </div>
  );
}

export function LazyNoticeBody({ markdown }: { markdown: string }) {
  return (
    <Suspense fallback={<BodyLoading />}>
      <NoticeBody markdown={markdown} />
    </Suspense>
  );
}
