import { useMutation } from "@tanstack/react-query";
import { Ellipsis, MessageSquare, ThumbsUp } from "lucide-react";
import { useEffect, useId, useRef, useState, type ReactNode } from "react";
import { Link } from "react-router";

import { AudienceBadge } from "@/components/AudienceBadge";
import { Callout } from "@/components/Callout";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { errorText } from "@/features/admin/labels";
import { useCollegeTimezone } from "@/features/admin/tabs";
import { formatDateTime } from "@/lib/datetime";
import { cn } from "@/lib/utils";

import { deletePost, editPost, setHelpful, type Author, type Post } from "./api";
import { usePostChanged } from "./cache";
import { POST_MAX, initials, relativeTime, roleLabel } from "./labels";
import { LinkifiedText } from "./LinkifiedText";
import { ReportDialog } from "./ReportDialog";

/** Avatar (initials), name, role badge for faculty and staff (Design.md §3.3, COMMUNITY-009). */
export function Byline({ author, children }: { author: Author; children?: ReactNode }) {
  const role = roleLabel(author);
  return (
    <div className="flex min-w-0 items-center gap-2.5">
      <span aria-hidden="true" className="flex size-8 shrink-0 items-center justify-center rounded-full bg-surface-sunken text-xs font-semibold text-muted">
        {initials(author.name)}
      </span>
      <div className="flex min-w-0 flex-wrap items-center gap-x-1.5 gap-y-0.5 text-sm">
        <span className="font-medium text-fg">{author.name}</span>
        {role && <span className="rounded-sm bg-surface-sunken px-1.5 py-0.5 text-xs font-medium text-muted">{role}</span>}
        {children}
      </div>
    </div>
  );
}

export function When({ iso, edited }: { iso: string; edited: boolean }) {
  const timeZone = useCollegeTimezone();
  return (
    <span className="text-xs text-subtle">
      <time dateTime={iso} title={formatDateTime(iso, timeZone)}>
        {relativeTime(iso)}
      </time>
      {edited && " · edited"}
    </span>
  );
}

/** A disclosure of a post's or comment's actions (Report; Edit and Delete for its author). */
export function ActionsMenu({ label, actions }: { label: string; actions: { label: string; onSelect: () => void; danger?: boolean }[] }) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const menuId = useId();
  useEffect(() => {
    if (!open) return;
    const close = (event: MouseEvent | KeyboardEvent) => {
      if (event instanceof KeyboardEvent ? event.key === "Escape" : !ref.current?.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", close);
    return () => {
      document.removeEventListener("mousedown", close);
      document.removeEventListener("keydown", close);
    };
  }, [open]);
  if (actions.length === 0) return null;
  return (
    <div ref={ref} className="relative">
      <Button variant="ghost" size="sm" aria-label={label} aria-expanded={open} aria-controls={menuId} onClick={() => setOpen((o) => !o)}>
        <Ellipsis aria-hidden="true" strokeWidth={1.5} />
      </Button>
      {open && (
        <ul id={menuId} className="absolute top-full right-0 z-10 mt-1 min-w-36 rounded-sm border border-border bg-surface py-1 shadow-overlay">
          {actions.map((a) => (
            <li key={a.label}>
              <button
                type="button"
                className={cn("flex min-h-10 w-full items-center px-3 text-left text-sm hover:bg-surface-sunken pointer-coarse:min-h-11", a.danger ? "text-danger-fg" : "text-fg")}
                onClick={() => {
                  setOpen(false);
                  a.onSelect();
                }}
              >
                {a.label}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

/**
 * Design.md §5 screens 9–10, PostItem: the social treatment, never the "Official" one notices
 * carry (COMMUNITY-009). Every action shown is one the server said this person may take.
 */
export function PostItem({ post, detail = false, onDeleted }: { post: Post; detail?: boolean; onDeleted?: () => void }) {
  const changed = usePostChanged();
  const [editing, setEditing] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [reporting, setReporting] = useState(false);
  const [reported, setReported] = useState(false);
  const helpful = useMutation({
    mutationFn: () => setHelpful(post.id, !post.reacted),
    onSuccess: (state) => changed(post.id, { ...post, reacted: state.reacted, reaction_count: state.reaction_count }),
  });
  const remove = useMutation({
    mutationFn: () => deletePost(post.id),
    onSuccess: () => {
      setDeleting(false);
      changed(post.id, null);
      onDeleted?.();
    },
  });
  const actions = [
    ...(post.can_edit ? [{ label: "Edit", onSelect: () => setEditing(true) }] : []),
    ...(post.can_delete ? [{ label: "Delete", onSelect: () => setDeleting(true), danger: true }] : []),
    // Anyone but the author may report visible content (the server says no otherwise).
    ...(!post.can_delete && post.status === "VISIBLE" && !reported ? [{ label: "Report", onSelect: () => setReporting(true) }] : []),
  ];
  const postLink = `/community/posts/${post.id}`;

  return (
    <article aria-label={`Post by ${post.author.name}`} className="space-y-3 px-4 py-4">
      <div className="flex items-start justify-between gap-3">
        <Byline author={post.author}>
          <AudienceBadge department={post.visibility === "DEPARTMENT" ? post.department : null} />
        </Byline>
        <ActionsMenu label="Post actions" actions={actions} />
      </div>
      {post.status === "HIDDEN" && (
        <Callout tone="warning" title="Hidden by a moderator">
          <p>
            {post.can_delete ? "Only you and moderators can see it." : "Only its author and moderators can see it."} Reason: {post.hidden_reason}
          </p>
        </Callout>
      )}
      {editing ? (
        <EditBody initial={post.body} max={POST_MAX} label="Edit your post" save={(body) => editPost(post.id, body)} onSaved={(p) => { changed(post.id, p); setEditing(false); }} onCancel={() => setEditing(false)} />
      ) : (
        <LinkifiedText text={post.body} className={cn("text-base whitespace-pre-line text-fg", !detail && "line-clamp-6")} />
      )}
      {reported && <Callout tone="success">Thanks. Moderators will look at it.</Callout>}
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
        {post.can_engage || post.reaction_count > 0 ? (
          <Button
            variant="ghost"
            size="sm"
            aria-pressed={post.reacted}
            disabled={!post.can_engage || helpful.isPending}
            onClick={() => helpful.mutate()}
            className={cn(post.reacted && "text-primary")}
          >
            <ThumbsUp aria-hidden="true" strokeWidth={1.5} className={cn(post.reacted && "fill-primary-subtle")} />
            Helpful{post.reaction_count > 0 && <span className="tabular-nums"> · {post.reaction_count}</span>}
          </Button>
        ) : null}
        {detail ? (
          <span className="inline-flex items-center gap-1.5 text-sm text-muted">
            <MessageSquare aria-hidden="true" strokeWidth={1.5} className="size-4" />
            {post.comment_count === 1 ? "1 comment" : `${post.comment_count} comments`}
          </span>
        ) : (
          <Link to={postLink} className="inline-flex min-h-8 items-center gap-1.5 rounded-sm px-2 text-sm text-muted hover:bg-surface-sunken hover:text-fg pointer-coarse:min-h-11">
            <MessageSquare aria-hidden="true" strokeWidth={1.5} className="size-4" />
            {post.comment_count === 0 ? "Comment" : post.comment_count === 1 ? "1 comment" : `${post.comment_count} comments`}
          </Link>
        )}
        <span className="ml-auto">
          {detail ? <When iso={post.created_at} edited={post.edited_at !== null} /> : <Link to={postLink} className="hover:underline"><When iso={post.created_at} edited={post.edited_at !== null} /></Link>}
        </span>
      </div>
      {helpful.isError && <p className="text-sm text-danger-fg">{errorText(helpful.error)}</p>}
      {deleting && (
        <ConfirmDialog
          title="Delete this post?"
          description="It disappears for everyone, with its comments. This can't be undone."
          confirmLabel="Delete post"
          pendingLabel="Deleting…"
          pending={remove.isPending}
          error={remove.isError ? errorText(remove.error) : null}
          onConfirm={() => remove.mutate()}
          onCancel={() => {
            setDeleting(false);
            remove.reset();
          }}
        />
      )}
      {reporting && (
        <ReportDialog
          target={{ post_id: post.id }}
          onDone={() => {
            setReporting(false);
            setReported(true);
          }}
          onCancel={() => setReporting(false)}
        />
      )}
    </article>
  );
}

/** Inline editing for a post or a comment: same limits as writing it. */
export function EditBody<T>({
  initial,
  max,
  label,
  save,
  onSaved,
  onCancel,
}: {
  initial: string;
  max: number;
  label: string;
  save: (body: string) => Promise<T>;
  onSaved: (saved: T) => void;
  onCancel: () => void;
}) {
  const [body, setBody] = useState(initial);
  const [empty, setEmpty] = useState(false);
  const id = useId();
  const mutation = useMutation({ mutationFn: save, onSuccess: onSaved });
  return (
    <form
      noValidate
      onSubmit={(event) => {
        event.preventDefault();
        if (!body.trim()) {
          setEmpty(true);
          return;
        }
        mutation.mutate(body.trim());
      }}
      className="space-y-2"
    >
      <label htmlFor={id} className="sr-only">
        {label}
      </label>
      <Textarea id={id} rows={4} maxLength={max} value={body} aria-invalid={empty || undefined} onChange={(e) => { setBody(e.target.value); setEmpty(false); }} />
      {empty && <p className="text-sm text-danger-fg">Write something, or cancel.</p>}
      {mutation.isError && <p className="text-sm text-danger-fg">{errorText(mutation.error)}</p>}
      <div className="flex gap-2">
        <Button type="submit" size="sm" disabled={mutation.isPending}>
          {mutation.isPending ? "Saving…" : "Save"}
        </Button>
        <Button type="button" size="sm" variant="ghost" onClick={onCancel}>
          Cancel
        </Button>
      </div>
    </form>
  );
}
