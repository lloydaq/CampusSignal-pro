import { expect, test, type Page } from "@playwright/test";

import { mockAcademicApi } from "./academicApi";
import { mockCommunityApi } from "./communityApi";
import { mockManageApi } from "./manageApi";
import { mockNoticesApi } from "./noticesApi";
import { mockAuthApi } from "./support";

/**
 * NFR-SEC-001/002 (Phase 9a): the built app runs under the Content-Security-Policy the proxy
 * will send (architecture.md §18; keep the two in step): only same-origin scripts, styles,
 * fonts and API calls, no inline script, no framing. Every document response here carries the
 * header, and any violation fails the test.
 */
export const CSP = [
  "default-src 'self'",
  "script-src 'self'",
  "style-src 'self'",
  "img-src 'self' data:",
  "font-src 'self'",
  "connect-src 'self'",
  "object-src 'none'",
  "base-uri 'self'",
  "form-action 'self'",
  "frame-ancestors 'none'",
].join("; ");

async function withCsp(page: Page): Promise<string[]> {
  const violations: string[] = [];
  await page.exposeFunction("reportCspViolation", (text: string) => violations.push(text));
  await page.addInitScript(() => {
    document.addEventListener("securitypolicyviolation", (e) => {
      void (window as unknown as { reportCspViolation: (t: string) => Promise<void> }).reportCspViolation(`${e.violatedDirective} ${e.blockedURI}`);
    });
  });
  await page.route(
    (url) => !url.pathname.startsWith("/api/"),
    async (route) => {
      if (route.request().resourceType() !== "document") return route.fallback();
      const response = await route.fetch();
      return route.fulfill({ response, headers: { ...response.headers(), "content-security-policy": CSP } });
    },
  );
  return violations;
}

const SCREENS = ["/home", "/notices", "/community", "/academics/timetable", "/academics/results", "/account"];

test("the student screens run under the production CSP with no violations", async ({ page }) => {
  const violations = await withCsp(page);
  await mockAuthApi(page, { signedIn: true, membership: "ACTIVE" });
  await mockNoticesApi(page, { manager: false });
  await mockCommunityApi(page);
  await mockAcademicApi(page);
  for (const path of SCREENS) {
    await page.goto(path);
    await expect(page.getByRole("heading", { level: 1 }).first()).toBeVisible();
  }
  // Theme switching changes styles at runtime: still allowed.
  await page.goto("/account");
  await page.getByText("Dark", { exact: true }).click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  expect(violations).toEqual([]);
});

test("the admin screens run under the production CSP with no violations", async ({ page }) => {
  const violations = await withCsp(page);
  await mockAuthApi(page, { signedIn: true, membership: "ACTIVE", admin: true });
  await mockManageApi(page);
  for (const path of ["/manage/requests", "/manage/members", "/manage/academics", "/manage/moderation"]) {
    await page.goto(path);
    await expect(page.getByRole("heading", { level: 1 }).first()).toBeVisible();
  }
  expect(violations).toEqual([]);
});

test("signing in and registering run under the production CSP with no violations", async ({ page }) => {
  const violations = await withCsp(page);
  await mockAuthApi(page, { signedIn: false });
  for (const path of ["/sign-in", "/register", "/forgot-password"]) {
    await page.goto(path);
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
  }
  // A failed sign-in renders an error (zod and the server message) without eval.
  await page.goto("/sign-in");
  await page.getByLabel("Email").fill("aarav@northfield.example");
  await page.getByLabel("Password").fill("wrong-password");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("alert")).toBeVisible();
  expect(violations).toEqual([]);
});
