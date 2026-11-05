import type { Author, Feed, ReportReason } from "./api";

export const communityKeys = {
  all: ["community"] as const,
  feed: (feed: Feed) => ["community", "feed", feed] as const,
  post: (id: string) => ["community", "post", id] as const,
  comments: (postId: string) => ["community", "comments", postId] as const,
};

export const POST_MAX = 5000;
export const COMMENT_MAX = 2000;

export const REPORT_REASONS: { value: ReportReason; label: string }[] = [
  { value: "HARASSMENT", label: "Harassment or bullying" },
  { value: "SPAM", label: "Spam" },
  { value: "MISINFORMATION", label: "False information" },
  { value: "PERSONAL_INFORMATION", label: "Someone's personal information" },
  { value: "OTHER", label: "Something else" },
];

/** COMMUNITY-009: faculty and staff wear a role badge; students none. */
export function roleLabel(author: Author): string | null {
  return author.kind === "FACULTY" ? "Faculty" : author.kind === "STAFF" ? "Staff" : null;
}

/** Up to two initials for the avatar (Design.md §3.3). */
export function initials(name: string): string {
  const words = name.trim().split(/\s+/).filter(Boolean);
  const letters = words.length > 1 ? [words[0]![0], words[words.length - 1]![0]] : [words[0]?.[0]];
  return letters.filter(Boolean).join("").toUpperCase();
}

/** "5 min ago", "3 h ago", then the date: posts are read in the moment. */
export function relativeTime(iso: string, now: Date = new Date()): string {
  const minutes = Math.floor((now.getTime() - new Date(iso).getTime()) / 60_000);
  if (minutes < 1) return "Just now";
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours} h ago`;
  const days = Math.floor(hours / 24);
  return days === 1 ? "Yesterday" : `${days} days ago`;
}
