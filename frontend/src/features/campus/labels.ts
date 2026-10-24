import type { Membership, RoleGrant } from "@/features/auth/api";

export const KIND_LABEL: Record<Membership["kind"], string> = {
  STUDENT: "Student",
  FACULTY: "Faculty",
  STAFF: "Staff",
};

export function roleLabel(grant: RoleGrant): string {
  switch (grant.role) {
    case "COLLEGE_ADMIN":
      return "College admin";
    case "DEPARTMENT_ADMIN":
      return `Department admin · ${grant.department?.code ?? ""}`.trim();
    case "ISSUE_COORDINATOR":
      return "Issue coordinator";
  }
}
