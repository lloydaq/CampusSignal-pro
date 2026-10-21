import AxeBuilder from "@axe-core/playwright";
import { expect, type Page, type Route } from "@playwright/test";

/** Synthetic backend states. Each maps to what the real FastAPI endpoints return. */
export type BackendState =
  | "ready"
  | "migrations_pending"
  | "database_unreachable"
  | "api_unreachable"
  | "server_error";

function json(route: Route, status: number, body: unknown, requestId: string) {
  return route.fulfill({
    status,
    contentType: "application/json",
    headers: { "X-Request-ID": requestId },
    body: JSON.stringify(body),
  });
}

function notReady(route: Route, details: Record<string, string>) {
  return json(
    route,
    503,
    { error: { code: "not_ready", message: "The service is not ready.", details, request_id: "e2e-503" } },
    "e2e-503",
  );
}

/**
 * Route /healthz and /readyz to a synthetic state. Any other API call fails the test,
 * so the shell can't silently depend on endpoints that don't exist yet.
 */
export async function mockBackend(page: Page, state: BackendState): Promise<void> {
  await page.route("**/api/**", (route) => route.abort("blockedbyclient"));

  await page.route("**/healthz", (route) => {
    if (state === "api_unreachable") return route.abort("connectionrefused");
    if (state === "server_error") {
      return json(
        route,
        500,
        {
          error: {
            code: "internal_error",
            message: "Something went wrong on our side.",
            details: null,
            request_id: "e2e-req-500",
          },
        },
        "e2e-req-500",
      );
    }
    return json(route, 200, { status: "ok" }, "e2e-health");
  });

  await page.route("**/readyz", (route) => {
    if (state === "migrations_pending") return notReady(route, { migrations: "pending" });
    if (state === "database_unreachable") return notReady(route, { database: "unreachable" });
    return json(route, 200, { status: "ready" }, "e2e-ready");
  });
}

/** WCAG 2.0/2.1/2.2 A and AA rules (PRD NFR-A11Y-001). Fails listing each violation. */
export async function expectNoAxeViolations(page: Page): Promise<void> {
  const results = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"])
    .analyze();
  const summary = results.violations.map((v) => `${v.id} (${v.impact ?? "n/a"}): ${v.nodes.length} node(s) — ${v.help}`);
  expect(summary).toEqual([]);
}

/** Row in the status list, e.g. statusRow(page, "Database"). */
export function statusRow(page: Page, name: "API" | "Database") {
  return page.locator("dl > div").filter({ has: page.locator("dt", { hasText: name }) });
}
