import { useEffect, useState } from "react";

/** Skeletons and loading text appear only after 150 ms so fast responses don't flash (Design.md §6). */
export const SKELETON_DELAY_MS = 150;

/** True once `active` has stayed true for `delayMs`; resets when it turns false. */
export function useDelayedFlag(active: boolean, delayMs: number = SKELETON_DELAY_MS): boolean {
  const [elapsed, setElapsed] = useState(false);
  useEffect(() => {
    if (!active) return;
    const timer = window.setTimeout(() => setElapsed(true), delayMs);
    return () => {
      window.clearTimeout(timer);
      setElapsed(false);
    };
  }, [active, delayMs]);
  return active && elapsed;
}
