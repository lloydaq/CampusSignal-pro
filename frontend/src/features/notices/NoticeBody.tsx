import Markdown, { type Components } from "react-markdown";
import rehypeSanitize, { defaultSchema } from "rehype-sanitize";

/**
 * A notice body: the NOTICE-001 Markdown subset (paragraphs, bold, italic, lists, links) and
 * nothing else (Rules R-2.18). Raw HTML is never rendered (skipHtml), other elements are
 * unwrapped to their text, and rehype-sanitize strips anything unsafe that remains, including
 * javascript: links. Output is React elements, never innerHTML.
 */
const ALLOWED = ["p", "strong", "em", "ul", "ol", "li", "a", "br"];

const schema = {
  ...defaultSchema,
  tagNames: ALLOWED,
  attributes: { a: ["href"] },
  protocols: { href: ["http", "https", "mailto"] },
};

const components: Components = {
  a: ({ href, children }) => (
    <a href={href} target="_blank" rel="noopener noreferrer nofollow" className="text-primary underline underline-offset-2">
      {children}
    </a>
  ),
  ul: ({ children }) => <ul className="list-disc space-y-1 pl-6">{children}</ul>,
  ol: ({ children }) => <ol className="list-decimal space-y-1 pl-6">{children}</ol>,
};

export function NoticeBody({ markdown }: { markdown: string }) {
  return (
    <div className="space-y-4 text-base leading-relaxed text-fg lg:text-lg">
      <Markdown skipHtml allowedElements={ALLOWED} unwrapDisallowed rehypePlugins={[[rehypeSanitize, schema]]} components={components}>
        {markdown}
      </Markdown>
    </div>
  );
}
