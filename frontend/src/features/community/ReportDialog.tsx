import { useMutation } from "@tanstack/react-query";
import { useId, useState } from "react";

import { ConfirmDialog } from "@/components/ConfirmDialog";
import { errorText } from "@/features/admin/labels";

import { reportContent, type ReportReason } from "./api";
import { REPORT_REASONS } from "./labels";

/** COMMUNITY-006: why, plus an optional note. Moderators never see who reported. */
export function ReportDialog({
  target,
  onDone,
  onCancel,
}: {
  target: { post_id: string } | { comment_id: string };
  onDone: () => void;
  onCancel: () => void;
}) {
  const [reason, setReason] = useState<ReportReason | null>(null);
  const [missing, setMissing] = useState(false);
  const legendId = useId();
  const report = useMutation({
    mutationFn: (note: string) => reportContent({ ...target, reason: reason!, ...(note ? { note } : {}) }),
    onSuccess: onDone,
  });
  const kind = "post_id" in target ? "post" : "comment";
  return (
    <ConfirmDialog
      title={`Report this ${kind}?`}
      description="Moderators will look at it. They don't see who reported it."
      reasonLabel="Anything they should know? (optional)"
      reasonOptional
      confirmLabel="Send report"
      pendingLabel="Sending…"
      destructive={false}
      pending={report.isPending}
      error={report.isError ? errorText(report.error) : null}
      onConfirm={(note) => {
        if (!reason) {
          setMissing(true);
          return;
        }
        report.mutate(note);
      }}
      onCancel={onCancel}
    >
      <fieldset aria-describedby={missing ? `${legendId}-error` : undefined} className="space-y-2">
        <legend id={legendId} className="text-sm font-medium">
          What's wrong with it?
        </legend>
        {REPORT_REASONS.map((r) => (
          <label key={r.value} className="flex min-h-11 items-center gap-2 text-sm">
            <input
              type="radio"
              name="report-reason"
              value={r.value}
              checked={reason === r.value}
              onChange={() => {
                setReason(r.value);
                setMissing(false);
              }}
              className="size-4 accent-primary"
            />
            {r.label}
          </label>
        ))}
        {missing && (
          <p id={`${legendId}-error`} className="text-sm text-danger-fg">
            Choose a reason.
          </p>
        )}
      </fieldset>
    </ConfirmDialog>
  );
}
