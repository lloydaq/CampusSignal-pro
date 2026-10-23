import type { FieldValues, Path, UseFormSetError } from "react-hook-form";

import { ApiError, fieldErrors } from "@/lib/api";

import { retryAfterText } from "./navigation";

/**
 * Put a failed request's field messages on the form's fields and return the message for
 * the form as a whole, or null when every problem was attached to a field.
 */
export function applyServerError<T extends FieldValues>(
  error: unknown,
  setError: UseFormSetError<T>,
  fields: readonly Path<T>[],
  rateLimitedLead = "Too many attempts.",
): string | null {
  if (error instanceof ApiError && error.status === 429) {
    return `${rateLimitedLead} ${retryAfterText(error.retryAfterSeconds)}`;
  }
  const byField = fieldErrors(error);
  let unmatched = false;
  for (const [field, message] of Object.entries(byField)) {
    if ((fields as readonly string[]).includes(field)) {
      setError(field as Path<T>, { type: "server", message }, { shouldFocus: true });
    } else {
      unmatched = true;
    }
  }
  if (Object.keys(byField).length > 0 && !unmatched) return null;
  return error instanceof Error ? error.message : "Something went wrong. Try again.";
}
