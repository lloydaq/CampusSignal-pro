import { useEffect, useId, useRef, useState } from "react";

import { Callout } from "@/components/Callout";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";

/**
 * Confirmation for destructive or irreversible actions (Design.md §6 ConfirmDialog): states the
 * consequence, names the action on its button, and asks for a reason where the PRD requires
 * one. Native <dialog>: focus is trapped and Escape cancels unless something was typed.
 */
export function ConfirmDialog({
  title,
  description,
  confirmLabel,
  pendingLabel,
  reasonLabel,
  destructive = true,
  pending,
  error,
  onConfirm,
  onCancel,
}: {
  title: string;
  description: string;
  confirmLabel: string;
  pendingLabel: string;
  /** When set, a reason (1–500 characters) is required. */
  reasonLabel?: string;
  destructive?: boolean;
  pending: boolean;
  error: string | null;
  onConfirm: (reason: string) => void;
  onCancel: () => void;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const [reason, setReason] = useState("");
  const [missing, setMissing] = useState(false);
  const titleId = useId();
  const textId = useId();
  const reasonId = useId();

  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (typeof dialog.showModal === "function" && !dialog.open) dialog.showModal();
    else dialog.setAttribute("open", "");
  }, []);

  const confirm = () => {
    if (reasonLabel && !reason.trim()) {
      setMissing(true);
      return;
    }
    onConfirm(reason.trim());
  };

  return (
    <dialog
      ref={ref}
      aria-labelledby={titleId}
      aria-describedby={textId}
      onCancel={(event) => {
        event.preventDefault();
        if (!reason.trim() && !pending) onCancel(); // Esc closes unless something was typed
      }}
      className="fixed inset-0 m-0 h-dvh max-h-none w-full max-w-none items-center justify-center bg-transparent p-4 backdrop:bg-fg/40 open:flex"
    >
      <div className="w-full max-w-auth space-y-5 rounded-md border border-border bg-surface p-6 text-fg shadow-overlay">
        <div className="space-y-2">
          <h2 id={titleId} className="text-lg font-semibold">
            {title}
          </h2>
          <p id={textId} className="text-sm text-muted">
            {description}
          </p>
        </div>
        {error && <Callout tone="danger">{error}</Callout>}
        {reasonLabel && (
          <div className="space-y-1.5">
            <label htmlFor={reasonId} className="block text-sm font-medium">
              {reasonLabel}
            </label>
            <Textarea
              id={reasonId}
              maxLength={500}
              value={reason}
              aria-invalid={missing || undefined}
              aria-describedby={missing ? `${reasonId}-error` : undefined}
              onChange={(e) => {
                setReason(e.target.value);
                setMissing(false);
              }}
            />
            {missing && (
              <p id={`${reasonId}-error`} className="text-sm text-danger-fg">
                Give a reason.
              </p>
            )}
          </div>
        )}
        <div className="flex flex-wrap justify-end gap-3">
          <Button variant="ghost" onClick={onCancel} disabled={pending}>
            Cancel
          </Button>
          <Button variant={destructive ? "destructive" : "primary"} onClick={confirm} disabled={pending}>
            {pending ? pendingLabel : confirmLabel}
          </Button>
        </div>
      </div>
    </dialog>
  );
}
