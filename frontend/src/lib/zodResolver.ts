import type { FieldErrors, FieldValues, Resolver } from "react-hook-form";
import type { z } from "zod";

/**
 * react-hook-form resolver for a zod schema of flat fields (the auth forms).
 * Kept in-house instead of @hookform/resolvers, which pulls in optional peers (ajv) that
 * aren't otherwise needed. The first issue per field wins.
 */
export function zodResolver<T extends FieldValues>(schema: z.ZodType<T>): Resolver<T> {
  return (values) => {
    const result = schema.safeParse(values);
    if (result.success) return { values: result.data, errors: {} };
    const errors: Record<string, { type: string; message: string }> = {};
    for (const issue of result.error.issues) {
      const field = issue.path.join(".");
      if (!(field in errors)) errors[field] = { type: issue.code, message: issue.message };
    }
    return { values: {}, errors: errors as FieldErrors<T> };
  };
}
