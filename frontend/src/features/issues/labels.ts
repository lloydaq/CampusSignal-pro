import { Building, Droplets, FlaskConical, LibraryBig, Projector, CircleQuestionMark, Wifi, Zap, type LucideIcon } from "lucide-react";

import type { Me } from "@/features/auth/api";

import type { IssueCategory, IssueScope, IssueStatus } from "./api";

export const CATEGORIES: { value: IssueCategory; label: string; Icon: LucideIcon }[] = [
  { value: "CLASSROOM_EQUIPMENT", label: "Classroom equipment", Icon: Projector },
  { value: "INFRASTRUCTURE", label: "Infrastructure", Icon: Building },
  { value: "WATER_SANITATION", label: "Water & sanitation", Icon: Droplets },
  { value: "ELECTRICAL", label: "Electrical", Icon: Zap },
  { value: "NETWORK", label: "Network / Wi-Fi", Icon: Wifi },
  { value: "LIBRARY", label: "Library", Icon: LibraryBig },
  { value: "LABORATORY", label: "Laboratory", Icon: FlaskConical },
  { value: "OTHER", label: "Other", Icon: CircleQuestionMark },
];

export const CATEGORY_LABEL = Object.fromEntries(CATEGORIES.map((c) => [c.value, c.label])) as Record<IssueCategory, string>;

export const STATUS_LABEL: Record<IssueStatus, string> = {
  SUBMITTED: "Submitted",
  ACKNOWLEDGED: "Acknowledged",
  IN_PROGRESS: "In progress",
  RESOLVED: "Resolved",
  REJECTED: "Rejected",
};

export const issueKeys = {
  all: ["issues"] as const,
  list: (scope: string | object) => ["issues", "list", scope] as const,
  one: (id: string) => ["issues", "one", id] as const,
};

/** PRD §9.8.1: a reporter may reopen a resolved issue within this many days. */
export const REOPEN_DAYS = 14;

/** "3 days ago": how long an issue has been open, from the report time. */
export function ageText(iso: string, now: Date = new Date()): string {
  const hours = Math.floor((now.getTime() - new Date(iso).getTime()) / 3_600_000);
  if (hours < 1) return "Less than an hour ago";
  if (hours < 24) return hours === 1 ? "1 hour ago" : `${hours} hours ago`;
  const days = Math.floor(hours / 24);
  return days === 1 ? "1 day ago" : `${days} days ago`;
}

const UUID = /[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/i;

/** The original's ID from what a coordinator pastes: a link to the issue or the ID itself. */
export function originalIdFrom(text: string): string | null {
  const match = UUID.exec(text.trim());
  return match ? match[0].toLowerCase() : null;
}

/** Which lists this member gets (Design.md §4): everyone reports; faculty and staff can be
 * assigned; coordinators and college admins see the whole college's queue (ISSUE-004, 009).
 * The server decides again: the queue route refuses anyone else. */
export function issueViews(me: Me): IssueScope[] {
  const views: IssueScope[] = ["mine"];
  if (me.membership?.kind === "FACULTY" || me.membership?.kind === "STAFF") views.push("assigned");
  if (me.roles.some((r) => r.role === "ISSUE_COORDINATOR" || r.role === "COLLEGE_ADMIN")) views.push("queue");
  return views;
}
