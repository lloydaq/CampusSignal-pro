import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

import { linkIn, waitForEmail } from "./mailpit";
import { createPlatformAdmin } from "./operator";

/**
 * Phase 3 exit demo (Phases.md), against the real API, database and SMTP: a platform admin
 * creates a college and invites its admin; the admin accepts, adds a department and imports
 * the roster; a student registers with their roster email, verifies it and joins by roll
 * number. Names are unique per run, so the suite also works on a database that isn't empty.
 */

const PASSWORD = "tidal-quartz-lantern";
const VERIFY_SUBJECT = "Verify your CampusSignal email";

const unique = () => `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;

async function register(page: Page, request: APIRequestContext, email: string, name: string) {
  await page.goto("/register");
  await page.getByLabel("Your name").fill(name);
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(PASSWORD);
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page.getByRole("heading", { level: 1, name: "Check your email" })).toBeVisible();
  const body = await waitForEmail(request, email, VERIFY_SUBJECT);
  await page.goto(linkIn(body, `${new URL(page.url()).origin}/verify-email#token=`));
  await expect(page.getByRole("heading", { level: 1, name: "Your email is verified" })).toBeVisible();
}

async function signIn(page: Page, email: string) {
  await page.goto("/sign-in");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(PASSWORD);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).not.toHaveURL(/\/sign-in/); // signed in before the next page load
}

async function signOut(page: Page) {
  await page.goto("/account");
  await page.getByRole("button", { name: "Sign out", exact: true }).click();
  await expect(page.getByText("You've signed out.")).toBeVisible();
}

test("platform admin creates a college; its admin imports the roster; a student joins", async ({ page, request }) => {
  const run = unique();
  const collegeName = `Exit Demo College ${run}`;
  const slug = `exit-${run}`.toLowerCase();
  const platformEmail = `e2e-ops-${run}@campussignal.example`;
  const adminEmail = `e2e-admin-${run}@northfield.example`;
  const studentEmail = `e2e-student-${run}@northfield.example`;
  const roll = `XD-${run}`.toUpperCase();
  createPlatformAdmin(platformEmail, PASSWORD);

  // 1. The platform admin creates the college, activates it and invites its first admin.
  await signIn(page, platformEmail);
  await expect(page).toHaveURL(/\/platform\/colleges$/);
  await page.getByLabel("Name").fill(collegeName);
  await page.getByLabel("Slug").fill(slug);
  await page.getByLabel("Email domains (optional)").fill("northfield.example");
  await page.getByRole("button", { name: "Create college" }).click();
  await page.getByRole("link", { name: "Invite its first admin" }).click();
  await expect(page.getByRole("heading", { level: 2, name: collegeName })).toBeVisible();
  await page.getByRole("button", { name: "Activate" }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Activate" }).click();
  await expect(page.getByRole("button", { name: "Suspend" })).toBeVisible();
  await page.getByLabel("Email").fill(adminEmail);
  await page.getByRole("button", { name: "Invite as college admin" }).click();
  await expect(page.getByRole("table", { name: "College admin invitations" })).toContainText("Waiting");
  await signOut(page);

  // 2. The admin registers, opens the invitation and sets the college up.
  await register(page, request, adminEmail, "Priya Menon");
  const invite = await waitForEmail(request, adminEmail, "You're invited to");
  await signIn(page, adminEmail);
  await page.goto(linkIn(invite, `${new URL(page.url()).origin}/invites/accept#token=`));
  await page.getByRole("button", { name: "Accept invitation" }).click();
  await expect(page.getByRole("heading", { level: 1, name: collegeName })).toBeVisible();

  await page.goto("/manage/departments");
  await page.getByLabel("Code").fill("CSE");
  await page.getByLabel("Name").fill("Computer Science");
  await page.getByRole("button", { name: "Add department" }).click();
  await expect(page.getByRole("table", { name: "Departments" })).toContainText("CSE");

  await page.goto("/manage/roster");
  await page
    .getByLabel("Or paste the rows")
    .fill(`roll_number,full_name,department_code,program,admission_year,email\n${roll},Ishita Verma,CSE,B.Tech,2025,${studentEmail}`);
  await page.getByRole("button", { name: "Import" }).click();
  await expect(page.getByText("Imported 1 students.")).toBeVisible();
  await expect(page.getByRole("table", { name: "Roster" })).toContainText(roll);
  await signOut(page);

  // 3. The student registers with the roster email, verifies it and joins by roll number.
  await register(page, request, studentEmail, "Ishita Verma");
  await signIn(page, studentEmail);
  await expect(page.getByRole("heading", { level: 1, name: "Join your college" })).toBeVisible();
  const search = page.getByLabel("Search colleges");
  if (await search.isVisible()) await search.fill(collegeName);
  await page.getByRole("radio", { name: collegeName }).check();
  await page.getByLabel("Roll number").fill(roll);
  await page.getByRole("button", { name: "Send request" }).click();
  await expect(page).toHaveURL(/\/home$/);
  await expect(page.getByRole("heading", { level: 1, name: collegeName })).toBeVisible();
  await expect(page.getByRole("region", { name: "Your membership" })).toContainText("Computer Science (CSE)");
});
