import type { CollegeStatus } from "./api";

export const collegesKey = ["platform", "colleges"] as const;
export const collegeKey = (id: string) => ["platform", "college", id] as const;

export const STATUS_LABEL: Record<CollegeStatus, string> = {
  ONBOARDING: "Onboarding",
  ACTIVE: "Active",
  SUSPENDED: "Suspended",
};

export const AUDIT_ACTIONS: Record<string, string> = {
  "platform.college_created": "College created",
  "platform.college_updated": "College changed",
  "platform.college_status_changed": "College status changed",
  "platform.admin_invited": "College admin invited",
  "platform.admin_created": "Platform admin created",
  "platform.user_suspended": "Account suspended",
  "platform.user_unsuspended": "Account reinstated",
  "platform.demo_seeded": "Demo data added",
};
