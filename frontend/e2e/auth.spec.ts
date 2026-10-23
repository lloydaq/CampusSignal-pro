import { expect, test, type Page } from "@playwright/test";

import { expectNoAxeViolations, expectNoHorizontalScroll, mockAuthApi } from "./support";

/**
 * Account screens against a mocked API (the real end-to-end flow with the backend and
 * Mailpit is a separate job). Each screen is checked with axe in both themes and for
 * horizontal overflow at the project's viewport (1280 px desktop, 390 px mobile).
 */

const PASSWORD = "tidal-quartz-lantern";

async function fillSignIn(page: Page, password = PASSWORD) {
  await page.getByLabel("Email").fill("aarav@northfield.example");
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: "Sign in" }).click();
}

test.describe("journeys", () => {
  test("register, then sign in and reach the account page", async ({ page }) => {
    await mockAuthApi(page, { emailVerified: false });
    await page.goto("/");
    await expect(page).toHaveURL(/\/sign-in$/);
    await page.getByRole("link", { name: "Create an account" }).click();

    await page.getByLabel("Your name").fill("Aarav Nair");
    await page.getByLabel("Email").fill("aarav@northfield.example");
    await page.getByLabel("Password").fill(PASSWORD);
    await page.getByRole("button", { name: "Create account" }).click();
    await expect(page.getByRole("heading", { level: 1, name: "Check your email" })).toBeVisible();

    await page.getByRole("link", { name: "sign in to send a new link" }).click();
    await fillSignIn(page);
    await expect(page).toHaveURL(/\/account$/);
    await expect(page.getByText("Not verified")).toBeVisible();
    await page.getByRole("button", { name: "Send a new link" }).click();
    await expect(page.getByRole("button", { name: /Send again in/ })).toBeDisabled();
  });

  test("a verification link verifies and leaves no token in the address bar", async ({ page }) => {
    await mockAuthApi(page, { signedIn: true, emailVerified: false });
    await page.goto("/verify-email#token=fresh-token");
    await expect(page.getByRole("heading", { level: 1, name: "Your email is verified" })).toBeVisible();
    expect(new URL(page.url()).hash).toBe("");
    await page.getByRole("link", { name: "Go to your account" }).click();
    await expect(page.getByText("Verified", { exact: true })).toBeVisible();
  });

  test("a wrong password shows the generic error; sign-out returns to sign-in", async ({ page }) => {
    await mockAuthApi(page);
    await page.goto("/account");
    await expect(page).toHaveURL(/\/sign-in\?next=%2Faccount$/);
    await fillSignIn(page, "wrong-password");
    await expect(page.getByRole("alert")).toHaveText("Email or password is incorrect.");
    await fillSignIn(page);
    await expect(page).toHaveURL(/\/account$/);
    await page.getByRole("button", { name: "Sign out", exact: true }).click();
    await expect(page.getByText("You've signed out.")).toBeVisible();
    await page.goto("/account");
    await expect(page).toHaveURL(/\/sign-in\?next=/);
  });

  test("forgot and reset password end at sign-in with a notice", async ({ page }) => {
    await mockAuthApi(page);
    await page.goto("/sign-in");
    await page.getByRole("link", { name: "Forgot your password?" }).click();
    await page.getByLabel("Email").fill("someone@riverside.example");
    await page.getByRole("button", { name: "Send reset link" }).click();
    await expect(page.getByText(/If an account exists for that email/)).toBeVisible();

    await page.goto("/reset-password#token=reset");
    expect(new URL(page.url()).hash).toBe("");
    await page.getByLabel("New password", { exact: true }).fill("copper-meadow-harbour");
    await page.getByLabel("Repeat new password").fill("copper-meadow-harbour");
    await page.getByRole("button", { name: "Save new password" }).click();
    await expect(page.getByText("Your password was changed. Sign in with your new password.")).toBeVisible();
  });
});

/** Screens in the states worth checking, each reached the way a user would. */
const SCREENS: { name: string; open: (page: Page) => Promise<void> }[] = [
  {
    name: "sign-in with an error",
    open: async (page) => {
      await mockAuthApi(page);
      await page.goto("/sign-in");
      await fillSignIn(page, "wrong-password");
      await expect(page.getByRole("alert")).toBeVisible();
    },
  },
  {
    name: "register with field errors",
    open: async (page) => {
      await mockAuthApi(page);
      await page.goto("/register");
      await page.getByLabel("Your name").fill("Aarav");
      await page.getByLabel("Email").fill("aarav@northfield.example");
      await page.getByLabel("Password").fill("password1234");
      await page.getByRole("button", { name: "Create account" }).click();
      await expect(page.getByText("This password is too common", { exact: false })).toBeVisible();
    },
  },
  {
    name: "check email",
    open: async (page) => {
      await mockAuthApi(page);
      await page.goto("/check-email");
      await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
    },
  },
  {
    name: "expired verification link",
    open: async (page) => {
      await mockAuthApi(page);
      await page.goto("/verify-email#token=expired");
      await expect(page.getByRole("heading", { level: 1, name: "This link has expired" })).toBeVisible();
    },
  },
  {
    name: "forgot password",
    open: async (page) => {
      await mockAuthApi(page);
      await page.goto("/forgot-password");
      await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
    },
  },
  {
    name: "reset password",
    open: async (page) => {
      await mockAuthApi(page);
      await page.goto("/reset-password#token=reset");
      await expect(page.getByRole("heading", { level: 1, name: "Choose a new password" })).toBeVisible();
    },
  },
  {
    name: "account, unverified, confirming sign-out everywhere",
    open: async (page) => {
      await mockAuthApi(page, { signedIn: true, emailVerified: false });
      await page.goto("/account");
      await page.getByRole("button", { name: "Sign out of all devices" }).click();
      await expect(page.getByRole("button", { name: "Sign out everywhere" })).toBeVisible();
    },
  },
];

test.describe("screens", () => {
  for (const screen of SCREENS) {
    for (const scheme of ["light", "dark"] as const) {
      test(`${screen.name} (${scheme}): no axe violations, no horizontal scroll`, async ({ page }) => {
        await page.emulateMedia({ colorScheme: scheme });
        await screen.open(page);
        await expectNoAxeViolations(page);
        await expectNoHorizontalScroll(page);
      });
    }
  }

  test("inputs and buttons are at least 44 px tall on touch screens", async ({ page }, testInfo) => {
    test.skip(testInfo.project.name !== "mobile", "Touch sizing applies to coarse pointers (mobile project)");
    await mockAuthApi(page);
    await page.goto("/sign-in");
    for (const target of [page.getByLabel("Email"), page.getByLabel("Password"), page.getByRole("button", { name: "Sign in" })]) {
      expect((await target.boundingBox())?.height ?? 0).toBeGreaterThanOrEqual(44);
    }
  });
});
