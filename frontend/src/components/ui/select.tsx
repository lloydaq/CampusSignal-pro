import type { Ref, SelectHTMLAttributes } from "react";

import { cn } from "@/lib/utils";

/** Native select (Design.md §6: native-like for ≤ 7 options), styled like Input. */
export function Select({ className, ref, ...props }: SelectHTMLAttributes<HTMLSelectElement> & { ref?: Ref<HTMLSelectElement> | undefined }) {
  return (
    <select
      ref={ref}
      className={cn(
        "h-10 w-full rounded-sm border border-border-strong bg-surface px-3 text-base text-fg disabled:cursor-not-allowed disabled:opacity-60 aria-invalid:border-danger pointer-coarse:min-h-11",
        className,
      )}
      {...props}
    />
  );
}
