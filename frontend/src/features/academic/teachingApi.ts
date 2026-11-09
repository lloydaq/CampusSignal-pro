import type { Page } from "@/features/admin/api";
import type { DepartmentRef } from "@/features/auth/api";
import { apiGet, apiPost, apiRequest } from "@/lib/api";

import type { AttendanceStatus, SubjectRef, TermRef } from "./api";

/** Section views for faculty and admins (backend app/api/v1/academic.py, ACADEMIC-005…010). */

const CAMPUS = "/api/v1/campus";

export interface Person {
  membership_id: string;
  display_name: string;
}

export interface Section {
  id: string;
  name: string;
  term: TermRef;
  subject: SubjectRef;
  department: DepartmentRef;
  instructors: Person[];
  enrollment_count: number;
}

export interface Enrollment {
  id: string;
  membership_id: string;
  display_name: string;
  /** Only for the section's department's managers. */
  roll_number: string | null;
  department: DepartmentRef | null;
}

/** "faculty" inside the window, "correction" (department admin, reason required), "window_closed", or null (read only). */
export type EditMode = "faculty" | "correction" | "window_closed" | null;

export interface AttendanceSession {
  id: string;
  section_id: string;
  held_on: string;
  slot: number;
  version: number;
  recorded_by: Person;
  counts: { present: number; absent: number; excused: number };
  edit: EditMode;
  edit_window_closes_at: string;
  created_at: string;
  updated_at: string;
}

export interface AttendanceSessionDetail extends AttendanceSession {
  records: { enrollment_id: string; membership_id: string; display_name: string; status: AttendanceStatus }[];
}

export type Mark = { enrollment_id: string; status: AttendanceStatus };

export type AssessmentKind = "QUIZ" | "ASSIGNMENT" | "LAB" | "MIDTERM" | "ENDTERM" | "OTHER";

export interface Assessment {
  id: string;
  section_id: string;
  name: string;
  kind: AssessmentKind;
  max_score: number;
  held_on: string;
  version: number;
  published_at: string | null;
  published_by: Person | null;
  counts: { enrolled: number; entered: number; absent: number };
  actions: { enter_scores: boolean; publish: boolean };
  created_at: string;
}

export interface ResultRow {
  enrollment_id: string;
  membership_id: string;
  display_name: string;
  score: number | null;
  absent: boolean;
  revised: boolean;
}

export interface AssessmentResults {
  assessment: Assessment;
  rows: ResultRow[];
}

export interface ScoreEntry {
  enrollment_id: string;
  /** A decimal string with up to two places ("18.5"), or null with `absent` / to clear. */
  score: string | null;
  absent: boolean;
}

const send = <T>(method: string, path: string, body: unknown) =>
  apiRequest<T>(path, { method, body: JSON.stringify(body), headers: { "Content-Type": "application/json" } });

const withCursor = (path: string, cursor: string | null) => (cursor ? `${path}${path.includes("?") ? "&" : "?"}cursor=${encodeURIComponent(cursor)}` : path);

export const fetchTeachingSections = (signal?: AbortSignal) => apiGet<{ term: TermRef | null; items: Section[] }>(`${CAMPUS}/teaching/sections`, signal);
export const fetchSection = (id: string, signal?: AbortSignal) => apiGet<Section>(`${CAMPUS}/sections/${id}`, signal);

/** Every enrolled student (the grid needs them all), following the cursor 100 at a time. */
export async function fetchAllEnrollments(sectionId: string, signal?: AbortSignal): Promise<Enrollment[]> {
  const all: Enrollment[] = [];
  let cursor: string | null = null;
  do {
    const page: Page<Enrollment> = await apiGet<Page<Enrollment>>(withCursor(`${CAMPUS}/sections/${sectionId}/enrollments?limit=100`, cursor), signal);
    all.push(...page.items);
    cursor = page.next_cursor;
  } while (cursor);
  return all;
}

export const fetchSessions = (sectionId: string, cursor: string | null, signal?: AbortSignal) =>
  apiGet<Page<AttendanceSession>>(withCursor(`${CAMPUS}/sections/${sectionId}/attendance-sessions`, cursor), signal);
export const fetchSession = (id: string, signal?: AbortSignal) => apiGet<AttendanceSessionDetail>(`${CAMPUS}/attendance-sessions/${id}`, signal);
export const recordSession = (sectionId: string, body: { held_on: string; slot: number; records: Mark[] }) =>
  apiPost<AttendanceSessionDetail>(`${CAMPUS}/sections/${sectionId}/attendance-sessions`, body);
export const editSession = (id: string, body: { version: number; records: Mark[]; reason?: string }) =>
  send<AttendanceSessionDetail>("PATCH", `${CAMPUS}/attendance-sessions/${id}`, body);

export const fetchAssessments = (sectionId: string, cursor: string | null, signal?: AbortSignal) =>
  apiGet<Page<Assessment>>(withCursor(`${CAMPUS}/sections/${sectionId}/assessments`, cursor), signal);
export const createAssessment = (sectionId: string, body: { name: string; kind: AssessmentKind; max_score: string; held_on: string }) =>
  apiPost<Assessment>(`${CAMPUS}/sections/${sectionId}/assessments`, body);
export const fetchResults = (id: string, signal?: AbortSignal) => apiGet<AssessmentResults>(`${CAMPUS}/assessments/${id}/results`, signal);
export const saveResults = (id: string, body: { version: number; results: ScoreEntry[]; reason?: string }) =>
  send<AssessmentResults>("PUT", `${CAMPUS}/assessments/${id}/results`, body);
export const publishAssessment = (id: string, version: number) => apiPost<Assessment>(`${CAMPUS}/assessments/${id}/publish`, { version });

export const teachingKeys = {
  sections: ["teaching", "sections"] as const,
  section: (id: string) => ["teaching", "section", id] as const,
  enrollments: (id: string) => ["teaching", "section", id, "enrollments"] as const,
  sessions: (id: string) => ["teaching", "section", id, "sessions"] as const,
  session: (id: string) => ["teaching", "session", id] as const,
  assessments: (id: string) => ["teaching", "section", id, "assessments"] as const,
  results: (id: string) => ["teaching", "assessment", id] as const,
};

export const KIND_LABEL: Record<AssessmentKind, string> = {
  QUIZ: "Quiz",
  ASSIGNMENT: "Assignment",
  LAB: "Lab",
  MIDTERM: "Mid-term",
  ENDTERM: "End-term",
  OTHER: "Other",
};
