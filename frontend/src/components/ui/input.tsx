import type { InputHTMLAttributes, Ref } from "react";

import { cn } from "@/lib/utils";

/**
 * Text input (Design.md §6, shadcn/ui pattern, project tokens only). 16 px text so mobile
 * browsers don't zoom on focus; 44 px tall on touch screens; danger border when invalid.
 */
export function Input({ className, ref, ...props }: InputHTMLAttributes<HTMLInputElement> & { ref?: Ref<HTMLInputElement> | undefined }) {
  return (
    <input
      ref={ref}
      className={cn(
        "h-10 w-full rounded-sm border border-border-strong bg-surface px-3 text-base text-fg transition-colors placeholder:text-subtle disabled:cursor-not-allowed disabled:opacity-60 aria-invalid:border-danger pointer-coarse:min-h-11",
        className,
      )}
      {...props}
    />
  );
}
