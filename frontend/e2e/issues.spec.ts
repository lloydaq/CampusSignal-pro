import { expect, test, type Page } from "@playwright/test";

import { mockAssigneesApi, mockIssuesApi } from "./issuesApi";
import { mockNoticesApi } from "./noticesApi";
import { expectNoAxeViolations, expectNoHorizontalScroll, mockAuthApi } from "./support";

async function asStudent(page: Page) {
  await mockAuthApi(page, { signedIn: true, membership: "ACTIVE" });
  await mockNoticesApi(page, { manager: false }); // the home page lists notices
  await mockIssuesApi(page);
}

/** Northfield's college admin: every coordinator power (ISSUE-004). */
async function asCoordinator(page: Page) {
  await mockAuthApi(page, { signedIn: true, membership: "ACTIVE", admin: true });
  await mockNoticesApi(page, { manager: true });
  await mockIssuesApi(page, { staff: true });
  await mockAssigneesApi(page);
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

    await page.getByRole("link", { name: "All issues" }).click();
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

test.describe("handling issues (J9)", () => {
  test("a coordinator works the queue: acknowledge, assign, start, resolve with a note", async ({ page }) => {
    await asCoordinator(page);
    await page.goto("/issues");
    await page.getByRole("navigation", { name: "Issue lists" }).getByRole("link", { name: "Queue" }).click();
    const queue = page.getByRole("table", { name: "Issue queue" });
    // The unacknowledged report comes first even though it is newer.
    await expect(queue.getByRole("link").first()).toHaveText("Wi-Fi drops in the library");
    await queue.getByRole("link", { name: "Wi-Fi drops in the library" }).click();

    const status = page.getByRole("region", { name: "Change status" });
    await status.getByRole("button", { name: "Acknowledge" }).click();
    await expect(page.getByText("Issue acknowledged. The reporter has been told.")).toBeVisible();

    await page.getByRole("region", { name: "Assignment" }).getByRole("button", { name: "Assign" }).click();
    await page.getByLabel("Find faculty or staff").fill("ravi");
    await page.getByRole("button", { name: "Assign to Ravi Sharma" }).click();
    await expect(page.getByText("Assigned to Ravi Sharma. They've been told.")).toBeVisible();

    await status.getByRole("button", { name: "Start work" }).click();
    await expect(page.getByText("Marked in progress. The reporter has been told.")).toBeVisible();
    await status.getByRole("button", { name: "Resolve" }).click();
    const dialog = page.getByRole("dialog", { name: "Resolve this issue?" });
    await dialog.getByLabel(/Resolution note/).fill("Replaced the access point on the second floor.");
    await dialog.getByRole("button", { name: "Resolve issue" }).click();
    await expect(page.getByText("Issue resolved. The reporter has been told.")).toBeVisible();

    const timeline = page.getByRole("region", { name: "Updates" });
    await expect(timeline).toContainText("Assigned it to Ravi Sharma");
    await expect(timeline).toContainText("Replaced the access point on the second floor.");
    await expect(page.getByRole("navigation", { name: "Progress" }).locator("[aria-current=step]")).toHaveText("Resolved");
  });

  test("a coordinator leaves an internal note the reporter won't see", async ({ page }) => {
    await asCoordinator(page);
    await page.goto("/issues/i2");
    await page.getByRole("textbox", { name: "Comment" }).fill("Vendor visit booked for Friday.");
    await page.getByRole("checkbox", { name: "Internal: hidden from the reporter" }).check();
    await page.getByRole("button", { name: "Post comment" }).click();
    const timeline = page.getByRole("region", { name: "Updates" });
    await expect(timeline.getByRole("listitem").last()).toContainText("Internal");
    await expect(timeline.getByRole("listitem").last()).toContainText("Vendor visit booked for Friday.");
  });
});

const SCREENS: { name: string; path: string; ready: (page: Page) => Promise<void>; as?: (page: Page) => Promise<void> }[] = [
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
  { name: "coordinator queue", path: "/issues/queue", as: asCoordinator, ready: (p) => expect(p.getByRole("table", { name: "Issue queue" })).toBeVisible() },
  { name: "issue, coordinator view", path: "/issues/i2", as: asCoordinator, ready: (p) => expect(p.getByRole("button", { name: "Acknowledge" })).toBeVisible() },
  {
    name: "assignee picker",
    path: "/issues/i2",
    as: asCoordinator,
    ready: async (p) => {
      await p.getByRole("region", { name: "Assignment" }).getByRole("button", { name: "Assign" }).click();
      await expect(p.getByRole("list", { name: "Faculty and staff" })).toBeVisible();
    },
  },
  {
    name: "duplicate dialog",
    path: "/issues/i2",
    as: asCoordinator,
    ready: async (p) => {
      await p.getByRole("button", { name: "Reject as duplicate" }).click();
      await expect(p.getByRole("dialog", { name: "Close as a duplicate?" })).toBeVisible();
    },
  },
];

test.describe("issue screens", () => {
  for (const screen of SCREENS) {
    for (const scheme of ["light", "dark"] as const) {
      test(`${screen.name} (${scheme}): no axe violations, no horizontal scroll`, async ({ page }) => {
        await page.emulateMedia({ colorScheme: scheme });
        await (screen.as ?? asStudent)(page);
        await page.goto(screen.path);
        await screen.ready(page);
        await expectNoAxeViolations(page);
        await expectNoHorizontalScroll(page);
      });
    }
  }
});
