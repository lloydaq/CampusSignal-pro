import { expect, test, type Page } from "@playwright/test";

import { mockNoticesApi } from "./noticesApi";
import { expectNoAxeViolations, expectNoHorizontalScroll, mockAuthApi } from "./support";

/** A synthetic notifications API (backend app/api/v1/notifications.py) for a Northfield student. */
async function mockNotificationsApi(page: Page) {
  const items = [
    { id: "a1", type: "NOTICE_PUBLISHED", title: "High priority notice: Mid-term timetable", subject_type: "NOTICE", subject_id: "n1", read: false, created_at: "2026-10-24T05:00:00Z" },
    { id: "a2", type: "NOTICE_PUBLISHED", title: "Urgent notice: Water supply off on Saturday", subject_type: "NOTICE", subject_id: "n9", read: false, created_at: "2026-10-23T09:15:00Z" },
    { id: "a3", type: "MEMBERSHIP_DECIDED", title: "You've joined Northfield Institute", subject_type: "MEMBERSHIP", subject_id: "r1", read: true, created_at: "2026-10-20T04:30:00Z" },
  ];
  const reply = (body: unknown) => ({ status: 200, contentType: "application/json", headers: { "X-Request-ID": "e2e-notifications" }, body: JSON.stringify(body) });
  await page.route("**/api/v1/me/notifications**", (route) => {
    const url = new URL(route.request().url());
    const method = route.request().method();
    if (url.pathname.endsWith("/unread-count")) return route.fulfill(reply({ unread: items.filter((n) => !n.read).length }));
    if (method === "POST" && url.pathname.endsWith("/read-all")) {
      const marked = items.filter((n) => !n.read).length;
      for (const n of items) n.read = true;
      return route.fulfill(reply({ marked }));
    }
    const one = /\/notifications\/([^/]+)\/read$/.exec(url.pathname);
    if (method === "POST" && one) {
      const n = items.find((x) => x.id === one[1])!;
      n.read = true;
      return route.fulfill(reply(n));
    }
    return route.fulfill(reply({ items, next_cursor: null }));
  });
}

async function asStudent(page: Page) {
  await mockAuthApi(page, { signedIn: true, membership: "ACTIVE" });
  await mockNoticesApi(page, { manager: false });
  await mockNotificationsApi(page);
}

test.describe("notifications", () => {
  test("a student sees the unread count, opens a notice from it and marks the rest read", async ({ page }) => {
    await asStudent(page);
    await page.goto("/home");
    // The rail item's name comes from its text, which Chromium spaces as "Notifications , 2 unread".
    const bell = page.getByRole("link", { name: /^Notifications\s*, 2 unread$/ }).locator("visible=true");
    await expect(bell).toHaveCount(1);
    await bell.click();

    await expect(page.getByRole("heading", { level: 1, name: "Notifications" })).toBeVisible();
    await page.getByRole("link", { name: /Mid-term timetable/ }).click();
    await expect(page.locator("article strong")).toHaveText("3 to 7 November");
    await expect(page.getByRole("link", { name: /^Notifications\s*, 1 unread$/ }).locator("visible=true")).toHaveCount(1);

    await page.goBack();
    await page.getByRole("button", { name: "Mark all as read" }).click();
    await expect(page.getByRole("button", { name: "Mark all as read" })).toHaveCount(0);
    await expect(page.getByRole("link", { name: "Notifications", exact: true }).locator("visible=true")).toHaveCount(1);
    await expect(page.getByText(/Unread:/)).toHaveCount(0);
  });
});

test.describe("notifications screen", () => {
  for (const scheme of ["light", "dark"] as const) {
    test(`notifications (${scheme}): no axe violations, no horizontal scroll`, async ({ page }) => {
      await page.emulateMedia({ colorScheme: scheme });
      await asStudent(page);
      await page.goto("/notifications");
      await expect(page.getByRole("link", { name: /Mid-term timetable/ })).toBeVisible();
      await expectNoAxeViolations(page);
      await expectNoHorizontalScroll(page);
    });
  }
});
