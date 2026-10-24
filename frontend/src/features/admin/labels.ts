import { isSignedOutError } from "@/features/auth/session";

import type { Kind, Member, VerificationFlag } from "./api";

export const KIND_OPTIONS: { value: Kind; label: string }[] = [
  { value: "STUDENT", label: "Student" },
  { value: "FACULTY", label: "Faculty" },
  { value: "STAFF", label: "Staff" },
];

export const STATUS_LABEL: Record<Member["status"], string> = {
  ACTIVE: "Active",
  SUSPENDED: "Suspended",
  ENDED: "Ended",
};

/** Why a request needs a person to look at it (MEMBER-006). */
export const FLAG_TEXT: Record<VerificationFlag, string> = {
  NO_ROSTER_EMAIL: "The roster has no email for this roll number, so the account couldn't be matched automatically.",
  EMAIL_MISMATCH: "The roster lists a different email for this roll number.",
  ROSTER_CLAIMED: "Another member already holds this roll number.",
  NO_ROSTER_MATCH: "This roll number isn't on the roster. Add it to the roster before approving, or reject the request.",
};

export const AUDIT_ACTIONS: Record<string, string> = {
  "membership.requested": "Asked to join",
  "membership.auto_activated": "Joined (roster match)",
  "membership.approved": "Request approved",
  "membership.rejected": "Request rejected",
  "membership.invite_accepted": "Invitation accepted",
  "college.invite_sent": "Invitation sent",
  "college.roster_imported": "Roster imported",
  "college.department_created": "Department created",
  "college.department_updated": "Department changed",
  "college.membership_department_changed": "Member's department changed",
  "college.membership_suspended": "Membership suspended",
  "college.membership_reactivated": "Membership reactivated",
  "college.membership_ended": "Membership ended",
  "college.role_granted": "Role given",
  "college.role_revoked": "Role removed",
};

/** A failed action's message for its form or dialog; null when the session-ended dialog takes over. */
export function errorText(error: unknown): string | null {
  if (isSignedOutError(error)) return null;
  return error instanceof Error ? error.message : "Something went wrong. Try again.";
}
