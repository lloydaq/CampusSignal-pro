import type { ReactNode } from "react";

import { usePageTitle } from "@/lib/usePageTitle";

/** The one h1 of a signed-out screen, with an optional lead paragraph; also sets the tab title. */
export function AuthHeading({ title, children }: { title: string; children?: ReactNode }) {
  usePageTitle(title);
  return (
    <div className="space-y-3">
      <h1 className="text-2xl font-semibold text-fg sm:text-3xl">{title}</h1>
      {children && <div className="space-y-2 text-base text-muted">{children}</div>}
    </div>
  );
}
