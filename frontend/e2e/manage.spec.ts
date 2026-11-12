import { expect, test, type Page } from "@playwright/test";

import { mockManageApi } from "./manageApi";
import { expectNoAxeViolations, expectNoHorizontalScroll, mockAuthApi } from "./support";

async function signInAsAdmin(page: Page) {
  await mockAuthApi(page, { signedIn: true, membership: "ACTIVE", admin: true });
  await mockManageApi(page);
}

/** On mobile the Manage tabs scroll sideways inside their own strip. */
const tab = (page: Page, name: string) => page.getByRole("navigation", { name: "Manage" }).getByRole("link", { name });

test.describe("college administration", () => {
  test("review the queue: approve a match, reject with a reason, see both in the audit log", async ({ page }, info) => {
    await signInAsAdmin(page);
    await page.goto("/home");
    // On phones, Manage sits in the bottom bar's More sheet.
    if (info.project.name === "mobile") await page.getByRole("button", { name: "More" }).click();
    await page.getByRole("navigation", { name: "Main" }).getByRole("link", { name: "Manage" }).locator("visible=true").first().click();
    await expect(page).toHaveURL(/\/manage\/requests$/);

    const meera = page.getByRole("listitem").filter({ hasText: "Meera Iyer" });
    await expect(meera).toContainText("The roster lists a different email for this roll number.");
    await meera.getByRole("button", { name: "Approve" }).click();
    await expect(meera).toHaveCount(0);

    const rohan = page.getByRole("listitem").filter({ hasText: "Rohan Gupta" });
    await rohan.getByRole("button", { name: "Approve" }).click();
    await expect(rohan.getByRole("alert")).toContainText("Add this roll number to the roster first");
    await rohan.getByRole("button", { name: "Reject" }).click();
    const dialog = page.getByRole("dialog", { name: "Reject Rohan Gupta's request?" });
    await dialog.getByLabel("Reason").fill("Roll number isn't one of ours");
    await dialog.getByRole("button", { name: "Reject request" }).click();
    await expect(page.getByText("No requests waiting.")).toBeVisible();

    await tab(page, "Audit log").click();
    const log = page.getByRole("table", { name: "Audit log" });
    await expect(log).toContainText("Request approved");
    await expect(log).toContainText("Roll number isn't one of ours");
  });

  test("import a roster: see every bad row, fix the file, see the students", async ({ page }) => {
    await signInAsAdmin(page);
    await page.goto("/manage/roster");
    await expect(page.getByText("The roster is empty.")).toBeVisible();
    const header = "roll_number,full_name,department_code,program,admission_year,email";
    await page.getByLabel("CSV file").setInputFiles({
      name: "students.csv",
      mimeType: "text/csv",
      buffer: Buffer.from(`${header}\nCSE2025001,Asha Rao,CSE,B.Tech,2025,asha@northfield.example\nEE2025001,Vikram Das,EEE,B.Tech,2025,\n`),
    });
    await page.getByRole("button", { name: "Import" }).click();
    const problems = page.getByRole("table", { name: "Problems in the file" });
    await expect(problems).toContainText("No current department has this code.");
    await expect(problems).toContainText("3");

    await page.getByLabel("Or paste the rows").fill(`${header}\nCSE2025001,Asha Rao,CSE,B.Tech,2025,asha@northfield.example`);
    await page.getByRole("button", { name: "Import" }).click();
    await expect(page.getByText("Imported 1 students.")).toBeVisible();
    await expect(page.getByRole("table", { name: "Roster" })).toContainText("CSE2025001");
  });

  test("suspend a member only with a reason", async ({ page }) => {
    await signInAsAdmin(page);
    await page.goto("/manage/members");
    await page.getByRole("button", { name: "Manage Kabir Shah" }).click();
    await page.getByRole("button", { name: "Suspend" }).click();
    const dialog = page.getByRole("dialog", { name: "Suspend this membership?" });
    await dialog.getByRole("button", { name: "Suspend" }).click();
    await expect(dialog.getByText("Give a reason.")).toBeVisible();
    await dialog.getByLabel(/Reason/).fill("Asked to leave for the term");
    await dialog.getByRole("button", { name: "Suspend" }).click();
    await expect(dialog).toHaveCount(0);
    await expect(page.getByRole("table", { name: "Members" })).not.toContainText("Kabir Shah"); // filter: Active
  });

  test("moderate: hide a post with a reason, dismiss a comment's report, see both in history and the audit log", async ({ page }) => {
    await signInAsAdmin(page);
    await page.goto("/manage/requests");
    await tab(page, "Moderation").click();
    const queue = page.getByRole("list", { name: "Open reports" });
    const first = queue.getByRole("listitem").filter({ hasText: "False information" });
    await expect(first).toContainText("2 open reports on this post");
    await expect(first).toContainText("Reporter's note: Nobody announced this.");
    await first.getByRole("button", { name: "Hide post" }).click();
    const hide = page.getByRole("dialog", { name: "Hide this post?" });
    await hide.getByLabel(/Reason/).fill("Unverified claim about a named person");
    await hide.getByRole("button", { name: "Hide post" }).click();
    await expect(page.getByText("Post hidden. Its author has been told why. 1 other report on it closed too.")).toBeVisible();
    // Both reports about the post closed together; the comment's report is left.
    await expect(queue.getByRole("listitem")).toHaveCount(1);
    await queue.getByRole("button", { name: "Dismiss" }).click();
    await page.getByRole("dialog", { name: "Dismiss this report?" }).getByRole("button", { name: "Dismiss report" }).click();
    await expect(page.getByText("Report dismissed. The comment stays up.")).toBeVisible();
    await expect(page.getByText("No reports to review.")).toBeVisible();

    await page.getByLabel("Show").selectOption("ACTIONED");
    const hidden = page.getByRole("list", { name: "Hidden" });
    await expect(hidden.getByRole("listitem")).toHaveCount(2);
    await expect(hidden.getByRole("listitem").first()).toContainText("Reason given to its author: Unverified claim about a named person");
    await expect(hidden.getByRole("button")).toHaveCount(0);
    await page.getByLabel("Show").selectOption("DISMISSED");
    await expect(page.getByRole("list", { name: "Dismissed" })).toContainText("Buy cheap notes at notes.example");

    await tab(page, "Audit log").click();
    const log = page.getByRole("table", { name: "Audit log" });
    await expect(log).toContainText("Post or comment hidden");
    await expect(log).toContainText("Reports dismissed");
  });

  test("academics: add a section, assign faculty, enroll by roll number and schedule a class", async ({ page }) => {
    await signInAsAdmin(page);
    await page.goto("/manage/requests");
    await tab(page, "Academics").click();
    const add = page.getByRole("form", { name: "Add section" });
    await add.getByLabel("Subject").selectOption("s1");
    await add.getByLabel("Section name").fill("B");
    await add.getByRole("button", { name: "Add section" }).click();
    const sections = page.getByRole("table", { name: "Sections" });
    await sections.getByRole("link", { name: /CS301 Compilers · B/ }).click();

    await page.getByLabel("Find faculty to assign").fill("La");
    await page.getByRole("button", { name: "Assign Dr. Lakshmi Pillai" }).click();
    await expect(page.getByRole("list", { name: "Assigned faculty" })).toContainText("Dr. Lakshmi Pillai");

    await page.getByLabel("Enroll by roll number").fill("CSE2025001\nME9");
    await page.getByRole("button", { name: "Enroll" }).click();
    await expect(page.getByRole("table", { name: "Problems in the list" })).toContainText("No active student has this roll number.");
    await page.getByLabel("Enroll by roll number").fill("CSE2025001\nCSE2025002");
    await page.getByRole("button", { name: "Enroll" }).click();
    await expect(page.getByText("2 students enrolled.")).toBeVisible();
    await expect(page.getByRole("table", { name: "Enrolled students" })).toContainText("CSE2025002");

    const klass = page.getByRole("form", { name: "Add a class" });
    await klass.getByLabel("Day").selectOption("3");
    await klass.getByLabel("Room").fill("C-103");
    await klass.getByRole("button", { name: "Add class" }).click();
    await expect(page.getByRole("list", { name: "Scheduled classes" })).toContainText("Wednesday 09:00–10:00 · C-103");
  });

  test("students don't see Manage and can't open it", async ({ page }) => {
    await mockAuthApi(page, { signedIn: true, membership: "ACTIVE" });
    await page.goto("/manage/members");
    await expect(page).toHaveURL(/\/home$/);
    await expect(page.getByRole("link", { name: "Manage" })).toHaveCount(0);
  });
});

const SCREENS: { name: string; path: string; ready: (page: Page) => Promise<void> }[] = [
  { name: "requests", path: "/manage/requests", ready: (page) => expect(page.getByText("Meera Iyer").first()).toBeVisible() },
  {
    name: "members with a member opened",
    path: "/manage/members",
    ready: async (page) => {
      await page.getByRole("button", { name: "Manage Dr. Lakshmi Pillai" }).click();
      await expect(page.getByRole("button", { name: "Remove Department admin · MECH" })).toBeVisible();
    },
  },
  { name: "invites", path: "/manage/invites", ready: (page) => expect(page.getByText("No invitations sent yet.")).toBeVisible() },
  { name: "departments", path: "/manage/departments", ready: (page) => expect(page.getByRole("table", { name: "Departments" })).toBeVisible() },
  {
    name: "roster with row errors",
    path: "/manage/roster",
    ready: async (page) => {
      await page.getByLabel("Or paste the rows").fill("roll_number,full_name,department_code,program,admission_year,email\nX1,A,ZZZ,B,2025,");
      await page.getByRole("button", { name: "Import" }).click();
      await expect(page.getByRole("table", { name: "Problems in the file" })).toBeVisible();
    },
  },
  { name: "audit log", path: "/manage/audit", ready: (page) => expect(page.getByText("Nothing recorded yet.")).toBeVisible() },
  { name: "academics sections", path: "/manage/academics", ready: (page) => expect(page.getByRole("table", { name: "Sections" })).toBeVisible() },
  { name: "academics subjects", path: "/manage/academics?view=subjects", ready: (page) => expect(page.getByRole("table", { name: "Subjects" })).toBeVisible() },
  {
    name: "academics terms",
    path: "/manage/academics?view=terms",
    ready: async (page) => {
      await expect(page.getByRole("table", { name: "Terms" })).toBeVisible();
      await expect(page.getByLabel("Attendance edit window (hours)")).toHaveValue("48");
    },
  },
  { name: "section setup", path: "/manage/academics/sections/sec1", ready: (page) => expect(page.getByRole("form", { name: "Add a class" })).toBeVisible() },
  { name: "moderation queue", path: "/manage/moderation", ready: (page) => expect(page.getByRole("list", { name: "Open reports" })).toBeVisible() },
  {
    name: "hide dialog",
    path: "/manage/moderation",
    ready: async (page) => {
      await page.getByRole("button", { name: "Hide post" }).first().click();
      await expect(page.getByRole("dialog")).toBeVisible();
    },
  },
  {
    name: "reject dialog",
    path: "/manage/requests",
    ready: async (page) => {
      await page.getByRole("button", { name: "Reject" }).first().click();
      await expect(page.getByRole("dialog")).toBeVisible();
    },
  },
];

test.describe("Manage screens", () => {
  for (const screen of SCREENS) {
    for (const scheme of ["light", "dark"] as const) {
      test(`${screen.name} (${scheme}): no axe violations, no horizontal scroll`, async ({ page }) => {
        await page.emulateMedia({ colorScheme: scheme });
        await signInAsAdmin(page);
        await page.goto(screen.path);
        await screen.ready(page);
        await expectNoAxeViolations(page);
        await expectNoHorizontalScroll(page);
      });
    }
  }
});
