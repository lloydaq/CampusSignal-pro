import { useMe } from "@/features/auth/session";

import type { Section } from "./teachingApi";

/** Is the signed-in member one of the section's assigned faculty (who record and score)? */
export function useTeaches(section: Section | undefined): boolean {
  const me = useMe();
  return Boolean(section && me.membership && section.instructors.some((i) => i.membership_id === me.membership!.id));
}
