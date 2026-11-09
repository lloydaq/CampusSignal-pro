import type { MyAttendanceItem, SectionRef, SubjectRef, TermRef } from "@/features/academic/api";
import type { IssueStatus } from "@/features/issues/api";
import { apiGet } from "@/lib/api";

/** GET /campus/home (HOME-001…004): only the viewer's blocks; each may be `status: "error"` on its own. */

type Status = "ok" | "error";

export interface HomeClass {
  starts_at: string;
  ends_at: string;
  room: string;
  section: SectionRef;
  subject: SubjectRef;
}

export type QueueKind = "membership_requests" | "content_reports" | "unacknowledged_issues";

export interface Home {
  today: string;
  is_demo: boolean;
  classes: { status: Status; term: TermRef | null; items: HomeClass[] } | null;
  attendance: { status: Status; term: TermRef | null; items: MyAttendanceItem[] } | null;
  needs_attendance: { status: Status; items: { section: SectionRef; subject: SubjectRef; held_on: string; starts_at: string }[] } | null;
  my_issues: { status: Status; open_count: number; items: { id: string; title: string; status: IssueStatus; created_at: string }[] };
  queues: { status: Status; items: { kind: QueueKind; count: number }[] } | null;
}

export const homeKey = ["campus", "home"] as const;
export const fetchHome = (signal?: AbortSignal) => apiGet<Home>("/api/v1/campus/home", signal);
