import { expect, test, type Page } from "@playwright/test";

import { createIssueCollege } from "./campus";

/**
 * J5 + J9 against the real API and database (PRD §8): a student reports an issue; the
 * coordinator acknowledges it and assigns it to a faculty member; the faculty member starts
 * work and resolves it with a note; the student is notified and sees it resolved.
 */

const PASSWORD = "tidal-quartz-lantern";
const unique = () => `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;

async function signIn(page: Page, email: string) {
  await page.goto("/sign-in");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(PASSWORD);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/home$/);
}

async function signOut(page: Page) {
  await page.goto("/account");
  await page.getByRole("button", { name: "Sign out", exact: true }).click();
  await expect(page.getByText("You've signed out.")).toBeVisible();
}

test("a reported issue is acknowledged, assigned, worked on and resolved", async ({ page }) => {
  const run = unique();
  const people = createIssueCollege(run, PASSWORD);
  const title = `Projector in C-103 flickers ${run}`;

  // J5: the student reports it.
  await signIn(page, people.student);
  await page.goto("/issues/new");
  await page.getByRole("radio", { name: "Classroom equipment" }).check();
  await page.getByLabel("What's wrong?").fill(title);
  await page.getByLabel("Where is it?").fill("Block C, first floor");
  await page.getByLabel("Description").fill("The image flickers every few seconds.");
  await page.getByRole("button", { name: "Report issue" }).click();
  await expect(page.getByRole("heading", { level: 1, name: title })).toBeVisible();
  const issueUrl = page.url();
  await signOut(page);

  // J9: the coordinator acknowledges it from the queue and assigns it.
  await signIn(page, people.coordinator);
  await page.goto("/issues/queue");
  await page.getByRole("table", { name: "Issue queue" }).getByRole("link", { name: title }).click();
  await page.getByRole("region", { name: "Change status" }).getByRole("button", { name: "Acknowledge" }).click();
  await expect(page.getByText("Issue acknowledged. The reporter has been told.")).toBeVisible();
  await page.getByRole("region", { name: "Assignment" }).getByRole("button", { name: "Assign" }).click();
  await page.getByLabel("Find faculty or staff").fill("Ravi");
  await page.getByRole("button", { name: "Assign to Ravi Sharma" }).click();
  await expect(page.getByText("Assigned to Ravi Sharma. They've been told.")).toBeVisible();
  await page.getByRole("textbox", { name: "Comment" }).fill("Vendor quote pending.");
  await page.getByRole("checkbox", { name: "Internal: hidden from the reporter" }).check();
  await page.getByRole("button", { name: "Post comment" }).click();
  await expect(page.getByRole("region", { name: "Updates" })).toContainText("Vendor quote pending.");
  await signOut(page);

  // The faculty member finds it under Assigned to me, starts work and resolves it.
  await signIn(page, people.faculty);
  await page.goto("/issues?view=assigned");
  await page.getByRole("list", { name: "Issues assigned to me" }).getByRole("link", { name: new RegExp(title) }).click();
  const status = page.getByRole("region", { name: "Change status" });
  await status.getByRole("button", { name: "Start work" }).click();
  await expect(page.getByText("Marked in progress. The reporter has been told.")).toBeVisible();
  await status.getByRole("button", { name: "Resolve" }).click();
  const dialog = page.getByRole("dialog", { name: "Resolve this issue?" });
  await dialog.getByLabel(/Resolution note/).fill("Replaced the HDMI cable.");
  await dialog.getByRole("button", { name: "Resolve issue" }).click();
  await expect(page.getByText("Issue resolved. The reporter has been told.")).toBeVisible();
  await signOut(page);

  // The student was told at each step and sees it resolved, without the internal note.
  await signIn(page, people.student);
  await page.goto("/notifications");
  const notifications = page.getByRole("list", { name: "Notifications" });
  await expect(notifications.getByRole("link", { name: new RegExp(`Issue resolved: ${title}`) })).toBeVisible();
  await expect(notifications.getByRole("link", { name: new RegExp(`Issue acknowledged: ${title}`) })).toBeVisible();
  await notifications.getByRole("link", { name: new RegExp(`Issue resolved: ${title}`) }).click();
  await expect(page).toHaveURL(issueUrl);
  await expect(page.getByRole("navigation", { name: "Progress" }).locator("[aria-current=step]")).toHaveText("Resolved");
  const timeline = page.getByRole("region", { name: "Updates" });
  await expect(timeline).toContainText("Replaced the HDMI cable.");
  await expect(timeline).not.toContainText("Vendor quote pending.");
  await expect(page.getByRole("button", { name: "Reopen issue" })).toBeVisible();
});
