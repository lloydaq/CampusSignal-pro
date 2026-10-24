import type { Ref, TextareaHTMLAttributes } from "react";

import { cn } from "@/lib/utils";

export function Textarea({ className, ref, ...props }: TextareaHTMLAttributes<HTMLTextAreaElement> & { ref?: Ref<HTMLTextAreaElement> | undefined }) {
  return (
    <textarea
      ref={ref}
      className={cn(
        "min-h-24 w-full rounded-sm border border-border-strong bg-surface px-3 py-2 text-base text-fg placeholder:text-subtle disabled:opacity-60 aria-invalid:border-danger",
        className,
      )}
      {...props}
    />
  );
}
