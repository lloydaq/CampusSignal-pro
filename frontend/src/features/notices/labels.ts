import type { Me } from "@/features/auth/api";

import type { Category, NoticeSummary, Priority } from "./api";

export const CATEGORY_LABEL: Record<Category, string> = {
  ACADEMIC: "Academic",
  EXAMINATION: "Examination",
  ADMINISTRATIVE: "Administrative",
  EVENT: "Event",
  FACILITIES: "Facilities",
  GENERAL: "General",
};

export const PRIORITY_LABEL: Record<Priority, string> = { NORMAL: "Normal", HIGH: "High", URGENT: "Urgent" };

export const noticeKeys = {
  all: ["notices"] as const,
  list: (filters: object) => ["notices", "list", filters] as const,
  one: (id: string) => ["notices", "one", id] as const,
  department: (id: string) => ["departments", "page", id] as const,
};

/** Who may compose (NOTICE-002): college admins anywhere, department admins for their departments. */
export function publishing(me: Me): { college: boolean; departmentIds: string[] } {
  const college = me.roles.some((r) => r.role === "COLLEGE_ADMIN");
  const departmentIds = me.roles.flatMap((r) => (r.role === "DEPARTMENT_ADMIN" && r.department ? [r.department.id] : []));
  return { college, departmentIds };
}

export const canPublish = (me: Me) => {
  const p = publishing(me);
  return p.college || p.departmentIds.length > 0;
};

/** Who issued it: the department, or the college itself (Design.md §3.3 official treatment). */
export function issuer(notice: Pick<NoticeSummary, "department">, collegeName: string): string {
  return notice.department ? notice.department.name : collegeName;
}
