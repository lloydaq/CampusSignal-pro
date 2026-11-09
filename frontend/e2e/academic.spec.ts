import { expect, test, type Page } from "@playwright/test";

import { mockAcademicApi } from "./academicApi";
import { expectNoAxeViolations, expectNoHorizontalScroll, mockAuthApi } from "./support";

async function asStudent(page: Page, empty = false) {
  await mockAuthApi(page, { signedIn: true, membership: "ACTIVE" });
  await mockAcademicApi(page, { empty });
}

test.describe("academics", () => {
  test("a student checks their timetable, attendance and results (J3, J4)", async ({ page }, info) => {
    await asStudent(page);
    await page.goto("/home");
    await page.getByRole("navigation", { name: "Main" }).getByRole("link", { name: "Academics" }).locator("visible=true").first().click();
    await expect(page).toHaveURL(/\/academics\/timetable$/);
    await expect(page.getByText("Demo data")).toBeVisible();
    if (info.project.name === "mobile") {
      await page.getByRole("group", { name: "Day" }).getByRole("button", { name: /Mon/ }).click();
      await expect(page.getByRole("list", { name: "Classes" })).toContainText("CS301 Compilers");
    } else {
      await expect(page.getByRole("table", { name: "Your week" })).toContainText("Compilers lab");
    }

    const tabs = page.getByRole("navigation", { name: "Academics" });
    await tabs.getByRole("link", { name: "Attendance" }).click();
    const table = page.getByRole("table", { name: "Attendance by subject" });
    await expect(table.getByRole("row", { name: /CS301/ })).toContainText("90.9%");
    await table.getByRole("link", { name: /MA201/ }).click();
    await expect(page.getByRole("list", { name: "Sessions" }).getByRole("listitem").first()).toContainText("Present");
    await page.getByRole("link", { name: "All subjects" }).click();

    await tabs.getByRole("link", { name: "Results" }).click();
    const cs = page.getByRole("region", { name: "CS301 Compilers" });
    await expect(cs).toContainText("18.5 / 20");
    await expect(cs.getByRole("row", { name: /Mid-term/ })).toContainText("Revised");
    await expect(page.getByRole("region", { name: /MA201/ })).toContainText("Absent");
  });

  test("a new term with nothing recorded says so on each tab", async ({ page }) => {
    await asStudent(page, true);
    await page.goto("/academics/timetable");
    await expect(page.getByText("No classes in your timetable yet.")).toBeVisible();
    await page.goto("/academics/attendance");
    await expect(page.getByText("No attendance has been recorded for this term yet.")).toBeVisible();
    await page.goto("/academics/results");
    await expect(page.getByText("No results have been published yet.")).toBeVisible();
  });
});

const SCREENS: { name: string; path: string; ready: (page: Page) => Promise<void> }[] = [
  { name: "timetable", path: "/academics/timetable", ready: (p) => expect(p.getByText("2026-27 Odd semester")).toBeVisible() },
  { name: "attendance", path: "/academics/attendance", ready: (p) => expect(p.getByRole("table", { name: "Attendance by subject" })).toBeVisible() },
  { name: "subject attendance", path: "/academics/attendance/s1-A", ready: (p) => expect(p.getByRole("list", { name: "Sessions" })).toBeVisible() },
  { name: "results", path: "/academics/results", ready: (p) => expect(p.getByRole("region", { name: "CS301 Compilers" })).toBeVisible() },
];

test.describe("Academics screens", () => {
  for (const screen of SCREENS) {
    for (const scheme of ["light", "dark"] as const) {
      test(`${screen.name} (${scheme}): no axe violations, no horizontal scroll`, async ({ page }) => {
        await page.emulateMedia({ colorScheme: scheme });
        await asStudent(page);
        await page.goto(screen.path);
        await screen.ready(page);
        await expectNoAxeViolations(page);
        await expectNoHorizontalScroll(page);
      });
    }
  }
});
