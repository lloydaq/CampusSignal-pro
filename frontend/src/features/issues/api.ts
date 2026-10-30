import type { Page } from "@/features/admin/api";
import { apiGet, apiPost } from "@/lib/api";

/** Campus issues (backend app/api/v1/issues.py; architecture.md §11.1). */

const ISSUES = "/api/v1/campus/issues";

export type IssueCategory =
  | "CLASSROOM_EQUIPMENT"
  | "INFRASTRUCTURE"
  | "WATER_SANITATION"
  | "ELECTRICAL"
  | "NETWORK"
  | "LIBRARY"
  | "LABORATORY"
  | "OTHER";
export type IssueStatus = "SUBMITTED" | "ACKNOWLEDGED" | "IN_PROGRESS" | "RESOLVED" | "REJECTED";
export type IssueScope = "mine" | "assigned" | "queue";

export interface IssueSummary {
  id: string;
  title: string;
  category: IssueCategory;
  location: string;
  room: string | null;
  status: IssueStatus;
  reporter_name: string;
  assignee_name: string | null;
  created_at: string;
  updated_at: string;
}

export interface IssueUpdate {
  id: string;
  kind: "CREATED" | "STATUS" | "ASSIGNMENT" | "COMMENT";
  from_status: IssueStatus | null;
  to_status: IssueStatus | null;
  body: string | null;
  is_internal: boolean;
  actor_name: string | null;
  assignee_name: string | null;
  created_at: string;
}

/** What the viewer may do now, decided by the server's policies. Hiding the rest is UX only. */
export interface IssueActions {
  transitions: { to_status: IssueStatus; needs_note: boolean }[];
  assign: boolean;
  comment: boolean;
  comment_internal: boolean;
}

export interface Issue extends IssueSummary {
  description: string;
  resolved_at: string | null;
  version: number;
  /** ISSUE-006: the original's status and resolution time only; `id` only if the viewer may open it. */
  duplicate_of: { id: string | null; status: IssueStatus; resolved_at: string | null } | null;
  updates: IssueUpdate[];
  actions: IssueActions;
}

/** Coordinator queue filters (ISSUE-009); empty values mean "any". */
export interface QueueFilters {
  status: IssueStatus | "";
  category: IssueCategory | "";
  assigneeId: string;
  olderThanDays: string;
}

export function fetchIssues(scope: IssueScope, cursor: string | null, signal?: AbortSignal, filters?: QueueFilters): Promise<Page<IssueSummary>> {
  const params = new URLSearchParams({ scope });
  if (filters?.status) params.set("status", filters.status);
  if (filters?.category) params.set("category", filters.category);
  if (filters?.assigneeId) params.set("assignee_id", filters.assigneeId);
  if (filters?.olderThanDays) params.set("older_than_days", filters.olderThanDays);
  if (cursor) params.set("cursor", cursor);
  return apiGet<Page<IssueSummary>>(`${ISSUES}?${params.toString()}`, signal);
}

export const fetchIssue = (id: string, signal?: AbortSignal) => apiGet<Issue>(`${ISSUES}/${id}`, signal);

export interface IssueInput {
  category: IssueCategory;
  title: string;
  description: string;
  location: string;
  room: string | null;
}

export function createIssue(input: IssueInput): Promise<Issue> {
  const { room, ...rest } = input;
  return apiPost<Issue>(ISSUES, room ? { ...rest, room } : rest);
}

export const transitionIssue = (id: string, body: { to_status: IssueStatus; note?: string; duplicate_of_id?: string; version: number }) =>
  apiPost<Issue>(`${ISSUES}/${id}/transitions`, body);

export const commentOnIssue = (id: string, body: { body: string; is_internal: boolean }) => apiPost<Issue>(`${ISSUES}/${id}/updates`, body);

export const assignIssue = (id: string, body: { assignee_id: string | null; version: number }) => apiPost<Issue>(`${ISSUES}/${id}/assignment`, body);

/** Someone an issue can be assigned to: ACTIVE faculty and staff, names only. */
export interface Assignee {
  id: string;
  name: string;
  kind: "FACULTY" | "STAFF";
}

export function fetchAssignees(query: string, cursor: string | null, signal?: AbortSignal): Promise<Page<Assignee>> {
  const params = new URLSearchParams();
  if (query) params.set("query", query);
  if (cursor) params.set("cursor", cursor);
  const text = params.toString();
  return apiGet<Page<Assignee>>(`/api/v1/campus/assignees${text ? `?${text}` : ""}`, signal);
}
