import { useQueryClient, type InfiniteData } from "@tanstack/react-query";

import type { Page } from "@/features/admin/api";

import type { Post } from "./api";
import { communityKeys } from "./labels";

/**
 * After a change to a post: replace it wherever it is cached (its page and any loaded feed
 * page), without refetching whole feeds for a reaction. Deleted posts drop out.
 */
export function usePostChanged() {
  const queryClient = useQueryClient();
  return (postId: string, next: Post | null) => {
    if (next) queryClient.setQueryData(communityKeys.post(postId), next);
    else queryClient.removeQueries({ queryKey: communityKeys.post(postId) });
    queryClient.setQueriesData<InfiniteData<Page<Post>>>({ queryKey: [...communityKeys.all, "feed"] }, (data) =>
      data
        ? {
            ...data,
            pages: data.pages.map((page) => ({
              ...page,
              items: next ? page.items.map((p) => (p.id === postId ? next : p)) : page.items.filter((p) => p.id !== postId),
            })),
          }
        : data,
    );
  };
}
