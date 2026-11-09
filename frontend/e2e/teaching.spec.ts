import { expect, test, type Page } from "@playwright/test";

import { mockTeachingApi } from "./teachingApi";
import { expectNoAxeViolations, expectNoHorizontalScroll, mockAuthApi } from "./support";

async function asFaculty(page: Page) {
  await mockAuthApi(page, { signedIn: true, membership: "ACTIVE", faculty: true });
  await mockTeachingApi(page);
}

test.describe("teaching", () => {
  test("a faculty member takes attendance by keyboard and scores and publishes a quiz (J6, J7)", async ({ page }) => {
    await asFaculty(page);
    await page.goto("/home");
    await page.getByRole("navigation", { name: "Main" }).getByRole("link", { name: "Teaching" }).locator("visible=true").first().click();
    await page.getByRole("list", { name: "Your sections" }).getByRole("link", { name: /CS301/ }).click();
    await page.getByRole("link", { name: "Take attendance" }).click();
    const first = page.getByRole("radiogroup", { name: "Ishita Verma" }).getByRole("radio", { name: "Present" });
    await first.focus();
    await page.keyboard.press("ArrowDown");
    await page.keyboard.press("a");
    await expect(page.getByRole("radiogroup", { name: "Kabir Shah" }).getByRole("radio", { name: "Absent" })).toBeChecked();
    await expect(page.locator("p", { hasText: /present ·/ })).toHaveText("3 present · 1 absent · 0 excused");
    await page.getByRole("button", { name: "Save attendance" }).click();
    await expect(page.getByText("Attendance saved.")).toBeVisible();

    await page.goto("/teaching/sections/sec1?tab=assessments");
    await page.getByRole("list", { name: "Assessments" }).getByRole("link", { name: /Quiz 1/ }).click();
    for (const [name, score] of [["Ishita Verma", "18.5"], ["Kabir Shah", "12"], ["Meera Iyer", "20"], ["Rohan Gupta", "9.25"]]) {
      await page.getByLabel(`Score for ${name}`).fill(score!);
    }
    await page.getByRole("button", { name: "Save scores" }).click();
    await expect(page.getByText("Scores saved.")).toBeVisible();
    await page.getByRole("button", { name: "Publish" }).click();
    await page.getByRole("dialog", { name: "Publish these results?" }).getByRole("button", { name: "Publish results" }).click();
    await expect(page.getByText("Published. All 4 students have been told.")).toBeVisible();
  });

  test("leaving unsaved attendance asks first; a closed window is read-only", async ({ page }) => {
    await asFaculty(page);
    await page.goto("/teaching/sections/sec1/attendance/new");
    await page.getByRole("radiogroup", { name: "Kabir Shah" }).getByText("Absent").click();
    await page.getByRole("link", { name: /Section A/ }).click();
    const leave = page.getByRole("dialog", { name: "Leave without saving?" });
    await leave.getByRole("button", { name: "Cancel" }).click();
    await expect(page).toHaveURL(/attendance\/new$/);

    await page.goto("/teaching/sessions/ses2");
    await expect(page.getByText("Edit window closed — ask your department admin")).toBeVisible();
    await expect(page.getByRole("button", { name: /Save/ })).toHaveCount(0);
  });
});

const SCREENS: { name: string; path: string; ready: (page: Page) => Promise<void> }[] = [
  { name: "sections", path: "/teaching", ready: (p) => expect(p.getByRole("list", { name: "Your sections" })).toBeVisible() },
  { name: "section attendance", path: "/teaching/sections/sec1", ready: (p) => expect(p.getByRole("list", { name: "Attendance sessions" })).toBeVisible() },
  { name: "section assessments", path: "/teaching/sections/sec1?tab=assessments", ready: (p) => expect(p.getByRole("list", { name: "Assessments" })).toBeVisible() },
  { name: "section students", path: "/teaching/sections/sec1?tab=students", ready: (p) => expect(p.getByRole("list", { name: "Students" })).toBeVisible() },
  { name: "take attendance", path: "/teaching/sections/sec1/attendance/new", ready: (p) => expect(p.getByRole("list", { name: "Class list" })).toBeVisible() },
  { name: "closed session", path: "/teaching/sessions/ses2", ready: (p) => expect(p.getByText("Edit window closed — ask your department admin")).toBeVisible() },
  { name: "score grid", path: "/teaching/assessments/as1", ready: (p) => expect(p.getByRole("table", { name: "Scores" })).toBeVisible() },
  { name: "published assessment", path: "/teaching/assessments/as2", ready: (p) => expect(p.getByText("Changing a published score needs a reason.", { exact: false })).toBeVisible() },
];

test.describe("Teaching screens", () => {
  for (const screen of SCREENS) {
    for (const scheme of ["light", "dark"] as const) {
      test(`${screen.name} (${scheme}): no axe violations, no horizontal scroll`, async ({ page }) => {
        await page.emulateMedia({ colorScheme: scheme });
        await asFaculty(page);
        await page.goto(screen.path);
        await screen.ready(page);
        await expectNoAxeViolations(page);
        await expectNoHorizontalScroll(page);
      });
    }
  }
});
