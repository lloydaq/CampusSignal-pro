import { lazy, type ComponentType } from "react";

/**
 * Route-level code splitting (NFR-PERF-002): role-specific sections load on first visit, so
 * a student's first load doesn't carry Manage, Platform or Teaching. A section's screens come
 * from one module, so they arrive as one chunk.
 */
export function lazyNamed<M extends Record<string, unknown>, K extends keyof M>(load: () => Promise<M>, name: K) {
  return lazy(() => load().then((m) => ({ default: m[name] as ComponentType })));
}
