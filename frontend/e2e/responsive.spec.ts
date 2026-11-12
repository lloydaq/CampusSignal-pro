import { expect, test, type Page } from "@playwright/test";

import { mockAcademicApi } from "./academicApi";
import { mockCommunityApi } from "./communityApi";
import { mockIssuesApi } from "./issuesApi";
import { mockManageApi } from "./manageApi";
import { mockNoticesApi } from "./noticesApi";
import { mockPlatformApi } from "./platformApi";
import { expectNoHorizontalScroll, mockAuthApi } from "./support";
import { mockTeachingApi } from "./teachingApi";

/**
 * Phase 9c: every screen at the two widths the per-feature specs don't cover, 360 px (small
 * Android phones) and 768 px (tablets, between the phone bar and the desktop rail): no
 * horizontal scroll, the page's heading visible. 390 and 1280 px are checked in each spec,
 * with axe. Screenshots at 360 px of the densest screens were checked by eye (memory.md §10).
 */

type Who = "guest" | "student" | "faculty" | "admin" | "platform";

async function as(page: Page, who: Who) {
  if (who === "guest") return void (await mockAuthApi(page, { signedIn: false }));
  if (who === "platform") {
    await mockAuthApi(page, { signedIn: true, platform: true });
    return void (await mockPlatformApi(page));
  }
  await mockAuthApi(page, { signedIn: true, membership: "ACTIVE", admin: who === "admin", faculty: who === "faculty" });
  await mockNoticesApi(page, { manager: who === "admin" });
  if (who === "student") {
    await mockCommunityApi(page);
    await mockAcademicApi(page);
    await mockIssuesApi(page);
  }
  if (who === "faculty") await mockTeachingApi(page);
  if (who === "admin") await mockManageApi(page);
}

const SCREENS: [Who, string][] = [
  ["guest", "/sign-in"],
  ["guest", "/register"],
  ["guest", "/forgot-password"],
  ["student", "/home"],
  ["student", "/notices"],
  ["student", "/community"],
  ["student", "/community/posts/p1"],
  ["student", "/academics/timetable"],
  ["student", "/academics/attendance"],
  ["student", "/academics/attendance/s1-A"],
  ["student", "/academics/results"],
  ["student", "/issues"],
  ["student", "/issues/new"],
  ["student", "/notifications"],
  ["student", "/account"],
  ["faculty", "/teaching"],
  ["faculty", "/teaching/sections/sec1"],
  ["faculty", "/teaching/sections/sec1?tab=assessments"],
  ["faculty", "/teaching/sections/sec1/attendance/new"],
  ["faculty", "/teaching/sessions/ses2"],
  ["faculty", "/teaching/assessments/as1"],
  ["admin", "/home"],
  ["admin", "/manage/requests"],
  ["admin", "/manage/members"],
  ["admin", "/manage/moderation"],
  ["admin", "/manage/academics"],
  ["admin", "/manage/academics/sections/sec1"],
  ["admin", "/manage/invites"],
  ["admin", "/manage/departments"],
  ["admin", "/manage/roster"],
  ["admin", "/manage/audit"],
  ["admin", "/notices/new"],
  ["platform", "/platform"],
];

// 360 px with the phone profile (touch: bigger targets), 768 px with the desktop one.
for (const [width, project] of [
  [360, "mobile"],
  [768, "desktop"],
] as const) {
  test.describe(`${width} px`, () => {
    test.use({ viewport: { width, height: 800 } });
    for (const [who, path] of SCREENS) {
      test(`${who} ${path}: no horizontal scroll`, async ({ page }, info) => {
        test.skip(info.project.name !== project, `${width} px runs with the ${project} profile`);
        await as(page, who);
        await page.goto(path);
        await expect(page.getByRole("heading", { level: 1 }).first()).toBeVisible();
        await page.waitForLoadState("networkidle");
        await expectNoHorizontalScroll(page);
      });
    }
  });
}
