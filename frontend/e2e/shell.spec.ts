import { expect, test } from "@playwright/test";

import { expectNoAxeViolations, mockBackend, statusRow } from "./support";

const LIGHT_BG = "rgb(246, 247, 249)"; // --bg, Design.md §3.1
const DARK_BG = "rgb(15, 20, 32)"; // --bg, Design.md §3.2

const bodyBackground = (page: import("@playwright/test").Page) =>
  page.evaluate(() => getComputedStyle(document.body).backgroundColor);

test.describe("service status", () => {
  test("shows API running and database ready", async ({ page }) => {
    await mockBackend(page, "ready");
    await page.goto("/status");
    await expect(page.getByRole("heading", { level: 1 })).toHaveText("Service status");
    await expect(statusRow(page, "API")).toContainText("Running");
    await expect(statusRow(page, "Database")).toContainText("Ready");
  });

  test("reports pending migrations and an unreachable database as states", async ({ page }) => {
    await mockBackend(page, "migrations_pending");
    await page.goto("/status");
    await expect(statusRow(page, "Database")).toContainText("Migrations pending");
    await expect(page.getByRole("alert")).toHaveCount(0);

    await page.unrouteAll({ behavior: "ignoreErrors" });
    await mockBackend(page, "database_unreachable");
    await page.getByRole("button", { name: "Check again" }).click();
    await expect(statusRow(page, "Database")).toContainText("Unreachable");
    await expect(statusRow(page, "API")).toContainText("Running");
  });

  test("reports the API as unreachable when the server can't be contacted", async ({ page }) => {
    await mockBackend(page, "api_unreachable");
    await page.goto("/status");
    await expect(statusRow(page, "API")).toContainText("Unreachable");
    await expect(statusRow(page, "Database")).toContainText("Unknown while the API is unreachable");
  });

  test("shows the error with its request ID, then recovers on Try again", async ({ page }) => {
    await mockBackend(page, "server_error");
    await page.goto("/status");
    const alert = page.getByRole("alert");
    await expect(alert).toContainText("Couldn't check service status");
    await expect(alert).toContainText("Request ID e2e-req-500");
    await expect(alert).not.toContainText("Traceback");

    await page.unrouteAll({ behavior: "ignoreErrors" });
    await mockBackend(page, "ready");
    await alert.getByRole("button", { name: "Try again" }).click();
    await expect(statusRow(page, "Database")).toContainText("Ready");
    await expect(page.getByRole("alert")).toHaveCount(0);
  });
});

test.describe("navigation", () => {
  test("unknown paths show the not-found page with a working link home", async ({ page }) => {
    await mockBackend(page, "ready");
    await page.goto("/no/such/page");
    await expect(page.getByRole("heading", { level: 1, name: "Page not found" })).toBeVisible();
    await page.getByRole("link", { name: "Go to the start page" }).click();
    await expect(page).toHaveURL(/\/sign-in$/);
    await expect(page.getByRole("heading", { level: 1, name: "Sign in" })).toBeVisible();
  });
});

test.describe("theme", () => {
  test("follows the system preference until the user chooses, and remembers the choice", async ({ page }) => {
    await mockBackend(page, "ready");
    await page.emulateMedia({ colorScheme: "dark" });
    await page.goto("/status");
    await expect(page.getByRole("radio", { name: "System" })).toBeChecked();
    expect(await bodyBackground(page)).toBe(DARK_BG);

    await page.getByText("Light", { exact: true }).click();
    await expect(page.getByRole("radio", { name: "Light" })).toBeChecked();
    expect(await bodyBackground(page)).toBe(LIGHT_BG);

    await page.reload();
    await expect(page.getByRole("radio", { name: "Light" })).toBeChecked();
    expect(await bodyBackground(page)).toBe(LIGHT_BG);

    await page.getByText("System", { exact: true }).click();
    expect(await bodyBackground(page)).toBe(DARK_BG);
    await page.emulateMedia({ colorScheme: "light" });
    expect(await bodyBackground(page)).toBe(LIGHT_BG);
  });

  test("can be changed with the keyboard", async ({ page }) => {
    await mockBackend(page, "ready");
    await page.emulateMedia({ colorScheme: "light" });
    await page.goto("/status");
    await page.getByRole("radio", { name: "System" }).focus();
    await page.keyboard.press("ArrowLeft"); // native radio group: moves to Dark and selects it
    await expect(page.getByRole("radio", { name: "Dark" })).toBeChecked();
    expect(await bodyBackground(page)).toBe(DARK_BG);
  });
});

test.describe("layout and accessibility", () => {
  for (const scheme of ["light", "dark"] as const) {
    test(`has no axe violations in the ${scheme} theme`, async ({ page }) => {
      await mockBackend(page, "ready");
      await page.emulateMedia({ colorScheme: scheme });
      await page.goto("/status");
      await expect(statusRow(page, "Database")).toContainText("Ready");
      await expectNoAxeViolations(page);
    });
  }

  test("has no axe violations in the error state or on the not-found page", async ({ page }) => {
    await mockBackend(page, "server_error");
    await page.goto("/status");
    await expect(page.getByRole("alert")).toBeVisible();
    await expectNoAxeViolations(page);

    await page.goto("/missing");
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
    await expectNoAxeViolations(page);
  });

  test("fits the viewport without horizontal scrolling", async ({ page }) => {
    await mockBackend(page, "ready");
    await page.goto("/status");
    await expect(statusRow(page, "API")).toContainText("Running");
    const { scrollWidth, innerWidth } = await page.evaluate(() => ({
      scrollWidth: document.documentElement.scrollWidth,
      innerWidth: window.innerWidth,
    }));
    expect(scrollWidth).toBeLessThanOrEqual(innerWidth);
  });

  test("touch targets are at least 44 px on touch screens", async ({ page }, testInfo) => {
    test.skip(testInfo.project.name !== "mobile", "Touch sizing applies to coarse pointers (mobile project)");
    await mockBackend(page, "ready");
    await page.goto("/status");
    await expect(statusRow(page, "API")).toContainText("Running");
    const targets = [
      page.getByRole("button", { name: "Check again" }),
      page.getByText("Light", { exact: true }),
      page.getByText("Dark", { exact: true }),
      page.getByText("System", { exact: true }),
    ];
    for (const target of targets) {
      const box = await target.boundingBox();
      expect(box?.height ?? 0).toBeGreaterThanOrEqual(44);
    }
  });

  test("keyboard focus is visible on the theme options", async ({ page }) => {
    await mockBackend(page, "ready");
    await page.goto("/status");
    await expect(statusRow(page, "API")).toContainText("Running");
    await page.keyboard.press("Tab"); // Check again
    await page.keyboard.press("Tab"); // selected theme radio
    const outline = await page.evaluate(() => {
      const active = document.activeElement as HTMLInputElement | null;
      const indicator = active?.nextElementSibling;
      return indicator ? getComputedStyle(indicator).outlineStyle : "none";
    });
    expect(await page.evaluate(() => (document.activeElement as HTMLInputElement | null)?.type)).toBe("radio");
    expect(outline).not.toBe("none");
  });

  test("honours reduced motion", async ({ page }) => {
    await mockBackend(page, "ready");
    await page.emulateMedia({ reducedMotion: "reduce" });
    await page.goto("/status");
    const duration = await page
      .getByRole("button", { name: "Check again" })
      .evaluate((el) => getComputedStyle(el).transitionDuration);
    expect(duration).toBe("0s");
  });
});
