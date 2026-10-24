import { apiGet, apiPost, apiRequest } from "@/lib/api";
import type { DepartmentRef } from "@/features/auth/api";

/** College administration endpoints (backend app/api/v1/campus.py; architecture.md §11.1). */

const CAMPUS = "/api/v1/campus";

export interface Page<T> {
  items: T[];
  next_cursor: string | null;
}

function query(params: Record<string, string | undefined | null>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) if (value) search.set(key, value);
  const text = search.toString();
  return text ? `?${text}` : "";
}

// --- approval queue ---

export type VerificationFlag = "NO_ROSTER_EMAIL" | "EMAIL_MISMATCH" | "ROSTER_CLAIMED" | "NO_ROSTER_MATCH";

export interface QueueItem {
  id: string;
  requester: { display_name: string; email: string };
  flag: VerificationFlag | null;
  roll_number: string | null;
  roster: { full_name: string; program: string; admission_year: number; department: DepartmentRef | null } | null;
  status: string;
  decision_reason: string | null;
  created_at: string;
}

export const fetchQueue = (cursor: string | null, signal?: AbortSignal) =>
  apiGet<Page<QueueItem>>(`${CAMPUS}/membership-requests${query({ cursor })}`, signal);
export const approveRequest = (id: string) => apiPost<{ id: string; status: string }>(`${CAMPUS}/membership-requests/${id}/approve`);
export const rejectRequest = (id: string, reason: string) =>
  apiPost<{ id: string; status: string }>(`${CAMPUS}/membership-requests/${id}/reject`, { reason });

// --- members and roles ---

export type Kind = "STUDENT" | "FACULTY" | "STAFF";
export type RoleName = "COLLEGE_ADMIN" | "DEPARTMENT_ADMIN" | "ISSUE_COORDINATOR";

export interface Grant {
  id: string;
  role: RoleName;
  department: DepartmentRef | null;
}

export interface Member {
  id: string;
  user_id: string;
  display_name: string;
  kind: Kind;
  status: "ACTIVE" | "SUSPENDED" | "ENDED";
  department: DepartmentRef | null;
  email: string | null;
  roll_number: string | null;
  roles: Grant[];
  joined_at: string;
}

export interface MemberFilters {
  query: string;
  kind: Kind | "";
  status: "ACTIVE" | "SUSPENDED" | "ENDED" | "";
}

export const fetchMembers = (filters: MemberFilters, cursor: string | null, signal?: AbortSignal) =>
  apiGet<Page<Member>>(`${CAMPUS}/members${query({ ...filters, cursor })}`, signal);
export const updateMember = (id: string, body: { status?: string; reason?: string; department_id?: string }) =>
  apiRequest<Member>(`${CAMPUS}/members/${id}`, {
    method: "PATCH",
    body: JSON.stringify(body),
    headers: { "Content-Type": "application/json" },
  });
export const grantRole = (memberId: string, body: { role: RoleName; department_id?: string }) =>
  apiPost<Grant>(`${CAMPUS}/members/${memberId}/grants`, body);
export const revokeRole = (memberId: string, grantId: string) =>
  apiRequest<void>(`${CAMPUS}/members/${memberId}/grants/${grantId}`, { method: "DELETE" });

// --- departments ---

export interface Department {
  id: string;
  code: string;
  name: string;
  description: string;
  archived: boolean;
}

export const fetchDepartments = (includeArchived: boolean, signal?: AbortSignal) =>
  apiGet<{ items: Department[] }>(`${CAMPUS}/departments${query({ include_archived: includeArchived ? "true" : null })}`, signal);
export const createDepartment = (body: { code: string; name: string; description?: string }) =>
  apiPost<Department>(`${CAMPUS}/departments`, body);
export const updateDepartment = (id: string, body: { name?: string; description?: string; archived?: boolean }) =>
  apiRequest<Department>(`${CAMPUS}/departments/${id}`, {
    method: "PATCH",
    body: JSON.stringify(body),
    headers: { "Content-Type": "application/json" },
  });

// --- invites ---

export interface Invite {
  id: string;
  email: string;
  kind: "FACULTY" | "STAFF";
  state: "PENDING" | "ACCEPTED" | "EXPIRED" | "REVOKED";
  created_at: string;
  expires_at: string;
}

export const fetchInvites = (signal?: AbortSignal) => apiGet<{ items: Invite[] }>(`${CAMPUS}/invites`, signal);
export const sendInvite = (body: { email: string; kind: "FACULTY" | "STAFF" }) => apiPost<Invite>(`${CAMPUS}/invites`, body);

// --- roster ---

export interface RosterEntry {
  id: string;
  roll_number: string;
  full_name: string;
  email: string | null;
  program: string;
  admission_year: number;
  department: DepartmentRef;
  claimed: boolean;
}

export interface RosterProblem {
  row: number;
  column: string | null;
  message: string;
}

export const fetchRoster = (search: string, cursor: string | null, signal?: AbortSignal) =>
  apiGet<Page<RosterEntry>>(`${CAMPUS}/roster${query({ query: search, cursor })}`, signal);
export const importRoster = (csv: string) => apiPost<{ imported: number }>(`${CAMPUS}/roster/import`, { csv });

// --- audit log ---

export interface AuditEntry {
  id: string;
  action: string;
  actor: { id: string; display_name: string } | null;
  target_type: string | null;
  target_id: string | null;
  reason: string | null;
  metadata: Record<string, unknown>;
  created_at: string;
}

export const fetchAudit = (action: string, cursor: string | null, signal?: AbortSignal) =>
  apiGet<Page<AuditEntry>>(`${CAMPUS}/audit-log${query({ action, cursor })}`, signal);
