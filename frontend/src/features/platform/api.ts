import { apiGet, apiPost, apiRequest } from "@/lib/api";
import type { Page } from "@/features/admin/api";

/** Platform administration endpoints (backend app/api/v1/platform.py; architecture.md §11.1). */

const PLATFORM = "/api/v1/platform";

export type CollegeStatus = "ONBOARDING" | "ACTIVE" | "SUSPENDED";

export interface PlatformCollege {
  id: string;
  name: string;
  slug: string;
  timezone: string;
  status: CollegeStatus;
  email_domains: string[];
  is_demo: boolean;
  created_at: string;
  active_member_count: number;
}

export interface AdminInvite {
  id: string;
  email: string;
  kind: "FACULTY" | "STAFF";
  state: "PENDING" | "ACCEPTED" | "EXPIRED" | "REVOKED";
  created_at: string;
  expires_at: string;
}

export interface PlatformCollegeDetail extends PlatformCollege {
  admin_invites: AdminInvite[];
}

export interface NewCollege {
  name: string;
  slug: string;
  timezone: string;
  email_domains: string[];
  is_demo: boolean;
}

const json = { "Content-Type": "application/json" };

export const fetchColleges = (cursor: string | null, signal?: AbortSignal) =>
  apiGet<Page<PlatformCollege>>(`${PLATFORM}/colleges${cursor ? `?cursor=${encodeURIComponent(cursor)}` : ""}`, signal);
export const createCollege = (body: NewCollege) => apiPost<PlatformCollege>(`${PLATFORM}/colleges`, body);
export const fetchCollege = (id: string, signal?: AbortSignal) => apiGet<PlatformCollegeDetail>(`${PLATFORM}/colleges/${id}`, signal);
export const updateCollege = (id: string, body: { name?: string; timezone?: string; email_domains?: string[]; status?: CollegeStatus; reason?: string }) =>
  apiRequest<PlatformCollegeDetail>(`${PLATFORM}/colleges/${id}`, { method: "PATCH", body: JSON.stringify(body), headers: json });
export const inviteCollegeAdmin = (id: string, body: { email: string; kind: "FACULTY" | "STAFF"; reason?: string }) =>
  apiPost<AdminInvite>(`${PLATFORM}/colleges/${id}/admin-invites`, body);

export interface PlatformUser {
  id: string;
  email: string;
  display_name: string;
  status: "ACTIVE" | "SUSPENDED";
  platform_role: string | null;
}

export const findUser = (email: string, signal?: AbortSignal) =>
  apiGet<{ items: PlatformUser[] }>(`${PLATFORM}/users?email=${encodeURIComponent(email)}`, signal);
export const suspendUser = (id: string, reason: string) => apiPost<PlatformUser>(`${PLATFORM}/users/${id}/suspend`, { reason });
export const unsuspendUser = (id: string, reason?: string) =>
  apiPost<PlatformUser>(`${PLATFORM}/users/${id}/unsuspend`, reason ? { reason } : {});

export interface PlatformAuditEntry {
  id: string;
  action: string;
  actor_user_id: string | null;
  college_id: string | null;
  target_type: string | null;
  target_id: string | null;
  reason: string | null;
  metadata: Record<string, unknown>;
  created_at: string;
}

export const fetchPlatformAudit = (cursor: string | null, signal?: AbortSignal) =>
  apiGet<Page<PlatformAuditEntry>>(`${PLATFORM}/audit-log${cursor ? `?cursor=${encodeURIComponent(cursor)}` : ""}`, signal);
