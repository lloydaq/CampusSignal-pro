# CampusSignal — Project Memory

Concise, verified state for new sessions. Details live in the linked documents; do not copy them here. Never store secrets here.

**Last updated:** 2026-10-21 (Phase 1, Step 1 — backend skeleton)

## 1. Project
CampusSignal (official name, P-4) — multi-college campus platform: isolated college spaces with official notices, student community, department pages, private academic info (timetable, attendance, results), and campus issue reporting. Spec: `PRD.md`.

## 2. Repository status (verified 2026-10-21)
- Backend skeleton exists in `backend/` (Phase 1 Step 1). No database, frontend, or CI yet.
- Git: branch `master` tracking `origin` = https://github.com/lloydaq/CampusSignal-pro.git. History: `095ffef` docs → `af1ba7b` README (created on GitHub) → `fd94cea` Phase 0 completion. Pushes only with owner approval.
- `.gitignore` exists and was verified with `git check-ignore` (env files, venvs, `node_modules`, build output, local DBs/dumps/uploads, Caddy state, logs, and local AI-tool state: `.claude/settings.local.json`, `.impeccable/config.local.json`, `.impeccable/hook.cache.json`, `.impeccable/live/`).
- Root: `CLAUDE.md` (rewritten for CampusSignal), the six docs, `.gitignore`, and AI-tooling folders `.agent/`, `.agents/`, `.claude/`, `.codex/`, `.gemini/`, `.impeccable/` (~86 MB; skills/hooks incl. four copies of a Windows binary `impeccable.exe`; not product code). Owner decision (2026-10-20): kept **out** of version control for now; they show as untracked in `git status` — do not stage them.
- `.impeccable/design.json` describes an unrelated design system ("DataSentry") — `Design.md` is authoritative.
- No `.env`, keys, or database files present.
- Verified layout so far: `backend/app/{main.py, core/{config,errors,logging,middleware,request_context}.py, api/health.py}`, `backend/tests/`, `backend/pyproject.toml`, `backend/uv.lock`, `backend/.env.example`. Rest of `architecture.md` §5 is still proposed.

## 3. Confirmed stack (`architecture.md` §4, `CLAUDE.md`)
React + TypeScript + Vite, Tailwind, shadcn/ui, TanStack Query, React Router, react-hook-form + zod · Python 3.12 FastAPI, SQLAlchemy 2 (sync), Alembic, Pydantic v2, argon2-cffi, psycopg 3 · PostgreSQL 16 · pytest, Vitest, Playwright + axe · GitHub Actions · Caddy. Later: react-markdown + rehype-sanitize (Phase 4), openapi-typescript (dev). React major pinned in Phase 1.

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

## 5. Tenant isolation model (detail: `architecture.md` §9)
College derived from session's ACTIVE membership on `/api/v1/campus/*` (no client college IDs) → `college_id`-scoped repositories → policies in `app/policies/` → composite `(college_id, id)` FKs. Cross-college → 404. Isolation test suite from Phase 3.

## 6. Implementation status
| Phase | Status |
|---|---|
| 0 Setup & docs | DONE (verified 2026-10-20, commit `095ffef`) |
| 1 Foundation | IN PROGRESS — Step 1 (backend skeleton) done, awaiting owner review; Steps 2–4 not started |
| 2–11 | NOT STARTED |

Completed milestones (2026-10-20): documentation set; pre-development review; owner decisions P-4/P-7/P-8/P-9 applied; `CLAUDE.md` aligned; `.gitignore`; initial commit `095ffef`. Nothing implemented.

## 7. Known issues / limitations
- MVP accepts that a network-level retry can create a duplicate post/comment/issue (until NFR-REL-002).
- Privileged-session idle precision is ±5 min (last_seen write throttling).
- Routes registered as plain Starlette routes (FastAPI's OpenAPI/docs pages, local only) appear as `<unmatched>` in the access log.
- `/readyz`, DB session and Alembic arrive in Step 2; Docker Desktop must be running for it.

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
Not yet verified: docker compose, alembic, frontend commands.

## 10. Test / verification status (2026-10-21, Step 1)
- `pytest`: 29 passed (config, error envelope incl. 401/403/404/405/409/422/429/500, request IDs, security headers, access log, log scrubbing).
- `ruff check`, `ruff format --check`, `mypy` (strict, pydantic plugin): all clean.
- Manual smoke test with uvicorn: `/healthz` 200 with `X-Request-ID` + security headers; unknown route → 404 envelope; JSON access log without query string; startup fails without required env vars.
- Backend deps: fastapi 0.156.4, uvicorn 0.54.0, pydantic-settings 2.16.1; dev: pytest 9.1.1, httpx2 2.13.1 + httpcore2 2.13.1 (pinned `==2.13.1`: Starlette ≥1.2 test client prefers httpx2 and deprecates `httpx`; 2.13.1 chosen over the same-day 2.16.0 release), ruff 0.17.1, mypy 2.4.0.

## 11. Next task
Owner reviews Phase 1 Step 1. Then Step 2 (database): `docker-compose.yml` (Postgres 16 + Mailpit), SQLAlchemy engine/session, Alembic + `citext` migration, `/readyz` — needs Docker Desktop running.
