import { useQueryClient } from "@tanstack/react-query";

import type { Issue } from "./api";
import { issueKeys } from "./labels";

/** Store the changed issue and refresh the lists that may show it. */
export function useIssueSaved(issueId: string) {
  const queryClient = useQueryClient();
  return async (updated: Issue) => {
    queryClient.setQueryData(issueKeys.one(issueId), updated);
    await queryClient.invalidateQueries({ queryKey: [...issueKeys.all, "list"] });
  };
}
