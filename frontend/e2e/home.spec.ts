import { expect, test, type Page } from "@playwright/test";

import { expectNoAxeViolations, expectNoHorizontalScroll, mockAuthApi } from "./support";

/** US-16: each role lands on a home with its own blocks (data or honest empty states). */

const TERM = { id: "t1", name: "2026-27 Odd semester", is_current: true };
const CS301 = { id: "s1", code: "CS301", name: "Compilers" };
const SECTION = { id: "sec1", name: "A" };

async function homeWith(page: Page, body: Record<string, unknown>) {
  await page.route("**/api/v1/campus/home", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ today: "2026-10-21", is_demo: true, classes: null, attendance: null, needs_attendance: null, my_issues: { status: "ok", open_count: 0, items: [] }, queues: null, ...body }),
    }),
  );
}

const STUDENT_HOME = {
  classes: { status: "ok", term: TERM, items: [{ starts_at: "09:00:00", ends_at: "10:00:00", room: "C-103", section: SECTION, subject: CS301 }] },
  attendance: { status: "ok", term: TERM, items: [{ section: SECTION, subject: CS301, held: 12, attended: 10, excused: 1, percentage: 90.9 }] },
  my_issues: { status: "ok", open_count: 1, items: [{ id: "i1", title: "Projector in C-103 flickers", status: "ACKNOWLEDGED", created_at: "2026-10-20T05:00:00Z" }] },
};
const FACULTY_HOME = {
  classes: STUDENT_HOME.classes,
  needs_attendance: { status: "ok", items: [{ section: SECTION, subject: CS301, held_on: "2026-10-19", starts_at: "09:00:00" }] },
};
const ADMIN_HOME = {
  queues: {
    status: "ok",
    items: [
      { kind: "membership_requests", count: 2 },
      { kind: "content_reports", count: 1 },
      { kind: "unacknowledged_issues", count: 3 },
    ],
  },
};

const ROLES = [
  { name: "student", account: {}, home: STUDENT_HOME, ready: (p: Page) => expect(p.getByRole("list", { name: "Attendance by subject" })).toContainText("90.9%") },
  { name: "faculty", account: { faculty: true }, home: FACULTY_HOME, ready: (p: Page) => expect(p.getByRole("list", { name: "Attendance not taken" })).toBeVisible() },
  { name: "college admin", account: { admin: true }, home: ADMIN_HOME, ready: (p: Page) => expect(p.getByRole("list", { name: "Waiting for you" })).toContainText("2 requests to join") },
];

test.describe("home per role", () => {
  for (const role of ROLES) {
    for (const scheme of ["light", "dark"] as const) {
      test(`${role.name} (${scheme}): their blocks, no axe violations, no horizontal scroll`, async ({ page }) => {
        await page.emulateMedia({ colorScheme: scheme });
        await mockAuthApi(page, { signedIn: true, membership: "ACTIVE", ...role.account });
        await homeWith(page, role.home);
        await page.goto("/");
        await expect(page).toHaveURL(/\/home$/);
        await role.ready(page);
        await expectNoAxeViolations(page);
        await expectNoHorizontalScroll(page);
      });
    }
  }

  test("a faculty member goes from a missing attendance straight to taking it for that date", async ({ page }) => {
    await mockAuthApi(page, { signedIn: true, membership: "ACTIVE", faculty: true });
    await homeWith(page, FACULTY_HOME);
    await page.goto("/home");
    await page.getByRole("list", { name: "Attendance not taken" }).getByRole("link", { name: "Take attendance" }).click();
    await expect(page).toHaveURL(/\/teaching\/sections\/sec1\/attendance\/new\?date=2026-10-19$/);
  });

  test("a student's home has no admin queues and links each block to its section", async ({ page }) => {
    await mockAuthApi(page, { signedIn: true, membership: "ACTIVE" });
    await homeWith(page, STUDENT_HOME);
    await page.goto("/home");
    await expect(page.getByRole("heading", { name: "Needs your attention" })).toHaveCount(0);
    await page.getByRole("link", { name: "Details" }).click();
    await expect(page).toHaveURL(/\/academics\/attendance$/);
  });
});
