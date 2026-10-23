import { defineConfig } from "@playwright/test";

/**
 * Full-stack E2E (Phases.md 2d): the real API on a disposable PostgreSQL, real emails caught
 * by Mailpit, and the production build served by `vite preview`, which proxies /api to uvicorn.
 *
 * Needs E2E_DATABASE_URL (a loopback database whose name ends in `_test`; never Supabase) and
 * a Mailpit listening on SMTP 127.0.0.1:1025 with its API at MAILPIT_URL (default
 * http://127.0.0.1:8025). Migrations are applied before the API starts. Runs serially on one
 * desktop browser: it's a journey check, not a layout check (the mocked suite covers layouts).
 */

const PORT = 4174;
const BASE_URL = `http://127.0.0.1:${PORT}`;
const API_URL = "http://127.0.0.1:8000";
const isCI = Boolean(process.env.CI);

function disposableDatabaseUrl(): string {
  const raw = process.env.E2E_DATABASE_URL;
  if (!raw) throw new Error("Set E2E_DATABASE_URL to a disposable PostgreSQL database (see README).");
  // SQLAlchemy URL (postgresql+psycopg://...): parse it as a generic URL for the checks.
  const url = new URL(raw.replace(/^postgresql\+psycopg:/, "postgres:"));
  const host = url.hostname.replace(/^\[|\]$/g, "").toLowerCase();
  if (!raw.startsWith("postgresql+psycopg://")) throw new Error("E2E_DATABASE_URL must start with postgresql+psycopg://");
  if (!["localhost", "127.0.0.1", "::1"].includes(host)) throw new Error("E2E_DATABASE_URL must point at localhost");
  if (!url.pathname.replace(/^\//, "").endsWith("_test")) throw new Error("E2E_DATABASE_URL database name must end with _test");
  return raw;
}

const databaseUrl = disposableDatabaseUrl();

export default defineConfig({
  testDir: "./e2e-fullstack",
  fullyParallel: false,
  workers: 1,
  forbidOnly: isCI,
  retries: 0,
  reporter: isCI ? [["list"], ["html", { open: "never", outputFolder: "playwright-report-fullstack" }]] : "list",
  outputDir: "test-results-fullstack",
  use: {
    baseURL: BASE_URL,
    trace: "retain-on-failure",
  },
  projects: [{ name: "desktop", use: { browserName: "chromium", viewport: { width: 1280, height: 800 } } }],
  webServer: [
    {
      // Settings come from here, not from a developer's backend/.env (explicit values win).
      command: "uv run alembic upgrade head && uv run uvicorn app.main:app_factory --factory --host 127.0.0.1 --port 8000",
      cwd: "../backend",
      url: `${API_URL}/readyz`,
      reuseExistingServer: false,
      timeout: 120_000,
      env: {
        APP_ENV: "ci",
        APP_ORIGIN: BASE_URL,
        DATABASE_URL: databaseUrl,
        LOG_LEVEL: "WARNING",
        EMAIL_BACKEND: "smtp",
        SMTP_HOST: "127.0.0.1",
        SMTP_PORT: "1025",
        SMTP_SECURITY: "none",
        TRUSTED_PROXY_COUNT: "0",
      },
    },
    {
      command: `npm run build && npx vite preview --host 127.0.0.1 --port ${PORT} --strictPort`,
      url: BASE_URL,
      reuseExistingServer: false,
      timeout: 120_000,
    },
  ],
});
