import { expect, test } from "@playwright/test";

import { createCommunityCollege, PASSWORD, signIn, signOut, unique } from "./campus";

/**
 * US-10 against the real API and database: a student posts to their department; a classmate
 * comments and reports it; the college admin hides it from Manage → Moderation with a reason;
 * it leaves the classmate's feed, and its author is notified and sees why.
 */

test("a reported post is hidden by a moderator and its author sees why", async ({ page }) => {
  const run = unique();
  const people = createCommunityCollege(run, PASSWORD);
  const words = `The hostel closes for good next week ${run}`;
  const reason = "Unverified claim; the hostel office says otherwise.";

  // The author posts to CSE.
  await signIn(page, people.author);
  await page.goto("/community");
  await page.getByRole("button", { name: "Write a post…" }).click();
  const composer = page.getByRole("form", { name: "Write a post" });
  await composer.getByLabel("Your post").fill(words);
  await composer.getByRole("button", { name: "Post" }).click();
  await expect(page.getByText("Posted.")).toBeVisible();
  await signOut(page);

  // A classmate finds it under My department, comments and reports it.
  await signIn(page, people.classmate);
  await page.goto("/community?feed=department");
  const post = page.getByRole("article", { name: "Post by Ishita Verma" });
  await expect(post).toContainText(words);
  await post.getByRole("link", { name: "Comment" }).click();
  const comments = page.getByRole("region", { name: "Comments" });
  await comments.getByRole("textbox", { name: "Comment", exact: true }).fill("Source?");
  await comments.getByRole("button", { name: "Post comment" }).click();
  await expect(comments).toContainText("Source?");
  const postUrl = page.url();
  const detail = page.getByRole("article", { name: "Post by Ishita Verma" });
  await detail.getByRole("button", { name: "Post actions" }).click();
  await detail.getByRole("button", { name: "Report" }).click();
  const report = page.getByRole("dialog", { name: "Report this post?" });
  await report.getByRole("radio", { name: "False information" }).check();
  await report.getByLabel(/Anything they should know/).fill("Nobody announced this.");
  await report.getByRole("button", { name: "Send report" }).click();
  await expect(detail).toContainText("Thanks. Moderators will look at it.");
  await signOut(page);

  // The college admin hides it from the queue.
  await signIn(page, people.admin);
  await page.goto("/manage/moderation");
  const item = page.getByRole("list", { name: "Open reports" }).getByRole("listitem").filter({ hasText: words });
  await expect(item).toContainText("False information");
  await expect(item).toContainText("Reporter's note: Nobody announced this.");
  await expect(item).not.toContainText("Kabir Shah"); // reporters stay private
  await item.getByRole("button", { name: "Hide post" }).click();
  const hide = page.getByRole("dialog", { name: "Hide this post?" });
  await hide.getByLabel(/Reason/).fill(reason);
  await hide.getByRole("button", { name: "Hide post" }).click();
  await expect(page.getByText("Post hidden. Its author has been told why.")).toBeVisible();
  await page.getByLabel("Show").selectOption("ACTIONED");
  await expect(page.getByRole("list", { name: "Hidden" })).toContainText(`Reason given to its author: ${reason}`);
  await signOut(page);

  // Gone for the classmate, in the feed and by its link.
  await signIn(page, people.classmate);
  await page.goto("/community?feed=department");
  await expect(page.getByText("No posts yet. Start the first discussion.")).toBeVisible();
  await page.goto(postUrl);
  await expect(page.getByText("This post isn't available")).toBeVisible();
  await signOut(page);

  // The author was told and sees the reason on the post.
  await signIn(page, people.author);
  await page.goto("/notifications");
  await page.getByRole("list", { name: "Notifications" }).getByRole("link", { name: /A moderator hid your post/ }).click();
  await expect(page).toHaveURL(postUrl);
  await expect(page.getByText("Hidden by a moderator")).toBeVisible();
  await expect(page.getByText(`Reason: ${reason}`)).toBeVisible();
});
