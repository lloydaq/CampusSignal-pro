import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft } from "lucide-react";
import { useId, useState } from "react";
import { Link, useNavigate, useParams } from "react-router";

import { Callout } from "@/components/Callout";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import { ErrorState } from "@/components/ErrorState";
import { SubmitButton } from "@/components/SubmitButton";
import { Textarea } from "@/components/ui/textarea";
import { errorText } from "@/features/admin/labels";
import { ListLoading, LoadMore } from "@/features/admin/list";
import { useCursorList } from "@/features/admin/useCursorList";
import { applyServerError } from "@/features/auth/serverErrors";
import { ApiError } from "@/lib/api";
import { usePageTitle } from "@/lib/usePageTitle";
import { cn } from "@/lib/utils";

import { addComment, deleteComment, editComment, fetchComments, fetchPost, type Comment, type Post } from "./api";
import { COMMENT_MAX, communityKeys } from "./labels";
import { LinkifiedText } from "./LinkifiedText";
import { ActionsMenu, Byline, EditBody, PostItem, When } from "./PostItem";
import { ReportDialog } from "./ReportDialog";

/** Design.md §5 screen 10: the post, its comments oldest first, a comment box at the bottom. */
export function PostPage() {
  const { postId = "" } = useParams();
  const navigate = useNavigate();
  const post = useQuery({ queryKey: communityKeys.post(postId), queryFn: ({ signal }) => fetchPost(postId, signal) });
  usePageTitle(post.data ? `Post by ${post.data.author.name}` : "Post");

  return (
    <div className="mx-auto max-w-reading space-y-6">
      <Link to="/community" className="inline-flex items-center gap-1.5 text-sm text-muted hover:text-fg">
        <ArrowLeft aria-hidden="true" strokeWidth={1.5} className="size-4" />
        Community
      </Link>
      <h1 className="sr-only">Post</h1>
      {post.isPending ? (
        <ListLoading label="Loading the post" />
      ) : post.isError ? (
        post.error instanceof ApiError && post.error.status === 404 ? (
          <Callout tone="info" title="This post isn't available">
            <p>It may have been deleted or hidden, or it's for another department.</p>
          </Callout>
        ) : (
          <ErrorState title="Couldn't load the post." error={post.error} onRetry={() => void post.refetch()} retrying={post.isFetching} />
        )
      ) : (
        <>
          <div className="rounded-sm border border-border bg-surface">
            <PostItem post={post.data} detail onDeleted={() => void navigate("/community", { replace: true })} />
          </div>
          <Comments post={post.data} />
        </>
      )}
    </div>
  );
}

function Comments({ post }: { post: Post }) {
  const headingId = useId();
  const { query, items } = useCursorList(communityKeys.comments(post.id), (cursor, signal) => fetchComments(post.id, cursor, signal));
  return (
    <section aria-labelledby={headingId} className="space-y-4">
      <h2 id={headingId} className="text-lg font-semibold text-fg">
        Comments
      </h2>
      {query.isPending ? (
        <ListLoading label="Loading comments" />
      ) : query.isError ? (
        <ErrorState title="Couldn't load the comments." error={query.error} onRetry={() => void query.refetch()} retrying={query.isFetching} />
      ) : items.length === 0 ? (
        <p className="text-sm text-muted">{post.can_engage ? "No comments yet." : "No comments."}</p>
      ) : (
        <>
          <ol className="space-y-4">
            {items.map((c) => (
              <li key={c.id}>
                <CommentItem comment={c} post={post} />
              </li>
            ))}
          </ol>
          <LoadMore shown={items.length} hasMore={query.hasNextPage} loading={query.isFetchingNextPage} onLoad={() => void query.fetchNextPage()} />
        </>
      )}
      {post.can_engage && <CommentForm post={post} />}
    </section>
  );
}

function useCommentsChanged(post: Post) {
  const queryClient = useQueryClient();
  return () =>
    Promise.all([
      queryClient.invalidateQueries({ queryKey: communityKeys.comments(post.id) }),
      // The post's comment count changes with them.
      queryClient.invalidateQueries({ queryKey: communityKeys.post(post.id) }),
      queryClient.invalidateQueries({ queryKey: [...communityKeys.all, "feed"] }),
    ]);
}

function CommentItem({ comment, post }: { comment: Comment; post: Post }) {
  const refresh = useCommentsChanged(post);
  const [editing, setEditing] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [reporting, setReporting] = useState(false);
  const [reported, setReported] = useState(false);
  const remove = useMutation({
    mutationFn: () => deleteComment(comment.id),
    onSuccess: async () => {
      setDeleting(false);
      await refresh();
    },
  });
  const actions = [
    ...(comment.can_edit ? [{ label: "Edit", onSelect: () => setEditing(true) }] : []),
    ...(comment.can_delete ? [{ label: "Delete", onSelect: () => setDeleting(true), danger: true }] : []),
    ...(!comment.can_delete && comment.status === "VISIBLE" && post.status === "VISIBLE" && !reported ? [{ label: "Report", onSelect: () => setReporting(true) }] : []),
  ];
  return (
    <article aria-label={`Comment by ${comment.author.name}`} className={cn("space-y-2 border-l-2 pl-3", comment.status === "HIDDEN" ? "border-warning" : "border-border")}>
      <div className="flex items-start justify-between gap-3">
        <Byline author={comment.author}>
          <When iso={comment.created_at} edited={comment.edited_at !== null} />
        </Byline>
        <ActionsMenu label="Comment actions" actions={actions} />
      </div>
      {comment.status === "HIDDEN" && (
        <Callout tone="warning" title="Hidden by a moderator">
          <p>Reason: {comment.hidden_reason}</p>
        </Callout>
      )}
      {editing ? (
        <EditBody
          initial={comment.body}
          max={COMMENT_MAX}
          label="Edit your comment"
          save={(body) => editComment(comment.id, body)}
          onSaved={() => {
            setEditing(false);
            void refresh();
          }}
          onCancel={() => setEditing(false)}
        />
      ) : (
        <LinkifiedText text={comment.body} className="text-sm whitespace-pre-line text-fg" />
      )}
      {reported && <p className="text-sm text-muted">Reported. Moderators will look at it.</p>}
      {deleting && (
        <ConfirmDialog
          title="Delete this comment?"
          description="It disappears for everyone. This can't be undone."
          confirmLabel="Delete comment"
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
          target={{ comment_id: comment.id }}
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

function CommentForm({ post }: { post: Post }) {
  const refresh = useCommentsChanged(post);
  const [body, setBody] = useState("");
  const [error, setError] = useState<string | null>(null);
  const id = useId();
  const add = useMutation({
    mutationFn: () => addComment(post.id, body.trim()),
    onSuccess: async () => {
      setBody("");
      await refresh();
    },
    onError: (e) => setError(applyServerError(e, () => undefined, [], "You've commented 60 times in the last hour.")),
  });
  return (
    <form
      noValidate
      aria-label="Add a comment"
      className="space-y-2"
      onSubmit={(event) => {
        event.preventDefault();
        setError(null);
        if (!body.trim()) {
          setError("Write a comment first.");
          return;
        }
        add.mutate();
      }}
    >
      <label htmlFor={id} className="block text-sm font-medium text-fg">
        Comment
      </label>
      <Textarea id={id} rows={3} maxLength={COMMENT_MAX} value={body} onChange={(e) => setBody(e.target.value)} />
      {error && <Callout tone="danger">{error}</Callout>}
      <SubmitButton pending={add.isPending} pendingLabel="Posting…" variant="secondary">
        Post comment
      </SubmitButton>
    </form>
  );
}
