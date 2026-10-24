import { useInfiniteQuery, type QueryKey } from "@tanstack/react-query";

import type { Page } from "./api";

/** A cursor-paginated Manage list (Design.md §6 Pagination: "Load more", no page numbers). */
export function useCursorList<T>(queryKey: QueryKey, fetchPage: (cursor: string | null, signal: AbortSignal) => Promise<Page<T>>) {
  const query = useInfiniteQuery({
    queryKey,
    queryFn: ({ pageParam, signal }) => fetchPage(pageParam, signal),
    initialPageParam: null as string | null,
    getNextPageParam: (last) => last.next_cursor,
  });
  const items = query.data?.pages.flatMap((page) => page.items) ?? [];
  return { query, items };
}
