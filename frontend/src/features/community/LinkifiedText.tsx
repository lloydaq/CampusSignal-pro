import { Fragment } from "react";

import { linkify } from "./text";

/**
 * A post or comment as its author wrote it: React escapes the text, line breaks are kept, and
 * only http(s) addresses become links, which never pass on who clicked them.
 */
export function LinkifiedText({ text, className }: { text: string; className?: string }) {
  return (
    <p className={className ?? "text-base whitespace-pre-line text-fg"}>
      {linkify(text).map((part, i) =>
        "href" in part ? (
          <a key={i} href={part.href} rel="noopener noreferrer nofollow" className="break-all text-primary underline underline-offset-2">
            {part.href}
          </a>
        ) : (
          <Fragment key={i}>{part.text}</Fragment>
        ),
      )}
    </p>
  );
}
