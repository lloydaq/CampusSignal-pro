import { expect, test, type Page } from "@playwright/test";

import { mockNoticesApi } from "./noticesApi";
import { expectNoAxeViolations, expectNoHorizontalScroll, mockAuthApi } from "./support";

async function asAdmin(page: Page) {
  await mockAuthApi(page, { signedIn: true, membership: "ACTIVE", admin: true });
  await mockNoticesApi(page, { manager: true });
}

async function asStudent(page: Page) {
  await mockAuthApi(page, { signedIn: true, membership: "ACTIVE" });
  await mockNoticesApi(page, { manager: false });
}

test.describe("notices", () => {
  test("an admin writes an urgent notice, previews it and publishes it to the top of the list", async ({ page }) => {
    await asAdmin(page);
    await page.goto("/notices");
    await page.getByRole("link", { name: "New notice" }).click();
    await page.getByLabel("Title").fill("Campus closed tomorrow");
    await page.getByLabel("Notice text").fill("Heavy rain is forecast. **All classes are cancelled.**\n\n- Hostels stay open\n- The library is closed");
    await page.getByRole("button", { name: "Preview" }).click();
    await expect(page.getByLabel("Preview").locator("strong")).toHaveText("All classes are cancelled.");
    await page.getByLabel("Priority").selectOption("URGENT");
    await page.getByRole("button", { name: "Publish" }).click();

    await expect(page.getByText("Notice published.")).toBeVisible();
    await expect(page.getByRole("heading", { level: 1, name: "Campus closed tomorrow" })).toBeVisible();
    await page.getByRole("link", { name: "All notices" }).click();
    const urgent = page.getByRole("region", { name: "Urgent" });
    await expect(urgent).toContainText("Campus closed tomorrow");
  });

  test("an admin saves a draft, then withdraws a published notice with a reason", async ({ page }) => {
    await asAdmin(page);
    await page.goto("/notices/new");
    await page.getByLabel("Title").fill("Sports day");
    await page.getByLabel("Notice text").fill("Details soon.");
    await page.getByRole("button", { name: "Save draft" }).click();
    await expect(page.getByText("Draft saved.")).toBeVisible();
    await page.goto("/notices?view=drafts");
    await expect(page.getByRole("link", { name: /Sports day/ })).toBeVisible();

    await page.goto("/notices/n2");
    await page.getByRole("button", { name: "Withdraw" }).click();
    const dialog = page.getByRole("dialog", { name: "Withdraw this notice?" });
    await dialog.getByLabel(/Reason/).fill("Superseded");
    await dialog.getByRole("button", { name: "Withdraw notice" }).click();
    await expect(page.getByText("Notice withdrawn.")).toBeVisible();
  });

  test("a student reads notices, opens a department page and can't compose", async ({ page }) => {
    await asStudent(page);
    await page.goto("/home");
    await page.getByRole("navigation", { name: "Main" }).getByRole("link", { name: "Notices" }).first().click();
    await expect(page.getByRole("link", { name: /Mid-term timetable/ })).toBeVisible();
    await expect(page.getByRole("link", { name: "New notice" })).toHaveCount(0);
    await page.getByRole("link", { name: /Mid-term timetable/ }).click();
    await expect(page.locator("article strong")).toHaveText("3 to 7 November");
    await expect(page.locator("article a[href^='https://northfield.example']")).toHaveAttribute("rel", "noopener noreferrer nofollow");

    await page.goto("/home");
    await page.getByRole("link", { name: "Computer Science (CSE)" }).click();
    await expect(page.getByRole("heading", { level: 1, name: "Computer Science" })).toBeVisible();
    await expect(page.getByText("Ravi Sharma")).toBeVisible();
    await expect(page.getByRole("region", { name: "Department notices" })).toContainText("Mid-term timetable");

    await page.goto("/notices/new");
    await expect(page).toHaveURL(/\/notices$/);
  });
});

const SCREENS: { name: string; path: string; as: (page: Page) => Promise<void>; ready: (page: Page) => Promise<void> }[] = [
  { name: "notices list", path: "/notices", as: asStudent, ready: (p) => expect(p.getByRole("link", { name: /Mid-term timetable/ })).toBeVisible() },
  { name: "notice", path: "/notices/n1", as: asStudent, ready: (p) => expect(p.locator("article strong")).toBeVisible() },
  { name: "notice, manager view", path: "/notices/n1", as: asAdmin, ready: (p) => expect(p.getByRole("button", { name: "Withdraw" })).toBeVisible() },
  { name: "editor", path: "/notices/new", as: asAdmin, ready: (p) => expect(p.getByLabel("Title")).toBeVisible() },
  {
    name: "editor with errors",
    path: "/notices/new",
    as: asAdmin,
    ready: async (p) => {
      await p.getByRole("button", { name: "Save draft" }).click();
      await expect(p.getByText("Enter a title.")).toBeVisible();
    },
  },
  { name: "department page", path: "/departments/d1", as: asStudent, ready: (p) => expect(p.getByText("Ravi Sharma")).toBeVisible() },
];

test.describe("notice screens", () => {
  for (const screen of SCREENS) {
    for (const scheme of ["light", "dark"] as const) {
      test(`${screen.name} (${scheme}): no axe violations, no horizontal scroll`, async ({ page }) => {
        await page.emulateMedia({ colorScheme: scheme });
        await screen.as(page);
        await page.goto(screen.path);
        await screen.ready(page);
        await expectNoAxeViolations(page);
        await expectNoHorizontalScroll(page);
      });
    }
  }
});
