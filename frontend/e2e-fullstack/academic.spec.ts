import { expect, test } from "@playwright/test";

import { createAcademicCollege, PASSWORD, signIn, signOut, unique } from "./campus";

/**
 * J6 + J7 + J3/J4 against the real API and database: a faculty member takes attendance with one
 * student absent, creates a quiz, enters scores and publishes them; the student is notified and
 * sees their own score and attendance, and nothing of their classmate's.
 */

test("faculty record attendance and publish scores; the student sees only their own", async ({ page }) => {
  const run = unique();
  const people = createAcademicCollege(run, PASSWORD);

  // J6: take attendance, Kabir absent.
  await signIn(page, people.faculty);
  await page.goto("/teaching");
  await page.getByRole("list", { name: "Your sections" }).getByRole("link", { name: /CS301/ }).click();
  await page.getByRole("link", { name: "Take attendance" }).click();
  const kabir = page.getByRole("radiogroup", { name: "Kabir Shah" });
  await kabir.getByText("Absent").click();
  await page.getByRole("button", { name: "Save attendance" }).click();
  await expect(page.getByText("Attendance saved.")).toBeVisible();

  // J7: a quiz, scores, publish.
  await page.getByRole("link", { name: /CS301/ }).first().click();
  await page.getByRole("navigation", { name: "Section" }).getByRole("link", { name: "Assessments" }).click();
  await page.getByRole("button", { name: "New assessment" }).click();
  const form = page.getByRole("form", { name: "New assessment" });
  await form.getByLabel("Name").fill("Quiz 1");
  await form.getByLabel("Maximum score").fill("20");
  await form.getByLabel("Date").fill(new Date().toISOString().slice(0, 10));
  await form.getByRole("button", { name: "Create assessment" }).click();
  await page.getByLabel("Score for Ishita Verma").fill("18.5");
  await page.getByLabel("Score for Kabir Shah").fill("12");
  await page.getByRole("button", { name: "Save scores" }).click();
  await expect(page.getByText("Scores saved.")).toBeVisible();
  await page.getByRole("button", { name: "Publish" }).click();
  await page.getByRole("dialog", { name: "Publish these results?" }).getByRole("button", { name: "Publish results" }).click();
  await expect(page.getByText("Published. All 2 students have been told.")).toBeVisible();
  await signOut(page);

  // J4 + J3: the student is told, sees their score, not their classmate's, and their attendance.
  await signIn(page, people.student);
  await page.goto("/notifications");
  await page.getByRole("list", { name: "Notifications" }).getByRole("link", { name: /Results published: CS301 Quiz 1/ }).click();
  await expect(page).toHaveURL(/\/academics\/results$/);
  const results = page.getByRole("region", { name: "CS301 Compilers" });
  await expect(results).toContainText("18.5 / 20");
  await expect(results).not.toContainText("12 / 20"); // the classmate's score (dates can contain "12")
  await page.getByRole("navigation", { name: "Academics" }).getByRole("link", { name: "Attendance" }).click();
  await expect(page.getByRole("table", { name: "Attendance by subject" }).getByRole("row", { name: /CS301/ })).toContainText("100%");

  // US-16: the home's attendance block shows the same, from /campus/home.
  await page.goto("/home");
  await expect(page.getByRole("list", { name: "Attendance by subject" })).toContainText("CS301 Compilers100%");
  await expect(page.getByRole("heading", { name: "Needs your attention" })).toHaveCount(0);
});
