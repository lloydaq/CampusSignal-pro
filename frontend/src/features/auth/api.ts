import { apiGet, apiPost } from "@/lib/api";

/** Auth endpoints (backend app/api/v1/auth.py, me.py; architecture.md §11.1). */

const AUTH = "/api/v1/auth";

export interface User {
  id: string;
  email: string;
  display_name: string;
  email_verified: boolean;
  platform_role: string | null;
}

interface Message {
  message: string;
}

export interface CollegeSummary {
  id: string;
  name: string;
  slug: string;
  timezone: string;
  status: "ONBOARDING" | "ACTIVE" | "SUSPENDED";
  is_demo: boolean;
}

export interface DepartmentRef {
  id: string;
  code: string;
  name: string;
}

export interface Membership {
  id: string;
  kind: "STUDENT" | "FACULTY" | "STAFF";
  status: "PENDING" | "ACTIVE" | "SUSPENDED";
  college: CollegeSummary;
  department: DepartmentRef | null;
}

export interface RoleGrant {
  role: "COLLEGE_ADMIN" | "DEPARTMENT_ADMIN" | "ISSUE_COORDINATOR";
  department: DepartmentRef | null;
}

export type Capability = "campus" | "manage_college" | "review_memberships" | "platform";

/** GET /me: who is signed in, their open college membership, roles and what they may open. */
export interface Me {
  user: User;
  membership: Membership | null;
  roles: RoleGrant[];
  capabilities: Capability[];
}

export const fetchMe = (signal?: AbortSignal) => apiGet<Me>("/api/v1/me", signal);

export const signIn = (body: { email: string; password: string }) =>
  apiPost<{ user: User; csrf_token: string }>(`${AUTH}/login`, body);

export const register = (body: { email: string; password: string; display_name: string }) =>
  apiPost<Message>(`${AUTH}/register`, body);

export const verifyEmail = (token: string) => apiPost<Message>(`${AUTH}/verify-email`, { token });

export const resendVerification = () => apiPost<Message>(`${AUTH}/resend-verification`);

export const requestPasswordReset = (body: { email: string }) => apiPost<Message>(`${AUTH}/password-reset/request`, body);

export const confirmPasswordReset = (body: { token: string; new_password: string }) =>
  apiPost<Message>(`${AUTH}/password-reset/confirm`, body);

export const changePassword = (body: { current_password: string; new_password: string }) =>
  apiPost<{ csrf_token: string }>("/api/v1/me/password", body);

export const signOut = () => apiPost<void>(`${AUTH}/logout`);

export const signOutEverywhere = () => apiPost<void>(`${AUTH}/logout-all`);

// --- joining a college (MEMBER-002…006) --------------------------------------------------

export interface CollegeListing {
  name: string;
  slug: string;
}

export interface JoinResult {
  status: "ACTIVE" | "PENDING";
  message: string;
  membership?: Membership;
}

export interface MyRequest {
  id: string;
  college: CollegeListing;
  status: "PENDING" | "REJECTED";
  decision_reason: string | null;
  created_at: string;
}

export const fetchColleges = (signal?: AbortSignal) => apiGet<{ items: CollegeListing[] }>("/api/v1/colleges", signal);

export const requestMembership = (body: { college_slug: string; roll_number: string }) =>
  apiPost<JoinResult>("/api/v1/me/membership-requests", body);

export const fetchMyRequests = (signal?: AbortSignal) => apiGet<{ items: MyRequest[] }>("/api/v1/me/membership-requests", signal);

export const acceptInvite = (token: string) => apiPost<{ membership: Membership }>("/api/v1/invites/accept", { token });
