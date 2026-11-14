import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useId, useState, type ReactNode } from "react";
import { useNavigate } from "react-router";

import { Callout } from "@/components/Callout";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import { SubmitButton } from "@/components/SubmitButton";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { errorText } from "@/features/admin/labels";
import { fieldErrors } from "@/lib/api";

import { formatScore } from "./format";
import { deleteAssessment, KIND_LABEL, teachingKeys, updateAssessment, type Assessment, type AssessmentKind } from "./teachingApi";

/**
 * A draft can still be corrected (name, kind, date, maximum: never below a score already entered)
 * or deleted with its scores; students never saw it. Published results change only by revision.
 */
export function DraftAssessmentActions({ assessment, onChanged }: { assessment: Assessment; onChanged: (notice: string) => void }) {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const ids = { name: useId(), kind: useId(), max: useId(), date: useId() };
  const [editing, setEditing] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [form, setForm] = useState({ name: assessment.name, kind: assessment.kind, max_score: formatScore(assessment.max_score), held_on: assessment.held_on });
  const refresh = () => Promise.all([
    queryClient.invalidateQueries({ queryKey: teachingKeys.results(assessment.id) }),
    queryClient.invalidateQueries({ queryKey: teachingKeys.assessments(assessment.section_id) }),
  ]);
  const save = useMutation({
    mutationFn: () => updateAssessment(assessment.id, { version: assessment.version, name: form.name.trim(), kind: form.kind, max_score: form.max_score.trim(), held_on: form.held_on }),
    onSuccess: async () => {
      setEditing(false);
      onChanged("Details saved.");
      await refresh();
    },
  });
  const remove = useMutation({
    mutationFn: () => deleteAssessment(assessment.id),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: teachingKeys.assessments(assessment.section_id) });
      void navigate(`/teaching/sections/${assessment.section_id}?tab=assessments`, { replace: true });
    },
  });
  const errors = fieldErrors(save.error);
  const general = save.isError && Object.keys(errors).length === 0 ? errorText(save.error) : null;

  if (!editing) {
    return (
      <div className="flex flex-wrap gap-3">
        <Button size="sm" variant="secondary" onClick={() => setEditing(true)}>
          Edit details
        </Button>
        <Button size="sm" variant="ghost" onClick={() => setDeleting(true)}>
          Delete
        </Button>
        {deleting && (
          <ConfirmDialog
            title={`Delete ${assessment.name}?`}
            description={assessment.counts.entered > 0 ? `Its ${assessment.counts.entered} entered scores go with it. Students never saw them.` : "Students never saw it."}
            confirmLabel="Delete assessment"
            pendingLabel="Deleting…"
            pending={remove.isPending}
            error={remove.isError ? errorText(remove.error) : null}
            onConfirm={() => remove.mutate()}
            onCancel={() => {
              setDeleting(false);
              remove.reset();
            }}
          />
        )}
      </div>
    );
  }
  const field = (id: string, label: string, error: string | undefined, input: ReactNode) => (
    <div className="space-y-1.5">
      <label htmlFor={id} className="block text-sm font-medium">
        {label}
      </label>
      {input}
      {error && (
        <p id={`${id}-error`} className="text-sm text-danger-fg">
          {error}
        </p>
      )}
    </div>
  );
  return (
    <form
      aria-label="Edit assessment"
      noValidate
      onSubmit={(e) => {
        e.preventDefault();
        save.mutate();
      }}
      className="space-y-3 rounded-sm border border-border p-4"
    >
      <div className="grid gap-3 sm:grid-cols-2">
        {field(ids.name, "Name", errors.name, <Input id={ids.name} value={form.name} maxLength={80} onChange={(e) => setForm({ ...form, name: e.target.value })} aria-invalid={Boolean(errors.name) || undefined} aria-describedby={errors.name ? `${ids.name}-error` : undefined} />)}
        {field(
          ids.kind,
          "Kind",
          errors.kind,
          <Select id={ids.kind} value={form.kind} onChange={(e) => setForm({ ...form, kind: e.target.value as AssessmentKind })}>
            {(Object.keys(KIND_LABEL) as AssessmentKind[]).map((k) => (
              <option key={k} value={k}>
                {KIND_LABEL[k]}
              </option>
            ))}
          </Select>,
        )}
        {field(ids.max, "Maximum score", errors.max_score, <Input id={ids.max} inputMode="decimal" className="font-mono" value={form.max_score} onChange={(e) => setForm({ ...form, max_score: e.target.value })} aria-invalid={Boolean(errors.max_score) || undefined} aria-describedby={errors.max_score ? `${ids.max}-error` : undefined} />)}
        {field(ids.date, "Date", errors.held_on, <Input id={ids.date} type="date" value={form.held_on} onChange={(e) => setForm({ ...form, held_on: e.target.value })} aria-invalid={Boolean(errors.held_on) || undefined} aria-describedby={errors.held_on ? `${ids.date}-error` : undefined} />)}
      </div>
      {general && <Callout tone="danger">{general}</Callout>}
      <div className="flex gap-3">
        <SubmitButton size="sm" pending={save.isPending} pendingLabel="Saving…">
          Save details
        </SubmitButton>
        <Button
          size="sm"
          variant="ghost"
          onClick={() => {
            setEditing(false);
            save.reset();
          }}
        >
          Cancel
        </Button>
      </div>
    </form>
  );
}
