import { lazy, Suspense } from "react";

// The Markdown renderer is most of this feature's weight (react-markdown + rehype-sanitize), so
// it loads only when a notice body is shown, keeping it out of the main bundle (NFR-PERF-002).
const NoticeBody = lazy(() => import("./NoticeBody").then((m) => ({ default: m.NoticeBody })));

export function LazyNoticeBody({ markdown }: { markdown: string }) {
  return (
    <Suspense fallback={<p className="text-base whitespace-pre-line text-fg">{markdown}</p>}>
      <NoticeBody markdown={markdown} />
    </Suspense>
  );
}
