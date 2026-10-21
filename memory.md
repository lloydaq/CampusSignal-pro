# CampusSignal — Project Memory

Concise, verified state for new sessions. Details live in the linked documents; do not copy them here. Never store secrets here.

**Last updated:** 2026-10-21 (Phase 1, Step 2 — database, awaiting review)

## 1. Project
CampusSignal (official name, P-4) — multi-college campus platform: isolated college spaces with official notices, student community, department pages, private academic info (timetable, attendance, results), and campus issue reporting. Spec: `PRD.md`.

## 2. Repository status (verified 2026-10-21)
- Backend skeleton (Step 1, commit `003384a`) plus database layer (Step 2, uncommitted). No frontend or CI yet.
- Git: branch `master` tracking `origin` = https://github.com/lloydaq/CampusSignal-pro.git. History: `095ffef` docs → `af1ba7b` README (created on GitHub) → `fd94cea` Phase 0 completion → `003384a` Phase 1 Step 1. Owner commits and pushes; Claude does not push.
- `.gitignore` exists and was verified with `git check-ignore` (env files, venvs, `node_modules`, build output, local DBs/dumps/uploads, Caddy state, logs, and local AI-tool state: `.claude/settings.local.json`, `.impeccable/config.local.json`, `.impeccable/hook.cache.json`, `.impeccable/live/`).
- Root: `CLAUDE.md` (rewritten for CampusSignal), the six docs, `.gitignore`, and AI-tooling folders `.agent/`, `.agents/`, `.claude/`, `.codex/`, `.gemini/`, `.impeccable/` (~86 MB; skills/hooks incl. four copies of a Windows binary `impeccable.exe`; not product code). Owner decision (2026-10-20): kept **out** of version control for now; they show as untracked in `git status` — do not stage them.
- `.impeccable/design.json` describes an unrelated design system ("DataSentry") — `Design.md` is authoritative.
- No `.env`, keys, or database files present.
- Verified layout so far: `backend/app/{main.py, core/{config,db,errors,logging,middleware,request_context}.py, api/health.py}`, `backend/alembic.ini`, `backend/alembic/{env.py, script.py.mako, versions/0001_enable_citext.py, versions/0002_revoke_supabase_api_roles.py}`, `backend/tests/` (+ `tests/integration/`), `backend/pyproject.toml`, `backend/uv.lock`, `backend/.env.example`. Rest of `architecture.md` §5 is still proposed.

## 3. Confirmed stack (`architecture.md` §4, `CLAUDE.md`)
React + TypeScript + Vite, Tailwind, shadcn/ui, TanStack Query, React Router, react-hook-form + zod · Python 3.12 FastAPI, SQLAlchemy 2 (sync), Alembic, Pydantic v2, argon2-cffi, psycopg 3 · PostgreSQL 17 (dev: Supabase; CI: disposable service; prod: P-1) · pytest, Vitest, Playwright + axe · GitHub Actions · Caddy. Later: react-markdown + rehype-sanitize (Phase 4), openapi-typescript (dev). React major pinned in Phase 1.

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
| 1 Foundation | IN PROGRESS — Step 1 committed (`003384a`); Step 2 (database) implemented, awaiting owner review; Steps 3–4 not started |
| 2–11 | NOT STARTED |

Completed milestones (2026-10-20): documentation set; pre-development review; owner decisions P-4/P-7/P-8/P-9 applied; `CLAUDE.md` aligned; `.gitignore`; initial commit `095ffef`. Nothing implemented.

## 7. Known issues / limitations
- MVP accepts that a network-level retry can create a duplicate post/comment/issue (until NFR-REL-002).
- Privileged-session idle precision is ±5 min (last_seen write throttling).
- Routes registered as plain Starlette routes (FastAPI's OpenAPI/docs pages, local only) appear as `<unmatched>` in the access log.
- **Supabase API-role privileges (fixed by `0002`, verified on dev DB 2026-10-21):** no `anon`/`authenticated` grants remain on `public` tables (incl. `alembic_version`); `postgres`'s default privileges no longer grant them anything; probe table/sequence created afterwards got none. Residual: `supabase_admin`'s default grants in `public` (24 entries) can't be changed by `postgres` (it owns only the citext functions); PostgreSQL's built-in `PUBLIC` EXECUTE on new functions remains → Rules R-2.22. `0002` downgrade is a deliberate no-op. Data API itself could not be probed without an API key (gateway returns 401 first).
- Integration tests (`tests/integration/`, 6 tests) have **never passed**. CI workflow `.github/workflows/backend.yml` (added 2026-10-21, uncommitted; actionlint clean) runs them on a disposable `postgres:17.11` service, but GitHub Actions only runs after a push. Local attempt with embedded `pgserver` (PG 16.2) failed at `0001`: that build lacks the `citext` extension (environmental). Guard: localhost + `*_test` DB + no Supabase roles on the server, else the run stops; CI mode (`CAMPUSSIGNAL_REQUIRE_INTEGRATION=1`) fails instead of skipping.
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
- `uv run uvicorn app.main:app_factory --factory --reload` — requires `APP_ENV` and `APP_ORIGIN` (copy `.env.example` to `.env`); refuses to start without them
- `uv run alembic upgrade head` / `current` / `check` — verified against the Supabase dev DB (applied `0001`, then `0002`; now `0002 (head)`)
- `/readyz` → 503 `migrations: pending` before upgrade, 200 after; `/healthz` 200 throughout
- CI (not yet run): `.github/workflows/backend.yml` — locked `uv sync`, whole-tree `git diff --check`, ruff, format, mypy, compileall, unit tests, integration tests (must all run, 0 skipped), `alembic upgrade head` + `check` on the test DB.
Not yet verified: integration tests, CI workflow execution, frontend commands. Docker is no longer used.

## 10. Test / verification status
**Step 2 (2026-10-21, incl. `0002` + final review):** pytest 60 passed, 6 integration tests skipped (no `TEST_DATABASE_URL`; never run), also with `-W error::DeprecationWarning`; ruff, format, mypy, compileall, `git diff --check` clean; offline `alembic upgrade --sql` rendering tested. Final review fixes: integration guard now also refuses Supabase direct hosts (`*.supabase.co`, previously only `*.supabase.com`); engine `hide_parameters=True` so bound parameters never reach logged exceptions. Live on Supabase dev DB with real `.env`: Postgres 17.11, client TLS on, `citext` 1.6 in `public`; `0002` dry-run (rolled back) then applied; `alembic check` clean; `/healthz` 200, `/readyz` 200, 404/405 envelopes with matching request IDs and security headers. New deps: sqlalchemy 2.1.5, psycopg[binary] 3.3.6, alembic 1.20.0 (+ mako 1.4.3, markupsafe 3.0.4, tzdata 2026.5), all released ≥5 days before install.

**Step 1 (2026-10-21):**
- `pytest`: 29 passed (config, error envelope incl. 401/403/404/405/409/422/429/500, request IDs, security headers, access log, log scrubbing).
- `ruff check`, `ruff format --check`, `mypy` (strict, pydantic plugin): all clean.
- Manual smoke test with uvicorn: `/healthz` 200 with `X-Request-ID` + security headers; unknown route → 404 envelope; JSON access log without query string; startup fails without required env vars.
- Backend deps: fastapi 0.156.4, uvicorn 0.54.0, pydantic-settings 2.16.1; dev: pytest 9.1.1, httpx2 2.13.1 + httpcore2 2.13.1 (pinned `==2.13.1`: Starlette ≥1.2 test client prefers httpx2 and deprecates `httpx`; 2.13.1 chosen over the same-day 2.16.0 release), ruff 0.17.1, mypy 2.4.0.

## 11. Next task
Owner reviews Step 2 + the backend CI workflow, then pushes (owner-only) so GitHub Actions runs the 6 integration tests on disposable Postgres 17. Step 2 closes only when that run passes. Then Step 3 (frontend shell).
