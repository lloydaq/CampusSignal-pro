# CampusSignal — Project Memory

Concise, verified state for new sessions. Details live in the linked documents; do not copy them here. Never store secrets here.

**Last updated:** 2026-10-21 (Phase 1, Steps 3–4 — frontend shell, frontend CI, E2E, README; awaiting review)

## 1. Project
CampusSignal (official name, P-4) — multi-college campus platform: isolated college spaces with official notices, student community, department pages, private academic info (timetable, attendance, results), and campus issue reporting. Spec: `PRD.md`.

## 2. Repository status (verified 2026-10-21)
- Backend (Steps 1–2) merged on `master` at `0213f34` (PR #1). Uncommitted: the ASGI entry-point fix (`backend/app/main.py` lazy `app`, `backend/tests/test_entrypoints.py`), the Step 3 frontend shell (`frontend/`) and Step 4 (`.github/workflows/frontend.yml`, `frontend/e2e/`, `frontend/playwright.config.ts`, README, architecture.md §18 routing contract).
- Git: branch `master` tracking `origin` = https://github.com/lloydaq/CampusSignal-pro.git. History: `095ffef` docs → `af1ba7b` README → `fd94cea` Phase 0 → `003384a` Step 1 → `69b3e5b`/`0213f34` Step 2 (merge of PR #1). Owner commits and pushes; Claude does not.
- `.gitignore` exists and was verified with `git check-ignore` (env files, venvs, `node_modules`, build output, local DBs/dumps/uploads, Caddy state, logs, and local AI-tool state: `.claude/settings.local.json`, `.impeccable/config.local.json`, `.impeccable/hook.cache.json`, `.impeccable/live/`).
- Root: `CLAUDE.md` (rewritten for CampusSignal), the six docs, `.gitignore`, and AI-tooling folders `.agent/`, `.agents/`, `.claude/`, `.codex/`, `.gemini/`, `.impeccable/` (~86 MB; skills/hooks incl. four copies of a Windows binary `impeccable.exe`; not product code). Owner decision (2026-10-20): kept **out** of version control for now; they show as untracked in `git status` — do not stage them.
- `.impeccable/design.json` describes an unrelated design system ("DataSentry") — `Design.md` is authoritative.
- No `.env`, keys, or database files present.
- Verified layout so far: `backend/app/{main.py, core/{config,db,errors,logging,middleware,request_context}.py, api/health.py}`, `backend/alembic.ini`, `backend/alembic/{env.py, script.py.mako, versions/0001_enable_citext.py, versions/0002_revoke_supabase_api_roles.py}`, `backend/tests/` (+ `tests/integration/`), `backend/pyproject.toml`, `backend/uv.lock`, `backend/.env.example`. `frontend/{package.json, package-lock.json, vite.config.ts, eslint.config.js, tsconfig*.json, components.json, index.html}`, `frontend/src/{main.tsx, app/{App, routes, queryClient, shells/AuthShell}, components/{Wordmark, ThemeSwitcher, ui/button}, features/{auth, system-status}, lib/{api, theme, utils}, styles/{tokens.css, index.css, contrast.ts}, test/}`, `.github/workflows/backend.yml`. Rest of `architecture.md` §5 is still proposed.

## 3. Confirmed stack (`architecture.md` §4, `CLAUDE.md`)
React + TypeScript + Vite, Tailwind, shadcn/ui, TanStack Query, React Router, react-hook-form + zod · Python 3.12 FastAPI, SQLAlchemy 2 (sync), Alembic, Pydantic v2, argon2-cffi, psycopg 3 · PostgreSQL 17 (dev: Supabase; CI: disposable service; prod: P-1) · pytest, Vitest, Playwright + axe · GitHub Actions · Caddy. Later: react-markdown + rehype-sanitize (Phase 4), openapi-typescript (dev). Frontend pinned 2026-10-21: React 19.3.1, react-router 8.4.0, TanStack Query 5.104.3, Tailwind 4.3.3, Vite 8.3.4, TypeScript 6.0.3 (TS 7 is not yet supported by typescript-eslint), Vitest 5.0.5, ESLint 10.13.0; all at least 5 days old at install.

## 4. Key decisions (rationale in `architecture.md` §23)
- Modular monolith, same-origin SPA behind Caddy (ADR-01, ADR-09).
- Server-side sessions in Postgres, HttpOnly cookies, CSRF + Origin checks (ADR-04).
- **Privileged sessions** (P-8, AUTH-013, ADR-12): FACULTY members and COLLEGE_ADMIN/DEPARTMENT_ADMIN grants → 24 h idle / 7 d absolute, evaluated per request; others 7 d / 30 d. Subject to Phase 9 review.
- **Separate platform-admin accounts** (P-7, ADR-13): a PLATFORM_ADMIN account cannot join a college.
- **MVP trims** (P-9): scheduled notice publishing (NOTICE-011), audience by kind (NOTICE-012), idempotency keys (NFR-REL-002) → Phase 11.
- No Redis/queues/WebSockets: DB rate limits, hourly Jobs CLI for purges, notification polling (ADR-05/06/07).
- Membership proof = roster or invite; uniform request responses; admin-only member directory (PRD §9.2, §17).
- One ACTIVE college membership per user (MEMBER-008). Platform admins cannot read college data (ADMIN-008).
- No uploads and no events in MVP; RLS deferred (ADR-10).
- **Dev database = Supabase** (ADR-14, 2026-10-21): Postgres 17 via session pooler (IPv4, port 5432) with `sslmode=require`; plain SQLAlchemy + psycopg 3, no Supabase client libraries; Data API disabled by owner and API-role privileges revoked in the DB by migration `0002`; no Docker locally; destructive integration tests only on CI's disposable Postgres 17; `citext` in `public`. Supabase approved for development only.

## 5. Tenant isolation model (detail: `architecture.md` §9)
College derived from session's ACTIVE membership on `/api/v1/campus/*` (no client college IDs) → `college_id`-scoped repositories → policies in `app/policies/` → composite `(college_id, id)` FKs. Cross-college → 404. Isolation test suite from Phase 3.

## 6. Implementation status
| Phase | Status |
|---|---|
| 0 Setup & docs | DONE (verified 2026-10-20, commit `095ffef`) |
| 1 Foundation | IN PROGRESS — Steps 1–2 done (Step 2 verified by CI on `0213f34`); Steps 3–4 implemented and verified locally, awaiting owner review; `frontend.yml` not yet run on GitHub |
| 2–11 | NOT STARTED |

Completed milestones (2026-10-20): documentation set; pre-development review; owner decisions P-4/P-7/P-8/P-9 applied; `CLAUDE.md` aligned; `.gitignore`; initial commit `095ffef`. Nothing implemented.

## 7. Known issues / limitations
- MVP accepts that a network-level retry can create a duplicate post/comment/issue (until NFR-REL-002).
- Privileged-session idle precision is ±5 min (last_seen write throttling).
- Routes registered as plain Starlette routes (FastAPI's OpenAPI/docs pages, local only) appear as `<unmatched>` in the access log.
- **Supabase API-role privileges (fixed by `0002`, verified on dev DB 2026-10-21):** no `anon`/`authenticated` grants remain on `public` tables (incl. `alembic_version`); `postgres`'s default privileges no longer grant them anything; probe table/sequence created afterwards got none. Residual: `supabase_admin`'s default grants in `public` (24 entries) can't be changed by `postgres` (it owns only the citext functions); PostgreSQL's built-in `PUBLIC` EXECUTE on new functions remains → Rules R-2.22. `0002` downgrade is a deliberate no-op. Data API itself could not be probed without an API key (gateway returns 401 first).
- Integration tests (6) passed in GitHub Actions on `0213f34` (disposable `postgres:17.11`). They never run locally (no disposable Postgres here); locally they skip.
- `backend/.env` verified complete 2026-10-21 (structure only): `APP_ENV=local`, `APP_ORIGIN=http://localhost:5173`, `DATABASE_URL` with `postgresql+psycopg://`, session pooler, `sslmode=require`.
- Supabase free plan: pauses after 1 week idle (`/readyz` → 503 until restored), 500 MB, no backups/PITR, logs 1 day.
- `pg_stat_ssl` shows `ssl=false` through the pooler (pooler→DB leg); the client→pooler connection is TLS (`ssl_in_use=True`).
- On Windows the DB-down unit test takes ~5 s (connect timeout; Windows doesn't refuse closed loopback ports instantly).

## 8. Open decisions
| ID | Decision | Needed by |
|---|---|---|
| P-1 | Hosting provider (staging + prod) | Phase 4 |
| P-2 | Transactional email provider | Phase 2 (non-local email) |
| P-3 | Pilot college + data-processing agreement | Before real data (Phase 10) |
| P-5 | Attendance edit window default (48 h assumed) | Phase 7 |
| P-6 | Error tracking (Sentry with scrubbing, or none) | Phase 10 |
| P-10 | Should platform-admin sessions also use privileged limits? (recommended: yes) | Phase 3 |
Resolved: P-4, P-7, P-8, P-9 (2026-10-20). Assumptions to validate: PRD §21 (A1–A4).

## 9. Commands
Verified 2026-10-21 (Windows, Git Bash; uv 0.13.1 provides managed CPython 3.12.10), from `backend/`:
- `uv sync` — installs pinned deps from `uv.lock`
- `uv run pytest -q` · `uv run ruff check .` · `uv run ruff format --check .` · `uv run mypy`
- `uv run uvicorn app.main:app --reload` (lazy module attribute, verified 2026-10-21) or `uv run uvicorn app.main:app_factory --factory --reload` — both need `APP_ENV`, `APP_ORIGIN`, `DATABASE_URL` (copy `.env.example` to `.env`); refuse to start without them. Importing `app.main` never reads settings.
- `uv run alembic upgrade head` / `current` / `check` — verified against the Supabase dev DB (applied `0001`, then `0002`; now `0002 (head)`)
- `/readyz` → 503 `migrations: pending` before upgrade, 200 after; `/healthz` 200 throughout
- CI (passing on `0213f34`): `.github/workflows/backend.yml` — locked `uv sync`, whole-tree `git diff --check`, ruff, format, mypy, compileall, unit tests, integration tests (must all run, 0 skipped), `alembic upgrade head` + `check` on the test DB.
From `frontend/` (verified 2026-10-21, Node 24.15, npm 11.12): `npm install` · `npm run dev` (Vite on http://localhost:5173 — it listens on the IPv6 loopback, so use `localhost`, not `127.0.0.1`; proxies `/api`, `/healthz`, `/readyz` to `127.0.0.1:8000`) · `npm test` · `npm run lint` · `npm run typecheck` · `npm run build`.
`npx playwright install chromium` (once) · `npm run e2e` (builds, serves `vite preview` on 127.0.0.1:4173, mocks every backend call; desktop 1280 px + mobile 390 px touch).
Not yet verified: `.github/workflows/frontend.yml` on GitHub (needs a push). Docker is no longer used.

## 10. Test / verification status
**Step 4 (2026-10-21):** Playwright 27 passed, 1 skipped by design (44 px touch-target test runs on the mobile project only); axe found zero WCAG 2.0/2.1/2.2 A/AA violations (light, dark, error state, 404; both viewports). A mutation check (removing the coarse-pointer sizing) made the touch-target test fail, then pass after restore. CI sequence (`npm ci`, lint, typecheck, 83 Vitest, build, e2e) passed from a clean copy with `CI=true`. actionlint clean for both workflows. Built `index.html` has no inline scripts or styles (CSP-ready). README PowerShell commands checked (`Invoke-RestMethod`, `Copy-Item`, env vars). New dev deps: @playwright/test 1.64.1, @axe-core/playwright 4.14.0 (≥5 days old). Note: on Windows, `npm ci` fails with EPERM while a Vite server from the same `node_modules` is running (native lightningcss module locked) — stop dev servers first.

**Step 3 (2026-10-21):** frontend Vitest 83 passed (6 files: API client, retry policy, theme, service status states, routes/404/theme radios, WCAG contrast for both themes); ESLint (type-aware), `tsc -b` (strict), `vite build` clean; initial JS 121.65 kB gzip (NFR-PERF-002 budget 250 kB). Browser check at 1280 px and 390 px, light and dark: live status Running/Ready through the dev proxy against the owner's running backend; explicit Light overrides OS dark; 44 px touch targets on coarse pointers; visible keyboard focus; no horizontal overflow. The contrast check found light `--border-strong` at 2.89:1 on `--bg`, so it was darkened to `#868FA0` (Design.md updated). Backend after the entry-point fix: 72 passed, 6 skipped.

**Step 2 (2026-10-21, incl. `0002` + final review):** pytest 60 passed, 6 integration tests skipped (no `TEST_DATABASE_URL`; never run), also with `-W error::DeprecationWarning`; ruff, format, mypy, compileall, `git diff --check` clean; offline `alembic upgrade --sql` rendering tested. Final review fixes: integration guard now also refuses Supabase direct hosts (`*.supabase.co`, previously only `*.supabase.com`); engine `hide_parameters=True` so bound parameters never reach logged exceptions. Live on Supabase dev DB with real `.env`: Postgres 17.11, client TLS on, `citext` 1.6 in `public`; `0002` dry-run (rolled back) then applied; `alembic check` clean; `/healthz` 200, `/readyz` 200, 404/405 envelopes with matching request IDs and security headers. New deps: sqlalchemy 2.1.5, psycopg[binary] 3.3.6, alembic 1.20.0 (+ mako 1.4.3, markupsafe 3.0.4, tzdata 2026.5), all released ≥5 days before install.

**Step 1 (2026-10-21):**
- `pytest`: 29 passed (config, error envelope incl. 401/403/404/405/409/422/429/500, request IDs, security headers, access log, log scrubbing).
- `ruff check`, `ruff format --check`, `mypy` (strict, pydantic plugin): all clean.
- Manual smoke test with uvicorn: `/healthz` 200 with `X-Request-ID` + security headers; unknown route → 404 envelope; JSON access log without query string; startup fails without required env vars.
- Backend deps: fastapi 0.156.4, uvicorn 0.54.0, pydantic-settings 2.16.1; dev: pytest 9.1.1, httpx2 2.13.1 + httpcore2 2.13.1 (pinned `==2.13.1`: Starlette ≥1.2 test client prefers httpx2 and deprecates `httpx`; 2.13.1 chosen over the same-day 2.16.0 release), ruff 0.17.1, mypy 2.4.0.

## 11. Next task
Owner reviews the ASGI entry-point fix and Steps 3–4, then commits and pushes so `frontend.yml` runs on GitHub. When both workflows are green, mark Steps 3–4 done and close Phase 1 (exit criteria in Phases.md). Next: Phase 2 — identity and platform bootstrap (plan first).
