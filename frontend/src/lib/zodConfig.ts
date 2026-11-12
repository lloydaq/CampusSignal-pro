import { z } from "zod";

/**
 * The production CSP has no 'unsafe-eval' (architecture.md §18, NFR-SEC-001). Zod would probe
 * `new Function` for its fast path; jitless skips that, so the browser reports no violation.
 * Imported first in main.tsx, before any schema is built or parsed.
 */
z.config({ jitless: true });
