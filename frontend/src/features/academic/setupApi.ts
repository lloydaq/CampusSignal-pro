import type { Page } from "@/features/admin/api";
import type { DepartmentRef } from "@/features/auth/api";
import { apiGet, apiPost, apiRequest } from "@/lib/api";

import type { SubjectRef } from "./api";
import type { Section } from "./teachingApi";

/** Academic setup for college and department admins (ACADEMIC-001…003; backend app/api/v1/academic.py). */

const CAMPUS = "/api/v1/campus";

export interface Term {
  id: string;
  name: string;
  is_current: boolean;
  starts_on: string;
  ends_on: string;
}

export interface Subject extends SubjectRef {
  department: DepartmentRef;
}

export interface TimetableEntry {
  id: string;
  section_id: string;
  weekday: number;
  starts_at: string;
  ends_at: string;
  room: string;
}

const send = <T>(method: string, path: string, body?: unknown) =>
  apiRequest<T>(path, { method, ...(body === undefined ? {} : { body: JSON.stringify(body), headers: { "Content-Type": "application/json" } }) });

function query(params: Record<string, string | null | undefined>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) if (value) search.set(key, value);
  const text = search.toString();
  return text ? `?${text}` : "";
}

export const fetchTerms = (signal?: AbortSignal) => apiGet<{ items: Term[] }>(`${CAMPUS}/terms`, signal);
export const createTerm = (body: { name: string; starts_on: string; ends_on: string; is_current: boolean }) => apiPost<Term>(`${CAMPUS}/terms`, body);
export const makeTermCurrent = (id: string) => send<Term>("PATCH", `${CAMPUS}/terms/${id}`, { is_current: true });

/** ACADEMIC-006, P-5: how long faculty may edit a recorded attendance session (college admins). */
export const fetchSettings = (signal?: AbortSignal) => apiGet<{ attendance_edit_window_hours: number }>(`${CAMPUS}/settings`, signal);
export const updateSettings = (hours: number) =>
  send<{ attendance_edit_window_hours: number }>("PATCH", `${CAMPUS}/settings`, { attendance_edit_window_hours: hours });

export const fetchSubjects = (cursor: string | null, signal?: AbortSignal) => apiGet<Page<Subject>>(`${CAMPUS}/subjects${query({ cursor, limit: "100" })}`, signal);
export const createSubject = (body: { department_id: string; code: string; name: string }) => apiPost<Subject>(`${CAMPUS}/subjects`, body);

export const fetchSections = (termId: string, cursor: string | null, signal?: AbortSignal) =>
  apiGet<Page<Section>>(`${CAMPUS}/sections${query({ term_id: termId, cursor })}`, signal);
export const createSection = (body: { term_id: string; subject_id: string; name: string }) => apiPost<Section>(`${CAMPUS}/sections`, body);
export const setInstructors = (sectionId: string, membershipIds: string[]) => send<Section>("PUT", `${CAMPUS}/sections/${sectionId}/instructors`, { membership_ids: membershipIds });

export const importEnrollments = (sectionId: string, csv: string) =>
  apiPost<{ enrolled: number; already_enrolled: number }>(`${CAMPUS}/sections/${sectionId}/enrollments/import`, { csv });
export const removeEnrollment = (id: string) => send<undefined>("DELETE", `${CAMPUS}/enrollments/${id}`);

export const fetchTimetable = (sectionId: string, signal?: AbortSignal) => apiGet<{ items: TimetableEntry[] }>(`${CAMPUS}/sections/${sectionId}/timetable`, signal);
export const addTimetableEntry = (sectionId: string, body: { weekday: number; starts_at: string; ends_at: string; room: string }) =>
  apiPost<TimetableEntry>(`${CAMPUS}/sections/${sectionId}/timetable`, body);
export const deleteTimetableEntry = (id: string) => send<undefined>("DELETE", `${CAMPUS}/timetable-entries/${id}`);

export const setupKeys = {
  terms: ["setup", "terms"] as const,
  settings: ["setup", "settings"] as const,
  subjects: ["setup", "subjects"] as const,
  sections: (termId: string) => ["setup", "sections", termId] as const,
  timetable: (sectionId: string) => ["setup", "timetable", sectionId] as const,
};

/** Roll numbers, one per line or comma-separated, as the import's CSV (a `roll_number` header added if missing). */
export function rollNumbersCsv(text: string): string {
  const values = text
    .split(/[\n,]/)
    .map((v) => v.trim())
    .filter(Boolean);
  if (values[0]?.toLowerCase() === "roll_number") values.shift();
  return ["roll_number", ...values].join("\n") + "\n";
}
