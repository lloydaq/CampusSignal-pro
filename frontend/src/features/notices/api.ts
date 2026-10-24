import type { Page } from "@/features/admin/api";
import type { DepartmentRef } from "@/features/auth/api";
import { apiGet, apiPost, apiRequest } from "@/lib/api";

/** Notices and department pages (backend app/api/v1/notices.py, campus.py; architecture.md §11.1). */

const NOTICES = "/api/v1/campus/notices";

export type Category = "ACADEMIC" | "EXAMINATION" | "ADMINISTRATIVE" | "EVENT" | "FACILITIES" | "GENERAL";
export type Priority = "NORMAL" | "HIGH" | "URGENT";
export type Scope = "COLLEGE" | "DEPARTMENT";
export type NoticeStatus = "DRAFT" | "PUBLISHED" | "WITHDRAWN";

export interface NoticeSummary {
  id: string;
  title: string;
  excerpt: string;
  category: Category;
  priority: Priority;
  scope: Scope;
  department: DepartmentRef | null;
  status: NoticeStatus;
  pinned: boolean;
  expired: boolean;
  published_at: string | null;
  expires_at: string | null;
  edited_at: string | null;
  created_at: string;
  can_manage: boolean;
}

export interface Notice extends NoticeSummary {
  body: string;
  version: number;
  author_name: string | null;
}

export interface NoticeFilters {
  status: NoticeStatus;
  past: boolean;
  category: Category | "";
  departmentId: string;
}

export function fetchNotices(filters: NoticeFilters, cursor: string | null, signal?: AbortSignal): Promise<Page<NoticeSummary>> {
  const params = new URLSearchParams();
  if (filters.status !== "PUBLISHED") params.set("status", filters.status);
  if (filters.past) params.set("past", "true");
  if (filters.category) params.set("category", filters.category);
  if (filters.departmentId) params.set("department_id", filters.departmentId);
  if (cursor) params.set("cursor", cursor);
  const query = params.toString();
  return apiGet<Page<NoticeSummary>>(`${NOTICES}${query ? `?${query}` : ""}`, signal);
}

export const fetchNotice = (id: string, signal?: AbortSignal) => apiGet<Notice>(`${NOTICES}/${id}`, signal);

export interface NoticeInput {
  title: string;
  body: string;
  category: Category;
  priority: Priority;
  expires_at: string | null;
}

export const createNotice = (body: NoticeInput & { scope: Scope; department_id?: string; publish: boolean }) =>
  apiPost<Notice>(NOTICES, body);

export const updateNotice = (id: string, body: Partial<NoticeInput> & { version: number }) =>
  apiRequest<Notice>(`${NOTICES}/${id}`, { method: "PATCH", body: JSON.stringify(body), headers: { "Content-Type": "application/json" } });

export const publishNotice = (id: string, version: number) => apiPost<Notice>(`${NOTICES}/${id}/publish`, { version });

export const withdrawNotice = (id: string, reason: string) => apiPost<Notice>(`${NOTICES}/${id}/withdraw`, { reason });

export interface DepartmentPage {
  id: string;
  code: string;
  name: string;
  description: string;
  archived: boolean;
  admins: string[];
}

export const fetchDepartmentPage = (id: string, signal?: AbortSignal) => apiGet<DepartmentPage>(`/api/v1/campus/departments/${id}`, signal);

export const updateDepartmentDescription = (id: string, description: string) =>
  apiRequest<DepartmentPage>(`/api/v1/campus/departments/${id}`, {
    method: "PATCH",
    body: JSON.stringify({ description }),
    headers: { "Content-Type": "application/json" },
  });
