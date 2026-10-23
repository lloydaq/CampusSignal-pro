# CampusSignal

Multi-college campus platform: each college gets an isolated, private space with official notices, a moderated student community, department pages, private academic information (timetable, attendance, results), and campus issue reporting. Cross-college content is limited to explicitly public features (none in the MVP beyond the college directory used for joining).

## Read first
1. `memory.md` — verified current state, pending decisions, next task.
2. `Phases.md` — the current phase and its unchecked tasks (execution protocol in §1).
3. The sections of `PRD.md` (what), `architecture.md` (how), `Rules.md` (engineering rules), `Design.md` (UI/UX) that the task touches.

These six documents are authoritative. If code and docs disagree, report it; don't silently pick one.

## Stack
- Frontend: React + TypeScript (Vite), Tailwind CSS, shadcn/ui, TanStack Query, React Router, react-hook-form + zod
- Backend: Python 3.12 + FastAPI, SQLAlchemy 2.x (sync), Alembic, Pydantic v2, argon2-cffi, psycopg 3
- DB: PostgreSQL 17 — development on a hosted Supabase project (session pooler, SSL, Data API disabled; plain SQLAlchemy, no Supabase client libraries); CI on a disposable Postgres 17 service. No Docker needed locally
- Tests: pytest (+ FastAPI/Starlette TestClient on httpx2) for backend; Vitest + Testing Library for frontend; Playwright + axe for E2E
- CI: GitHub Actions. Deploy: Caddy + API + scheduled jobs CLI (`architecture.md` §18)
- Not used (see ADRs): microservices, Redis, queues, WebSockets, GraphQL, Kubernetes

## Commands (`memory.md` §9 records which ones have been verified)
```bash
# Backend (from backend/; copy .env.example to .env first)
uv sync
uv run alembic upgrade head
uv run uvicorn app.main:app --reload   # or: uvicorn app.main:app_factory --factory --reload
uv run pytest -q                 # unit + DB tests; DB tests need TEST_DATABASE_URL (local PG 17 or CI)
# TEST_DATABASE_URL must be a DISPOSABLE Postgres 17 (tests downgrade migrations); never Supabase.
# The guard requires a localhost host and a *_test database; CI: .github/workflows/backend.yml
uv run ruff check . && uv run ruff format --check . && uv run mypy

# Frontend (from frontend/)
npm install
npm run dev
npm run typecheck && npm run lint && npm run build
npm test                         # Vitest (unit/component + WCAG token contrast)
npx playwright install chromium  # once
npm run e2e                      # Playwright + axe smoke tests (mocked backend, 1280/390 px)
```
Run the relevant tests + lint before saying a task is done (`Rules.md` §8).

## Repository layout (proposed in `architecture.md` §5)
```
backend/app/
  main.py          # app factory, router registration
  core/            # config, db session, security (hashing, sessions, csrf, rate limits)
  api/v1/          # routers only: parse request, call service, return schema
  models/          # SQLAlchemy models
  schemas/         # Pydantic request/response models
  services/        # business logic
  repositories/    # DB queries (college-scoped functions require college_id)
  policies/        # ALL authorization decisions live here
  jobs/            # scheduled jobs CLI (retention purges)
  cli/             # create-platform-admin, seed-demo
backend/tests/
frontend/src/features/<feature>/   # auth, campus, notices, community, issues, academic, notifications, admin, platform
```
Add folders only when a feature needs them.

## Security rules (non-negotiable — full list in `Rules.md` §2)
1. **Every protected endpoint calls a policy in `app/policies/`** (e.g. `can_read_post(actor, post)`). No inline ad-hoc permission checks in routers.
2. **Never trust tenant identity from the client.** `college_id`, role, or membership in a request body/URL/header is a *request*, not a fact. Campus endpoints derive the college from the authenticated user's ACTIVE membership in the DB.
3. **Load the object, then authorize it** — knowing an ID grants nothing (prevent IDOR). Applies to notices, posts, comments, reactions, reports, issues, attendance, results, enrollments, members, notifications.
4. Unauthorized access to another college's resource returns **404**, not 403, so existence doesn't leak.
5. Search, lists, feeds, and counts apply the **same** policies as single-object reads.
6. Frontend hiding a button is UX, not security.
7. Passwords: Argon2id. Auth: server-side sessions in HttpOnly, Secure, SameSite=Lax cookies with CSRF tokens — no tokens in localStorage. Faculty and college/department admin sessions use shorter limits (AUTH-013).
8. Platform admins never read college content or academic records, and a platform-admin account cannot join a college (ADMIN-002, ADMIN-008).
9. Never log passwords, session IDs, tokens, roll numbers, emails, or academic data. Never commit secrets; use `.env` (keep `.env.example` updated).

## Testing rules
- Every new endpoint ships with: one **allow** test, one **cross-college deny** test, and one **wrong-role deny** test where roles apply.
- Deny tests also assert the response body leaks no private fields.
- New college-scoped routes are added to the tenant isolation suite and route inventory test.
- For security work: write the failing tests first, then implement.
- Use factories/fixtures with at least two fictional colleges ("Northfield Institute", "Riverside College").

## Data & migrations
- All schema changes via Alembic (`alembic revision --autogenerate -m "..."`); review the generated file before applying; keep a working downgrade.
- UUID primary keys, real foreign keys, unique constraints for business rules (one reaction per member per post, one attendance session per section/date/slot, one active membership per user).
- College-scoped tables carry `college_id` and use composite `(college_id, id)` foreign keys. Platform-wide tables (users, sessions) don't.
- Use transactions and row locks / optimistic `version` checks for contested updates (attendance, results, issues).
- Cursor-based pagination for all collections.

## Frontend & design
- Follow `Design.md`; use the frontend-design skill for any new screen or visual change.
- Deep blue primary + one warm accent used sparingly; Space Grotesk headings, IBM Plex Sans body, IBM Plex Mono for codes. No gradients, glows, or generic dashboard card grids.
- Every notice and post shows an audience badge (Department / College). A "Public" badge is reserved for future cross-college content and must stay visually distinct.
- Official notices look clearly different from student posts.
- Every data view has loading, empty, and error states. Mobile-first, accessible (labels, focus states, contrast).
- Build with shadcn/ui components; colors/spacing/radii as theme tokens, never one-off values.
- After UI changes, check them in the browser (Playwright screenshots at 390 px and 1280 px, light and dark) and fix what looks off.

## Working style
- Work one vertical slice at a time (model → migration → policy → service → route → tests → UI).
- For anything bigger than a small fix, propose a plan first and wait for approval.
- Stay inside the current phase; don't start later phases silently.
- Keep changes focused; don't refactor unrelated code.
- Don't add new dependencies without saying why.
- Academic data (attendance, marks): synthetic, clearly labelled demo data only. Never scrape or connect to college ERPs.
- Update `memory.md` after completing work; never claim tests passed unless they ran.

## Current phase
Phase 2 — identity and platform bootstrap, in progress (2a and 2b merged; 2c on review; see `Phases.md`). Update this line as phases complete.
