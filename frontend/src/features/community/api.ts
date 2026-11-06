import type { Page } from "@/features/admin/api";
import type { DepartmentRef } from "@/features/auth/api";
import { apiGet, apiPost, apiRequest } from "@/lib/api";

/** Community posts, comments, reactions and reports (backend app/api/v1/community.py). */

const CAMPUS = "/api/v1/campus";

export type Visibility = "COLLEGE" | "DEPARTMENT";
export type ContentStatus = "VISIBLE" | "HIDDEN";
export type Feed = "college" | "department";
export type ReportReason = "HARASSMENT" | "SPAM" | "MISINFORMATION" | "PERSONAL_INFORMATION" | "OTHER";

export interface Author {
  name: string;
  kind: "STUDENT" | "FACULTY" | "STAFF";
}

export interface Post {
  id: string;
  body: string;
  visibility: Visibility;
  department: DepartmentRef | null;
  author: Author;
  status: ContentStatus;
  /** Only its author and moderators see a hidden post, and with it why. */
  hidden_reason: string | null;
  edited_at: string | null;
  created_at: string;
  reaction_count: number;
  comment_count: number;
  reacted: boolean;
  can_edit: boolean;
  can_delete: boolean;
  /** Comment and react: the post is visible and readable. */
  can_engage: boolean;
}

export interface Comment {
  id: string;
  body: string;
  author: Author;
  status: ContentStatus;
  hidden_reason: string | null;
  edited_at: string | null;
  created_at: string;
  can_edit: boolean;
  can_delete: boolean;
}

export function fetchFeed(feed: Feed, cursor: string | null, signal?: AbortSignal): Promise<Page<Post>> {
  const params = new URLSearchParams({ feed });
  if (cursor) params.set("cursor", cursor);
  return apiGet<Page<Post>>(`${CAMPUS}/posts?${params.toString()}`, signal);
}

export const fetchPost = (id: string, signal?: AbortSignal) => apiGet<Post>(`${CAMPUS}/posts/${id}`, signal);

export const createPost = (body: { body: string; visibility: Visibility }) => apiPost<Post>(`${CAMPUS}/posts`, body);

const send = <T>(method: string, path: string, body?: unknown) =>
  apiRequest<T>(path, { method, ...(body === undefined ? {} : { body: JSON.stringify(body), headers: { "Content-Type": "application/json" } }) });

export const editPost = (id: string, body: string) => send<Post>("PATCH", `${CAMPUS}/posts/${id}`, { body });

export const deletePost = (id: string) => send<undefined>("DELETE", `${CAMPUS}/posts/${id}`);

export function fetchComments(postId: string, cursor: string | null, signal?: AbortSignal): Promise<Page<Comment>> {
  const query = cursor ? `?cursor=${encodeURIComponent(cursor)}` : "";
  return apiGet<Page<Comment>>(`${CAMPUS}/posts/${postId}/comments${query}`, signal);
}

export const addComment = (postId: string, body: string) => apiPost<Comment>(`${CAMPUS}/posts/${postId}/comments`, { body });

export const editComment = (id: string, body: string) => send<Comment>("PATCH", `${CAMPUS}/comments/${id}`, { body });

export const deleteComment = (id: string) => send<undefined>("DELETE", `${CAMPUS}/comments/${id}`);

export interface ReactionState {
  reacted: boolean;
  reaction_count: number;
}

/** "Helpful" on (PUT) or off (DELETE); each is idempotent, so a double tap can't duplicate. */
export const setHelpful = (postId: string, on: boolean) => send<ReactionState>(on ? "PUT" : "DELETE", `${CAMPUS}/posts/${postId}/reaction`);

export const reportContent = (body: { post_id?: string; comment_id?: string; reason: ReportReason; note?: string }) =>
  apiPost<{ id: string; status: string }>(`${CAMPUS}/reports`, body);

// --- moderation (COMMUNITY-007; Manage → Moderation) ---

export type ReportStatus = "OPEN" | "ACTIONED" | "DISMISSED";

/** One report in the moderation queue. Who reported it is never sent. */
export interface ModerationItem {
  id: string;
  reason: ReportReason;
  note: string | null;
  status: ReportStatus;
  created_at: string;
  handled_at: string | null;
  /** Open reports on the same post or comment, this one included. */
  open_reports: number;
  content: {
    type: "post" | "comment";
    post_id: string;
    comment_id: string | null;
    body: string;
    author: Author;
    visibility: Visibility;
    department: DepartmentRef | null;
    status: ContentStatus;
    hidden_reason: string | null;
  };
}

export function fetchModerationQueue(status: ReportStatus, cursor: string | null, signal?: AbortSignal): Promise<Page<ModerationItem>> {
  const params = new URLSearchParams({ status });
  if (cursor) params.set("cursor", cursor);
  return apiGet<Page<ModerationItem>>(`${CAMPUS}/moderation/reports?${params.toString()}`, signal);
}

/** HIDE needs the reason its author will read; DISMISS's reason goes to the audit log only. */
export const resolveReport = (id: string, body: { action: "HIDE" | "DISMISS"; reason?: string }) =>
  apiPost<{ action: string; closed_reports: number }>(`${CAMPUS}/moderation/reports/${id}/resolve`, body);
