import { apiGet } from "@/lib/api";

/** A student's own academics (backend app/api/v1/academic.py, ACADEMIC-004, 007, 008). */

const CAMPUS = "/api/v1/campus";

export interface TermRef {
  id: string;
  name: string;
  is_current: boolean;
}

export interface SubjectRef {
  id: string;
  code: string;
  name: string;
}

export interface SectionRef {
  id: string;
  name: string;
}

export interface MyClass {
  /** 1 Monday … 7 Sunday */
  weekday: number;
  /** "09:00:00" */
  starts_at: string;
  ends_at: string;
  room: string;
  section: SectionRef;
  subject: SubjectRef;
}

export interface MyTimetable {
  term: TermRef | null;
  is_demo: boolean;
  classes: MyClass[];
}

export interface AttendanceSummary {
  held: number;
  attended: number;
  excused: number;
  /** Null until something counts (EXCUSED sessions leave the denominator). */
  percentage: number | null;
}

export interface MyAttendanceItem extends AttendanceSummary {
  section: SectionRef;
  subject: SubjectRef;
}

export interface MyAttendance {
  term: TermRef | null;
  is_demo: boolean;
  items: MyAttendanceItem[];
}

export type AttendanceStatus = "PRESENT" | "ABSENT" | "EXCUSED";

export interface MySectionAttendance extends AttendanceSummary {
  section: SectionRef;
  subject: SubjectRef;
  term: TermRef;
  is_demo: boolean;
  sessions: { held_on: string; slot: number; status: AttendanceStatus }[];
}

export interface MyResult {
  id: string;
  name: string;
  kind: string;
  max_score: number;
  held_on: string;
  published_at: string;
  score: number | null;
  absent: boolean;
  revised: boolean;
}

export interface MyResults {
  term: TermRef | null;
  is_demo: boolean;
  items: { section: SectionRef; subject: SubjectRef; assessments: MyResult[] }[];
}

export const fetchMyTimetable = (signal?: AbortSignal) => apiGet<MyTimetable>(`${CAMPUS}/me/timetable`, signal);
export const fetchMyAttendance = (signal?: AbortSignal) => apiGet<MyAttendance>(`${CAMPUS}/me/attendance`, signal);
export const fetchMySectionAttendance = (sectionId: string, signal?: AbortSignal) =>
  apiGet<MySectionAttendance>(`${CAMPUS}/me/attendance/${sectionId}`, signal);
export const fetchMyResults = (signal?: AbortSignal) => apiGet<MyResults>(`${CAMPUS}/me/results`, signal);

export const academicKeys = {
  all: ["academic"] as const,
  timetable: ["academic", "timetable"] as const,
  attendance: ["academic", "attendance"] as const,
  section: (id: string) => ["academic", "attendance", id] as const,
  results: ["academic", "results"] as const,
};
