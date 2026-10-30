import { execFileSync } from "node:child_process";

/**
 * An ACTIVE college with a student, an issue coordinator (staff) and a faculty member, all
 * signed-up and verified, written straight to the disposable database the API uses. Signing
 * up through the screens is covered elsewhere (auth.spec.ts, exit-demo.spec.ts) and would use
 * up the registration limit per address; here the journey under test starts once people exist.
 */
const SCRIPT = `
import sys
from datetime import UTC, datetime
from sqlalchemy.orm import Session
from app.core.config import get_settings
from app.core.db import create_db_engine
from app.core.security import hash_password
from app.models import College, CollegeMembership, CollegeStatus, Department, MembershipKind, MembershipStatus, Role, RoleGrant, User

run, password = sys.argv[1], sys.argv[2]
now = datetime.now(UTC)
engine = create_db_engine(get_settings())
with Session(engine) as db:
    college = College(name=f"Issue Demo College {run}", slug=f"issues-{run}".lower(), timezone="Asia/Kolkata", status=CollegeStatus.ACTIVE)
    db.add(college)
    db.flush()
    cse = Department(college_id=college.id, code="CSE", name="Computer Science")
    db.add(cse)
    db.flush()
    people = (
        ("student", "Ishita Verma", MembershipKind.STUDENT, cse.id, None),
        ("coordinator", "Meera Iyer", MembershipKind.STAFF, None, Role.ISSUE_COORDINATOR),
        ("faculty", "Ravi Sharma", MembershipKind.FACULTY, cse.id, None),
    )
    for who, name, kind, department_id, role in people:
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

export function createIssueCollege(run: string, password: string): { student: string; coordinator: string; faculty: string } {
  execFileSync("uv", ["run", "python", "-c", SCRIPT, run, password], {
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
  const email = (who: string) => `e2e-${who}-${run}@northfield.example`;
  return { student: email("student"), coordinator: email("coordinator"), faculty: email("faculty") };
}
