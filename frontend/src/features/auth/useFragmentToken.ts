import { useEffect, useState } from "react";

/**
 * The `#token=…` from an emailed link. Tokens travel in the fragment so they never reach
 * server logs or Referer headers (architecture.md §15); the fragment is then removed from the
 * address bar so the token doesn't linger in history or get shared by copying the URL.
 */
export function useFragmentToken(): string | null {
  const [token] = useState(() => {
    const match = /^#(?:.*&)?token=([^&]+)/.exec(window.location.hash);
    if (!match?.[1]) return null;
    try {
      return decodeURIComponent(match[1]);
    } catch {
      return null;
    }
  });
  useEffect(() => {
    if (window.location.hash) {
      window.history.replaceState(window.history.state, "", window.location.pathname + window.location.search);
    }
  }, []);
  return token;
}
