import { execFileSync } from "node:child_process";

/**
 * Creates a platform-admin account the way an operator would (the service behind
 * `python -m app.cli create-platform-admin`), against the same disposable database the API
 * uses. The CLI itself prompts for the password on a terminal, which a test can't type into.
 * The password goes on the command line, which is fine for a throwaway test account.
 */
const SCRIPT = `
import sys
from datetime import UTC, datetime
from sqlalchemy.orm import Session
from app.core.config import get_settings
from app.core.db import create_db_engine
from app.services.platform_admins import create_platform_admin

engine = create_db_engine(get_settings())
with Session(engine) as db:
    create_platform_admin(db, email=sys.argv[1], display_name="Platform Ops", password=sys.argv[2], now=datetime.now(UTC))
engine.dispose()
`;

export function createPlatformAdmin(email: string, password: string): void {
  execFileSync("uv", ["run", "python", "-c", SCRIPT, email, password], {
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
}
