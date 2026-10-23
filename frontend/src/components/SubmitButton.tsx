import { LoaderCircle } from "lucide-react";

import { Button, type ButtonProps } from "@/components/ui/button";

/** Submit with a pending state: spinner plus a label that says what's happening (Design.md §6). */
export function SubmitButton({ pending, pendingLabel, children, ...props }: ButtonProps & { pending: boolean; pendingLabel: string }) {
  return (
    <Button type="submit" disabled={pending} aria-disabled={pending} {...props}>
      {pending && <LoaderCircle aria-hidden="true" strokeWidth={1.5} className="animate-spin motion-reduce:animate-none" />}
      {pending ? pendingLabel : children}
    </Button>
  );
}
