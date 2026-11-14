import { expect, test, type Page } from "@playwright/test";

import { mockCommunityApi } from "./communityApi";
import { mockNoticesApi } from "./noticesApi";
import { expectNoAxeViolations, expectNoHorizontalScroll, mockAuthApi } from "./support";

async function asStudent(page: Page) {
  await mockAuthApi(page, { signedIn: true, membership: "ACTIVE" });
  await mockNoticesApi(page, { manager: false }); // the home page lists notices
  await mockCommunityApi(page);
}

test.describe("community", () => {
  test("a student posts to their department, finds it under My department and comments on a college post", async ({ page }) => {
    await asStudent(page);
    await page.goto("/home");
    await page.getByRole("navigation", { name: "Main" }).getByRole("link", { name: "Community" }).first().click();
    await expect(page.getByRole("heading", { level: 1, name: "Community" })).toBeVisible();

    await page.getByRole("button", { name: "Write a post…" }).click();
    const composer = page.getByRole("form", { name: "Write a post" });
    await expect(composer.getByRole("radio", { name: "My department (CSE)" })).toBeChecked();
    await composer.getByLabel("Your post").fill("Study group for the compilers quiz, Friday 4 pm, library room 2.");
    await composer.getByRole("button", { name: "Post" }).click();
    await expect(page.getByText("Posted.")).toBeVisible();

    await page.getByRole("navigation", { name: "Feeds" }).getByRole("link", { name: "My department · CSE" }).click();
    await expect(page.getByRole("article").first()).toContainText("Study group for the compilers quiz");

    await page.getByRole("navigation", { name: "Feeds" }).getByRole("link", { name: "College" }).click();
    const lab = page.getByRole("article", { name: "Post by Ravi Sharma" });
    await lab.getByRole("button", { name: /Helpful/ }).click();
    await expect(lab.getByRole("button", { name: /Helpful/ })).toHaveAttribute("aria-pressed", "true");
    await lab.getByRole("link", { name: "1 comment" }).click();
    const comments = page.getByRole("region", { name: "Comments" });
    await expect(comments).toContainText("Is it open to first years?");
    await comments.getByRole("textbox", { name: "Comment", exact: true }).fill("Yes, I went last week.");
    await comments.getByRole("button", { name: "Post comment" }).click();
    await expect(comments).toContainText("Yes, I went last week.");
  });

  test("a student edits and deletes their own post, and reports someone else's", async ({ page }) => {
    await asStudent(page);
    await page.goto("/community");
    await page.getByRole("button", { name: "Write a post…" }).click();
    const composer = page.getByRole("form", { name: "Write a post" });
    await composer.getByRole("radio", { name: "The whole college" }).check();
    await composer.getByLabel("Your post").fill("Lost: a blue umbrella near the canteen.");
    await composer.getByRole("button", { name: "Post" }).click();

    const mine = page.getByRole("article", { name: "Post by Aarav Nair" });
    await mine.getByRole("button", { name: "Post actions" }).click();
    await mine.getByRole("button", { name: "Edit" }).click();
    await mine.getByLabel("Edit your post").fill("Found it, thanks!");
    await mine.getByRole("button", { name: "Save" }).click();
    await expect(mine).toContainText("Found it, thanks!");
    await expect(mine).toContainText("edited");
    await mine.getByRole("button", { name: "Post actions" }).click();
    await mine.getByRole("button", { name: "Delete" }).click();
    await page.getByRole("dialog", { name: "Delete this post?" }).getByRole("button", { name: "Delete post" }).click();
    await expect(page.getByRole("article", { name: "Post by Aarav Nair" })).toHaveCount(0);

    const theirs = page.getByRole("article", { name: "Post by Ravi Sharma" });
    await theirs.getByRole("button", { name: "Post actions" }).click();
    await theirs.getByRole("button", { name: "Report" }).click();
    const dialog = page.getByRole("dialog", { name: "Report this post?" });
    await dialog.getByRole("radio", { name: "Spam" }).check();
    await dialog.getByRole("button", { name: "Send report" }).click();
    await expect(theirs).toContainText("Thanks. Moderators will look at it.");
  });
});

test("on phones the bottom bar steps aside while typing (Design.md §4)", async ({ page }, info) => {
  test.skip(info.project.name !== "mobile", "the bar exists on phones only");
  await asStudent(page);
  await page.goto("/community");
  const bar = page.getByRole("navigation", { name: "Main" }).filter({ visible: true });
  await expect(bar).toBeVisible();
  await page.getByRole("button", { name: "Write a post…" }).click();
  await page.getByRole("form", { name: "Write a post" }).getByLabel("Your post").fill("Typing");
  await expect(page.getByRole("navigation", { name: "Main" }).filter({ visible: true })).toHaveCount(0);
  await page.getByRole("heading", { level: 1, name: "Community" }).click(); // focus leaves the field
  await expect(bar).toBeVisible();
});

const SCREENS: { name: string; path: string; ready: (page: Page) => Promise<void> }[] = [
  { name: "college feed", path: "/community", ready: (p) => expect(p.getByRole("article").first()).toBeVisible() },
  {
    name: "composer open",
    path: "/community",
    ready: async (p) => {
      await p.getByRole("button", { name: "Write a post…" }).click();
      await expect(p.getByRole("form", { name: "Write a post" })).toBeVisible();
    },
  },
  { name: "department feed", path: "/community?feed=department", ready: (p) => expect(p.getByText("Anyone have notes")).toBeVisible() },
  { name: "post page", path: "/community/posts/p1", ready: (p) => expect(p.getByText("Is it open to first years?")).toBeVisible() },
  {
    name: "report dialog",
    path: "/community/posts/p1",
    ready: async (p) => {
      await p.getByRole("button", { name: "Post actions" }).click();
      await p.getByRole("button", { name: "Report" }).click();
      await expect(p.getByRole("dialog", { name: "Report this post?" })).toBeVisible();
    },
  },
];

test.describe("community screens", () => {
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
