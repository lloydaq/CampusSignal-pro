import { useMutation, useQueryClient } from "@tanstack/react-query";
import { MessagesSquare } from "lucide-react";
import { useId, useRef, useState, type RefObject } from "react";
import { NavLink, useSearchParams } from "react-router";

import { AudienceBadge } from "@/components/AudienceBadge";
import { Callout } from "@/components/Callout";
import { EmptyState } from "@/components/EmptyState";
import { ErrorState } from "@/components/ErrorState";
import { SubmitButton } from "@/components/SubmitButton";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { ListLoading, LoadMore } from "@/features/admin/list";
import { useCursorList } from "@/features/admin/useCursorList";
import { useMe } from "@/features/auth/session";
import { applyServerError } from "@/features/auth/serverErrors";
import { usePageTitle } from "@/lib/usePageTitle";
import { cn } from "@/lib/utils";

import { createPost, fetchFeed, type Feed, type Visibility } from "./api";
import { POST_MAX, communityKeys } from "./labels";
import { PostItem } from "./PostItem";

/** Design.md §5 screen 9: "What are people discussing?" College · My department. */
export function CommunityPage() {
  usePageTitle("Community");
  const me = useMe();
  const department = me.membership?.department ?? null;
  const [params] = useSearchParams();
  const feed: Feed = department && params.get("feed") === "department" ? "department" : "college";
  const { query, items } = useCursorList(communityKeys.feed(feed), (cursor, signal) => fetchFeed(feed, cursor, signal));
  const composer = useRef<HTMLTextAreaElement>(null);
  const [composing, setComposing] = useState(false);
  const startWriting = () => {
    setComposing(true);
    requestAnimationFrame(() => composer.current?.focus());
  };

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold text-fg sm:text-3xl">Community</h1>
      {department && (
        <nav aria-label="Feeds" className="-mx-4 overflow-x-auto border-b border-border px-4 sm:mx-0 sm:px-0">
          <ul className="flex gap-1">
            {(["college", "department"] as const).map((f) => (
              <li key={f}>
                <NavLink
                  to={f === "college" ? "/community" : "/community?feed=department"}
                  aria-current={feed === f ? "page" : undefined}
                  className={cn(
                    "relative flex h-10 items-center px-3 text-sm font-medium whitespace-nowrap pointer-coarse:min-h-11",
                    feed === f ? "text-primary after:absolute after:inset-x-2 after:bottom-0 after:h-0.75 after:rounded-sm after:bg-accent" : "text-muted hover:text-fg",
                  )}
                >
                  {f === "college" ? "College" : `My department · ${department.code}`}
                </NavLink>
              </li>
            ))}
          </ul>
        </nav>
      )}

      <Composer open={composing} onOpen={startWriting} onClose={() => setComposing(false)} textareaRef={composer} defaultVisibility={feed === "department" ? "DEPARTMENT" : department ? "DEPARTMENT" : "COLLEGE"} />

      {query.isPending ? (
        <ListLoading label="Loading posts" />
      ) : query.isError ? (
        <ErrorState title="Couldn't load posts." error={query.error} onRetry={() => void query.refetch()} retrying={query.isFetching} />
      ) : items.length === 0 ? (
        <EmptyState Icon={MessagesSquare} title="No posts yet. Start the first discussion.">
          <Button size="sm" variant="secondary" onClick={startWriting}>
            Write a post
          </Button>
        </EmptyState>
      ) : (
        <div className="space-y-4">
          <ul aria-label="Posts" className="divide-y divide-border overflow-hidden rounded-sm border border-border bg-surface">
            {items.map((post) => (
              <li key={post.id}>
                <PostItem post={post} />
              </li>
            ))}
          </ul>
          <LoadMore shown={items.length} hasMore={query.hasNextPage} loading={query.isFetchingNextPage} onLoad={() => void query.fetchNextPage()} />
        </div>
      )}
    </div>
  );
}

/**
 * Design.md §5 screen 10: collapsed until used; a character count, the audience chosen
 * explicitly (defaulting to the department) and shown as the badge the post will carry.
 */
function Composer({
  open,
  onOpen,
  onClose,
  textareaRef,
  defaultVisibility,
}: {
  open: boolean;
  onOpen: () => void;
  onClose: () => void;
  textareaRef: RefObject<HTMLTextAreaElement | null>;
  defaultVisibility: Visibility;
}) {
  const me = useMe();
  const department = me.membership?.department ?? null;
  const queryClient = useQueryClient();
  const [body, setBody] = useState("");
  const [visibility, setVisibility] = useState<Visibility>(defaultVisibility);
  const [error, setError] = useState<string | null>(null);
  const [posted, setPosted] = useState(false);
  const ids = { body: useId(), help: useId() };
  const create = useMutation({
    mutationFn: () => createPost({ body: body.trim(), visibility }),
    onSuccess: async (post) => {
      setBody("");
      setPosted(true);
      onClose();
      await queryClient.invalidateQueries({ queryKey: communityKeys.feed(post.visibility === "DEPARTMENT" ? "department" : "college") });
    },
    onError: (e) => setError(applyServerError(e, () => undefined, [], "You've posted 10 times in the last hour.")),
  });

  if (!open) {
    return (
      <div className="space-y-3">
        {posted && <Callout tone="success">Posted.</Callout>}
        <button
          type="button"
          onClick={() => {
            setPosted(false);
            onOpen();
          }}
          className="flex min-h-11 w-full items-center rounded-sm border border-border bg-surface px-4 py-3 text-left text-sm text-muted hover:border-border-strong"
        >
          Write a post…
        </button>
      </div>
    );
  }
  const tooLong = body.length > POST_MAX;
  return (
    <form
      noValidate
      aria-label="Write a post"
      className="space-y-3 rounded-sm border border-border bg-surface p-4"
      onSubmit={(event) => {
        event.preventDefault();
        setError(null);
        if (!body.trim()) {
          setError("Write something first.");
          return;
        }
        create.mutate();
      }}
    >
      <label htmlFor={ids.body} className="sr-only">
        Your post
      </label>
      <Textarea id={ids.body} ref={textareaRef} rows={4} maxLength={POST_MAX} value={body} aria-describedby={ids.help} onChange={(e) => setBody(e.target.value)} />
      <p id={ids.help} className={cn("text-sm", tooLong ? "text-danger-fg" : "text-muted")}>
        Plain text; links work. {body.length.toLocaleString("en-IN")} / 5,000
      </p>
      {department && (
        <fieldset className="space-y-1.5">
          <legend className="text-sm font-medium text-fg">Who can see it</legend>
          <div className="flex flex-wrap gap-x-4">
            {(["DEPARTMENT", "COLLEGE"] as const).map((v) => (
              <label key={v} className="flex min-h-11 items-center gap-2 text-sm">
                <input type="radio" name="visibility" value={v} checked={visibility === v} onChange={() => setVisibility(v)} className="size-4 accent-primary" />
                {v === "DEPARTMENT" ? `My department (${department.code})` : "The whole college"}
              </label>
            ))}
          </div>
        </fieldset>
      )}
      {error && <Callout tone="danger">{error}</Callout>}
      <div className="flex flex-wrap items-center gap-3">
        <span className="text-sm text-muted">
          Shows as <AudienceBadge department={visibility === "DEPARTMENT" ? department : null} />
        </span>
        <span className="ml-auto flex gap-2">
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <SubmitButton pending={create.isPending} pendingLabel="Posting…">
            Post
          </SubmitButton>
        </span>
      </div>
    </form>
  );
}
