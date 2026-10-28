import { expect, test, type Page } from "@playwright/test";

import { mockIssuesApi } from "./issuesApi";
import { mockNoticesApi } from "./noticesApi";
import { expectNoAxeViolations, expectNoHorizontalScroll, mockAuthApi } from "./support";

async function asStudent(page: Page) {
  await mockAuthApi(page, { signedIn: true, membership: "ACTIVE" });
  await mockNoticesApi(page, { manager: false }); // the home page lists notices
  await mockIssuesApi(page);
}

test.describe("issues (J5)", () => {
  test("a student reports an issue, finds it under My issues and comments on it", async ({ page }) => {
    await asStudent(page);
    await page.goto("/home");
    await page.getByRole("navigation", { name: "Main" }).getByRole("link", { name: "Issues" }).first().click();
    await expect(page.getByRole("heading", { level: 1, name: "My issues" })).toBeVisible();
    await page.getByRole("link", { name: "Report an issue" }).click();

    await page.getByRole("radio", { name: "Water & sanitation" }).check();
    await page.getByLabel("What's wrong?").fill("No water in hostel B");
    await page.getByLabel("Where is it?").fill("Hostel block B, ground floor");
    await page.getByLabel("Description").fill("The taps have been dry since 7 am.");
    await page.getByRole("button", { name: "Report issue" }).click();

    await expect(page.getByText("Issue reported. You'll be notified each time its status changes.")).toBeVisible();
    await expect(page.getByRole("heading", { level: 1, name: "No water in hostel B" })).toBeVisible();
    await expect(page.getByRole("navigation", { name: "Progress" }).locator("[aria-current=step]")).toHaveText("Submitted");

    await page.getByRole("textbox", { name: "Comment" }).fill("Block A has water.");
    await page.getByRole("button", { name: "Post comment" }).click();
    await expect(page.getByRole("region", { name: "Updates" })).toContainText("Block A has water.");

    await page.getByRole("link", { name: "My issues" }).click();
    await expect(page.getByRole("list", { name: "My issues" }).getByRole("link")).toHaveCount(2);
    await expect(page.getByRole("list", { name: "My issues" }).getByRole("link").first()).toContainText("No water in hostel B");
  });

  test("a student reopens a resolved issue with a reason", async ({ page }) => {
    await asStudent(page);
    await page.goto("/issues/i1");
    await expect(page.getByRole("region", { name: "Updates" })).toContainText("Replaced the HDMI cable.");
    await page.getByRole("button", { name: "Reopen issue" }).click();
    const dialog = page.getByRole("dialog", { name: "Reopen this issue?" });
    await dialog.getByLabel("What's still wrong?").fill("Still flickers.");
    await dialog.getByRole("button", { name: "Reopen issue" }).click();
    await expect(page.getByText("Issue reopened.")).toBeVisible();
    await expect(page.getByRole("navigation", { name: "Progress" }).locator("[aria-current=step]")).toHaveText("Acknowledged");
    await expect(page.getByRole("button", { name: "Reopen issue" })).toHaveCount(0);
  });
});

const SCREENS: { name: string; path: string; ready: (page: Page) => Promise<void> }[] = [
  { name: "my issues", path: "/issues", ready: (p) => expect(p.getByRole("link", { name: /Lab 3 projector flickers/ })).toBeVisible() },
  { name: "report form", path: "/issues/new", ready: (p) => expect(p.getByLabel("What's wrong?")).toBeVisible() },
  {
    name: "report form with errors",
    path: "/issues/new",
    ready: async (p) => {
      await p.getByRole("button", { name: "Report issue" }).click();
      await expect(p.getByText("Choose a category.")).toBeVisible();
    },
  },
  { name: "resolved issue", path: "/issues/i1", ready: (p) => expect(p.getByRole("button", { name: "Reopen issue" })).toBeVisible() },
];

test.describe("issue screens", () => {
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
