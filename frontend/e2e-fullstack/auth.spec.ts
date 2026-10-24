import { expect, test, type Page } from "@playwright/test";

import { countEmails, linkIn, waitForEmail } from "./mailpit";

/**
 * US-01 end to end against the real API, database and SMTP (Phases.md 2d): register →
 * verify via the emailed link → sign in → sign out, plus the password-reset email flow.
 * Addresses are unique per run, so the suite also works on a database that isn't empty.
 */

const PASSWORD = "tidal-quartz-lantern";
const NEW_PASSWORD = "copper-meadow-harbour";
const VERIFY_SUBJECT = "Verify your CampusSignal email";

function uniqueEmail(label: string): string {
  return `e2e-${label}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}@northfield.example`;
}

async function registerAs(page: Page, email: string, password = PASSWORD) {
  await page.goto("/register");
  await page.getByLabel("Your name").fill("Aarav Nair");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page.getByRole("heading", { level: 1, name: "Check your email" })).toBeVisible();
}

async function signInAs(page: Page, email: string, password: string) {
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: "Sign in" }).click();
}

test("register, verify by email, sign in and out", async ({ page, request }) => {
  const email = uniqueEmail("verify");
  await registerAs(page, email);

  const link = linkIn(await waitForEmail(request, email, VERIFY_SUBJECT), `${new URL(page.url()).origin}/verify-email#token=`);
  await page.goto(link);
  await expect(page.getByRole("heading", { level: 1, name: "Your email is verified" })).toBeVisible();
  expect(new URL(page.url()).hash).toBe("");

  await page.getByRole("link", { name: "Sign in" }).click();
  await signInAs(page, email, PASSWORD);
  // A verified account without a college lands on the join flow (no colleges exist here).
  await expect(page.getByRole("heading", { level: 1, name: "Join your college" })).toBeVisible();
  await page.goto("/account");
  await expect(page.getByText("Verified", { exact: true })).toBeVisible();

  // US-01: the same link a second time says it was already used.
  await page.goto(link);
  await expect(page.getByRole("heading", { level: 1, name: "This link was already used" })).toBeVisible();

  await page.goto("/account");
  await page.getByRole("button", { name: "Sign out", exact: true }).click();
  await expect(page.getByText("You've signed out.")).toBeVisible();
  await page.goto("/account");
  await expect(page).toHaveURL(/\/sign-in\?next=%2Faccount$/);
});

test("registering an existing email reveals nothing and notifies the owner", async ({ page, request }) => {
  const email = uniqueEmail("dup");
  await registerAs(page, email);
  await waitForEmail(request, email, VERIFY_SUBJECT);

  await registerAs(page, email.toUpperCase(), "another-long-password");
  await waitForEmail(request, email, "Someone tried to register with your email");
  expect(await countEmails(request, email, VERIFY_SUBJECT)).toBe(1);
});

test("reset a password by email; the old one stops working", async ({ page, request }) => {
  const email = uniqueEmail("reset");
  await registerAs(page, email);

  await page.goto("/forgot-password");
  await page.getByLabel("Email").fill(email);
  await page.getByRole("button", { name: "Send reset link" }).click();
  await expect(page.getByText(/If an account exists for that email/)).toBeVisible();

  const body = await waitForEmail(request, email, "Reset your CampusSignal password");
  await page.goto(linkIn(body, `${new URL(page.url()).origin}/reset-password#token=`));
  await page.getByLabel("New password", { exact: true }).fill(NEW_PASSWORD);
  await page.getByLabel("Repeat new password").fill(NEW_PASSWORD);
  await page.getByRole("button", { name: "Save new password" }).click();
  await expect(page.getByText("Your password was changed. Sign in with your new password.")).toBeVisible();

  await signInAs(page, email, PASSWORD);
  await expect(page.getByRole("alert")).toHaveText("Email or password is incorrect.");
  await signInAs(page, email, NEW_PASSWORD);
  // A reset doesn't verify the email (AUTH-006, decided 2026-10-21), so joining asks for it.
  await expect(page.getByRole("heading", { level: 1, name: "Verify your email first" })).toBeVisible();
  await page.goto("/account");
  await expect(page.getByText("Not verified")).toBeVisible();
});
