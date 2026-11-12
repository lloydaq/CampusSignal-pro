import { Suspense, type ReactNode } from "react";

import { ListLoading } from "@/features/admin/list";

/** Where a lazy screen loads: the surrounding layout (navigation, tabs) stays in place. */
export function RouteSuspense({ children }: { children: ReactNode }) {
  return <Suspense fallback={<ListLoading label="Loading" />}>{children}</Suspense>;
}
