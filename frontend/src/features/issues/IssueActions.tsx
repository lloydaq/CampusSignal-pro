import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useDeferredValue, useId, useState } from "react";
import { useNavigate } from "react-router";

import { Callout } from "@/components/Callout";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { errorText } from "@/features/admin/labels";
import { ApiError } from "@/lib/api";

import { assignIssue, fetchAssignees, transitionIssue, type Issue, type IssueStatus } from "./api";
import { useIssueSaved } from "./cache";
import type { IssueFlash } from "./IssuePage";
import { issueKeys, originalIdFrom } from "./labels";

const isConflict = (error: unknown) => error instanceof ApiError && error.code === "version_conflict";

export function ConflictNotice({ issueId, onReloaded }: { issueId: string; onReloaded: () => void }) {
  const queryClient = useQueryClient();
  return (
    <Callout tone="danger" title="Updated by someone else">
      <p>Reload the issue to see the latest, then try again.</p>
      <Button size="sm" variant="secondary" onClick={() => void queryClient.invalidateQueries({ queryKey: issueKeys.one(issueId) }).then(onReloaded)}>
        Reload the issue
      </Button>
    </Callout>
  );
}

interface Step {
  label: string;
  done: string;
  dialog?: { title: string; description: string; reasonLabel: string; confirm: string; pending: string; destructive: boolean };
}

/** What each change the server offers is called, and what a note-taking one asks (PRD §9.8.1). */
function stepFor(issue: Issue, to: IssueStatus): Step {
  const reopening = issue.status === "RESOLVED" || issue.status === "REJECTED";
  if (to === "ACKNOWLEDGED" && reopening) {
    // The reporter reopens because it isn't fixed; staff reopen for a reason of their own.
    const staff = issue.actions.assign;
    return {
      label: "Reopen issue",
      done: "Issue reopened.",
      dialog: {
        title: "Reopen this issue?",
        description: staff ? "It goes back to acknowledged, and the reporter is told." : "It goes back to the coordinators as acknowledged. Say what's still wrong.",
        reasonLabel: staff ? "Why reopen it? (the reporter sees this)" : "What's still wrong?",
        confirm: "Reopen issue",
        pending: "Reopening…",
        destructive: false,
      },
    };
  }
  switch (to) {
    case "ACKNOWLEDGED":
      return { label: "Acknowledge", done: "Issue acknowledged. The reporter has been told." };
    case "IN_PROGRESS":
      return { label: "Start work", done: "Marked in progress. The reporter has been told." };
    case "RESOLVED":
      return {
        label: "Resolve",
        done: "Issue resolved. The reporter has been told.",
        dialog: {
          title: "Resolve this issue?",
          description: "Say what was done. The reporter is told and can reopen it within 14 days if it isn't fixed.",
          reasonLabel: "Resolution note (the reporter sees this)",
          confirm: "Resolve issue",
          pending: "Resolving…",
          destructive: false,
        },
      };
    case "REJECTED":
      return {
        label: "Reject",
        done: "Issue rejected. The reporter has been told.",
        dialog: {
          title: "Reject this issue?",
          description: "Use this for reports that aren't the college's to fix, or that were made in bad faith. The reporter is told and sees your reason.",
          reasonLabel: "Reason (the reporter sees this)",
          confirm: "Reject issue",
          pending: "Rejecting…",
          destructive: true,
        },
      };
    default:
      return { label: to, done: "Status changed." };
  }
}

type Pending = { to: IssueStatus; duplicate: boolean } | null;

/**
 * The status changes the server says this person may make now (`actions.transitions`), as
 * buttons; those that need a note ask for it first. Rejecting may name the original issue
 * this one duplicates (ISSUE-006). The server checks every change again.
 */
export function StatusActions({ issue }: { issue: Issue }) {
  const saved = useIssueSaved(issue.id);
  const navigate = useNavigate();
  const [open, setOpen] = useState<Pending>(null);
  const [original, setOriginal] = useState("");
  const [originalError, setOriginalError] = useState<string | null>(null);
  const originalId = useId();

  const change = useMutation({
    mutationFn: ({ to, note, duplicateOf }: { to: IssueStatus; note: string; duplicateOf?: string }) =>
      transitionIssue(issue.id, { to_status: to, ...(note ? { note } : {}), ...(duplicateOf ? { duplicate_of_id: duplicateOf } : {}), version: issue.version }),
    onSuccess: async (updated, { to, duplicateOf }) => {
      setOpen(null);
      await saved(updated);
      const flash = duplicateOf ? "Closed as a duplicate. The reporter has been told." : stepFor(issue, to).done;
      await navigate(".", { replace: true, state: { flash } satisfies IssueFlash });
    },
    // Someone else changed it: close any dialog so the reload notice is in view.
    onError: (error) => {
      if (isConflict(error)) setOpen(null);
    },
  });
  const conflict = isConflict(change.error);
  const transitions = issue.actions.transitions;
  if (transitions.length === 0) return null;
  const canReject = transitions.some((t) => t.to_status === "REJECTED");
  const close = () => {
    setOpen(null);
    setOriginal("");
    setOriginalError(null);
    change.reset();
  };

  return (
    <section aria-label="Change status" className="space-y-3">
      {conflict && <ConflictNotice issueId={issue.id} onReloaded={() => change.reset()} />}
      {change.isError && !conflict && !open && <Callout tone="danger">{errorText(change.error)}</Callout>}
      <div className="flex flex-wrap gap-3">
        {transitions.map(({ to_status: to, needs_note: needsNote }) => {
          const step = stepFor(issue, to);
          const primary = to !== "REJECTED" && !(to === "ACKNOWLEDGED" && issue.status !== "SUBMITTED");
          return (
            <Button
              key={to}
              variant={primary ? "primary" : "secondary"}
              className={to === "REJECTED" ? "text-danger-fg" : undefined}
              disabled={change.isPending}
              onClick={() => (needsNote ? setOpen({ to, duplicate: false }) : change.mutate({ to, note: "" }))}
            >
              {change.isPending && change.variables.to === to && !needsNote ? "Saving…" : step.label}
            </Button>
          );
        })}
        {canReject && (
          <Button variant="ghost" disabled={change.isPending} onClick={() => setOpen({ to: "REJECTED", duplicate: true })}>
            Reject as duplicate
          </Button>
        )}
      </div>
      {open && !open.duplicate && (() => {
        const dialog = stepFor(issue, open.to).dialog;
        if (!dialog) return null;
        return (
          <ConfirmDialog
            title={dialog.title}
            description={dialog.description}
            reasonLabel={dialog.reasonLabel}
            confirmLabel={dialog.confirm}
            pendingLabel={dialog.pending}
            destructive={dialog.destructive}
            pending={change.isPending}
            error={change.isError ? errorText(change.error) : null}
            onConfirm={(note) => change.mutate({ to: open.to, note })}
            onCancel={close}
          />
        );
      })()}
      {open?.duplicate && (
        <ConfirmDialog
          title="Close as a duplicate?"
          description="Point to the earlier report of the same problem. This reporter then sees only that issue's status and resolution date, never its details."
          reasonLabel="Note (optional; the reporter sees it)"
          reasonOptional
          confirmLabel="Close as duplicate"
          pendingLabel="Closing…"
          pending={change.isPending}
          error={change.isError ? errorText(change.error) : null}
          onConfirm={(note) => {
            const id = originalIdFrom(original);
            if (!id) {
              setOriginalError("Paste the original issue's link or ID.");
              return;
            }
            change.mutate({ to: "REJECTED", note, duplicateOf: id });
          }}
          onCancel={close}
        >
          <div className="space-y-1.5">
            <label htmlFor={originalId} className="block text-sm font-medium">
              Original issue (link or ID)
            </label>
            <Input
              id={originalId}
              value={original}
              autoComplete="off"
              aria-invalid={originalError ? true : undefined}
              aria-describedby={originalError ? `${originalId}-error` : `${originalId}-help`}
              onChange={(e) => {
                setOriginal(e.target.value);
                setOriginalError(null);
              }}
            />
            {originalError ? (
              <p id={`${originalId}-error`} className="text-sm text-danger-fg">
                {originalError}
              </p>
            ) : (
              <p id={`${originalId}-help`} className="text-sm text-muted">
                Copy it from the address bar of the original issue's page.
              </p>
            )}
          </div>
        </ConfirmDialog>
      )}
    </section>
  );
}

/**
 * ISSUE-004: coordinators and college admins hand an open issue to an ACTIVE member of
 * faculty or staff (the server's assignee list), or take it back.
 */
export function AssignControl({ issue }: { issue: Issue }) {
  const saved = useIssueSaved(issue.id);
  const navigate = useNavigate();
  const [picking, setPicking] = useState(false);
  const [query, setQuery] = useState("");
  const search = useDeferredValue(query.trim());
  const searchId = useId();
  const assignees = useQuery({
    queryKey: [...issueKeys.all, "assignees", search],
    queryFn: ({ signal }) => fetchAssignees(search, null, signal),
    enabled: picking,
  });
  const assign = useMutation({
    mutationFn: (assigneeId: string | null) => assignIssue(issue.id, { assignee_id: assigneeId, version: issue.version }),
    onSuccess: async (updated) => {
      setPicking(false);
      setQuery("");
      await saved(updated);
      const flash = updated.assignee_name ? `Assigned to ${updated.assignee_name}. They've been told.` : "Nobody is assigned now.";
      await navigate(".", { replace: true, state: { flash } satisfies IssueFlash });
    },
  });
  const conflict = isConflict(assign.error);
  if (!issue.actions.assign || issue.status === "RESOLVED" || issue.status === "REJECTED") return null;

  return (
    <section aria-label="Assignment" className="space-y-3">
      {conflict && <ConflictNotice issueId={issue.id} onReloaded={() => assign.reset()} />}
      {assign.isError && !conflict && <Callout tone="danger">{errorText(assign.error)}</Callout>}
      {!picking ? (
        <div className="flex flex-wrap gap-3">
          <Button variant="secondary" onClick={() => setPicking(true)}>
            {issue.assignee_name ? "Change assignee" : "Assign"}
          </Button>
          {issue.assignee_name && (
            <Button variant="ghost" disabled={assign.isPending} onClick={() => assign.mutate(null)}>
              {assign.isPending ? "Saving…" : "Unassign"}
            </Button>
          )}
        </div>
      ) : (
        <div className="space-y-3 rounded-sm border border-border bg-surface p-4">
          <div className="space-y-1.5">
            <label htmlFor={searchId} className="block text-sm font-medium">
              Find faculty or staff
            </label>
            <Input id={searchId} type="search" autoComplete="off" value={query} onChange={(e) => setQuery(e.target.value)} />
          </div>
          {assignees.isPending ? (
            <p role="status" className="text-sm text-muted">
              Loading…
            </p>
          ) : assignees.isError ? (
            <Callout tone="danger">{errorText(assignees.error) ?? "Couldn't load the list."}</Callout>
          ) : assignees.data.items.length === 0 ? (
            <p className="text-sm text-muted">{search ? "Nobody matches that name." : "No active faculty or staff yet."}</p>
          ) : (
            <ul aria-label="Faculty and staff" className="divide-y divide-border rounded-sm border border-border">
              {assignees.data.items.map((a) => (
                <li key={a.id} className="flex items-center justify-between gap-3 px-3 py-2">
                  <span className="min-w-0 text-sm">
                    <span className="font-medium text-fg">{a.name}</span>
                    <span className="text-muted"> · {a.kind === "FACULTY" ? "Faculty" : "Staff"}</span>
                  </span>
                  <Button size="sm" variant="secondary" disabled={assign.isPending} aria-label={`Assign to ${a.name}`} onClick={() => assign.mutate(a.id)}>
                    Assign
                  </Button>
                </li>
              ))}
            </ul>
          )}
          <Button variant="ghost" size="sm" onClick={() => setPicking(false)}>
            Cancel
          </Button>
        </div>
      )}
    </section>
  );
}
