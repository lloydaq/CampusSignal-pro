import type { Capability } from "@/features/auth/api";
import { useMe } from "@/features/auth/session";

interface Tab {
  to: string;
  label: string;
  needs: Capability;
}

/** Manage sub-pages (Design.md §5 screen 17). Department admins review requests and see their members. */
export const MANAGE_TABS: Tab[] = [
  { to: "requests", label: "Requests", needs: "review_memberships" },
  { to: "members", label: "Members", needs: "review_memberships" },
  { to: "invites", label: "Invites", needs: "manage_college" },
  { to: "departments", label: "Departments", needs: "manage_college" },
  { to: "roster", label: "Roster", needs: "manage_college" },
  { to: "audit", label: "Audit log", needs: "manage_college" },
];

/** Times in Manage are shown in the college's time zone (Rules R-4.6). */
export function useCollegeTimezone(): string {
  return useMe().membership?.college.timezone ?? "Asia/Kolkata";
}
