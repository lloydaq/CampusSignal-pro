import { CircleAlert } from "lucide-react";
import type { InputHTMLAttributes, ReactNode, Ref } from "react";

import { Input } from "@/components/ui/input";

type FormFieldProps = Omit<InputHTMLAttributes<HTMLInputElement>, "id"> & {
  id: string;
  label: string;
  helper?: ReactNode | undefined;
  error?: string | undefined;
  ref?: Ref<HTMLInputElement> | undefined;
};

/**
 * Label above, helper below; an error replaces the helper and is tied to the input with
 * aria-describedby and aria-invalid (Design.md §6, Rules R-3.3). Works with
 * react-hook-form's register(), whose ref is passed through.
 */
export function FormField({ id, label, helper, error, ref, ...inputProps }: FormFieldProps) {
  const describedBy = error ? `${id}-error` : helper ? `${id}-helper` : undefined;
  return (
    <div className="space-y-1.5">
      <label htmlFor={id} className="block text-sm font-medium text-fg">
        {label}
      </label>
      <Input id={id} ref={ref} aria-invalid={error ? true : undefined} aria-describedby={describedBy} {...inputProps} />
      {error ? (
        <p id={`${id}-error`} className="flex items-start gap-1.5 text-sm text-danger-fg">
          <CircleAlert aria-hidden="true" strokeWidth={1.5} className="mt-0.5 size-4 shrink-0" />
          {error}
        </p>
      ) : (
        helper && (
          <p id={`${id}-helper`} className="text-sm text-muted">
            {helper}
          </p>
        )
      )}
    </div>
  );
}
