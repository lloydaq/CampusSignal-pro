import { execFileSync } from "node:child_process";

import { expect, type Page } from "@playwright/test";

/**
 * An ACTIVE college with a CSE department and the people a journey needs, all signed-up and
 * verified, written straight to the disposable database the API uses. Signing up through the
 * screens is covered elsewhere (auth.spec.ts, exit-demo.spec.ts) and would use up the
 * registration limit per address; here the journey under test starts once people exist.
 */
const SCRIPT = `
import json
import sys
from datetime import UTC, datetime
from sqlalchemy.orm import Session
from app.core.config import get_settings
from app.core.db import create_db_engine
from app.core.security import hash_password
from app.models import College, CollegeMembership, CollegeStatus, Department, MembershipKind, MembershipStatus, Role, RoleGrant, User

run, password, prefix, people = sys.argv[1], sys.argv[2], sys.argv[3], json.loads(sys.argv[4])
now = datetime.now(UTC)
engine = create_db_engine(get_settings())
with Session(engine) as db:
    college = College(name=f"{prefix.title()} Demo College {run}", slug=f"{prefix}-{run}".lower(), timezone="Asia/Kolkata", status=CollegeStatus.ACTIVE)
    db.add(college)
    db.flush()
    cse = Department(college_id=college.id, code="CSE", name="Computer Science")
    db.add(cse)
    db.flush()
    for who, name, kind, in_cse, role in people:
        kind, role = MembershipKind(kind), Role(role) if role else None
        department_id = cse.id if in_cse else None
        user = User(email=f"e2e-{who}-{run}@northfield.example", password_hash=hash_password(password), display_name=name, email_verified_at=now)
        db.add(user)
        db.flush()
        membership = CollegeMembership(user_id=user.id, college_id=college.id, kind=kind, status=MembershipStatus.ACTIVE, department_id=department_id)
        db.add(membership)
        db.flush()
        if role:
            db.add(RoleGrant(college_id=college.id, membership_id=membership.id, role=role))
    db.commit()
engine.dispose()
`;

type Person = [who: string, name: string, kind: "STUDENT" | "FACULTY" | "STAFF", inCse: boolean, role: string | null];

function createCollege(run: string, password: string, prefix: string, people: Person[]): Record<string, string> {
  execFileSync("uv", ["run", "python", "-c", SCRIPT, run, password, prefix, JSON.stringify(people)], {
    cwd: "../backend",
    stdio: "pipe",
    env: {
      ...process.env,
      APP_ENV: "ci",
      APP_ORIGIN: "http://127.0.0.1:4174",
      DATABASE_URL: process.env.E2E_DATABASE_URL ?? "",
      LOG_LEVEL: "WARNING",
    },
  });
  return Object.fromEntries(people.map(([who]) => [who, `e2e-${who}-${run}@northfield.example`]));
}

/** A student, an issue coordinator (staff) and a faculty member (J5, J9). */
export function createIssueCollege(run: string, password: string): { student: string; coordinator: string; faculty: string } {
  const emails = createCollege(run, password, "issues", [
    ["student", "Ishita Verma", "STUDENT", true, null],
    ["coordinator", "Meera Iyer", "STAFF", false, "ISSUE_COORDINATOR"],
    ["faculty", "Ravi Sharma", "FACULTY", true, null],
  ]);
  return { student: emails.student!, coordinator: emails.coordinator!, faculty: emails.faculty! };
}

/** Two CSE students and a college admin who moderates (US-10). */
export function createCommunityCollege(run: string, password: string): { author: string; classmate: string; admin: string } {
  const emails = createCollege(run, password, "community", [
    ["author", "Ishita Verma", "STUDENT", true, null],
    ["classmate", "Kabir Shah", "STUDENT", true, null],
    ["admin", "Meera Iyer", "STAFF", false, "COLLEGE_ADMIN"],
  ]);
  return { author: emails.author!, classmate: emails.classmate!, admin: emails.admin! };
}

/** The password every account above gets, and a run id that keeps each run's rows apart. */
export const PASSWORD = "tidal-quartz-lantern";
export const unique = () => `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;

export async function signIn(page: Page, email: string) {
  await page.goto("/sign-in");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(PASSWORD);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/home$/);
}

export async function signOut(page: Page) {
  await page.goto("/account");
  await page.getByRole("button", { name: "Sign out", exact: true }).click();
  await expect(page.getByText("You've signed out.")).toBeVisible();
}
