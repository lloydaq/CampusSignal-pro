import { expect, test, type Page } from "@playwright/test";

import { mockPlatformApi } from "./platformApi";
import { expectNoAxeViolations, expectNoHorizontalScroll, mockAuthApi } from "./support";

async function signInAsPlatformAdmin(page: Page) {
  await mockAuthApi(page, { signedIn: true, platform: true });
  await mockPlatformApi(page);
}

test.describe("platform administration", () => {
  test("create a college, invite its first admin and activate it", async ({ page }) => {
    await signInAsPlatformAdmin(page);
    await page.goto("/");
    await expect(page).toHaveURL(/\/platform\/colleges$/);

    await page.getByLabel("Name").fill("Northfield Institute");
    await page.getByLabel("Slug").fill("northfield");
    await page.getByRole("button", { name: "Create college" }).click();
    await page.getByRole("link", { name: "Invite its first admin" }).click();
    await expect(page.getByRole("heading", { level: 2, name: "Northfield Institute" })).toBeVisible();

    await page.getByLabel("Email").fill("priya.menon@northfield.example");
    await page.getByRole("button", { name: "Invite as college admin" }).click();
    await expect(page.getByRole("table", { name: "College admin invitations" })).toContainText("Waiting");

    await page.getByRole("button", { name: "Activate" }).click();
    await page.getByRole("dialog").getByRole("button", { name: "Activate" }).click();
    await expect(page.getByRole("button", { name: "Suspend" })).toBeVisible();

    await page.getByRole("navigation", { name: "Platform" }).getByRole("link", { name: "Audit log" }).click();
    const log = page.getByRole("table", { name: "Platform audit log" });
    await expect(log).toContainText("College created");
    await expect(log).toContainText("College admin invited");
    await expect(log).toContainText("College status changed");
  });

  test("suspending a college needs a reason", async ({ page }) => {
    await signInAsPlatformAdmin(page);
    await page.goto("/platform/colleges");
    await page.getByRole("link", { name: "Riverside College" }).click();
    await page.getByRole("button", { name: "Suspend" }).click();
    const dialog = page.getByRole("dialog", { name: "Suspend Riverside College?" });
    await dialog.getByRole("button", { name: "Suspend" }).click();
    await expect(dialog.getByText("Give a reason.")).toBeVisible();
    await dialog.getByLabel(/Reason/).fill("Fees unpaid");
    await dialog.getByRole("button", { name: "Suspend" }).click();
    await expect(page.getByRole("button", { name: "Reactivate" })).toBeVisible();
  });

  test("find an account by exact email and suspend it", async ({ page }) => {
    await signInAsPlatformAdmin(page);
    await page.goto("/platform/users");
    await page.getByLabel("Find an account by email").fill("kabir.shah@northfield.example");
    await page.getByRole("button", { name: "Find" }).click();
    await expect(page.getByText("Kabir Shah")).toBeVisible();
    await page.getByRole("button", { name: "Suspend account" }).click();
    const dialog = page.getByRole("dialog");
    await dialog.getByLabel(/Reason/).fill("Report of misuse");
    await dialog.getByRole("button", { name: "Suspend account" }).click();
    await expect(page.getByRole("button", { name: "Reinstate account" })).toBeVisible();
  });

  test("college admins and students can't open the platform", async ({ page }) => {
    await mockAuthApi(page, { signedIn: true, membership: "ACTIVE", admin: true });
    await page.goto("/platform/colleges");
    await expect(page).toHaveURL(/\/home$/);
    await expect(page.getByRole("link", { name: "Platform" })).toHaveCount(0);
  });
});

const SCREENS: { name: string; path: string; ready: (page: Page) => Promise<void> }[] = [
  { name: "colleges", path: "/platform/colleges", ready: (page) => expect(page.getByRole("table", { name: "Colleges" })).toBeVisible() },
  { name: "college detail", path: "/platform/colleges/c2", ready: (page) => expect(page.getByRole("button", { name: "Suspend" })).toBeVisible() },
  {
    name: "suspend dialog",
    path: "/platform/colleges/c2",
    ready: async (page) => {
      await page.getByRole("button", { name: "Suspend" }).click();
      await expect(page.getByRole("dialog")).toBeVisible();
    },
  },
  {
    name: "users with an account found",
    path: "/platform/users",
    ready: async (page) => {
      await page.getByLabel("Find an account by email").fill("kabir.shah@northfield.example");
      await page.getByRole("button", { name: "Find" }).click();
      await expect(page.getByText("Kabir Shah")).toBeVisible();
    },
  },
  { name: "audit log", path: "/platform/audit", ready: (page) => expect(page.getByText("Nothing recorded yet.")).toBeVisible() },
];

test.describe("Platform screens", () => {
  for (const screen of SCREENS) {
    for (const scheme of ["light", "dark"] as const) {
      test(`${screen.name} (${scheme}): no axe violations, no horizontal scroll`, async ({ page }) => {
        await page.emulateMedia({ colorScheme: scheme });
        await signInAsPlatformAdmin(page);
        await page.goto(screen.path);
        await screen.ready(page);
        await expectNoAxeViolations(page);
        await expectNoHorizontalScroll(page);
      });
    }
  }
});
