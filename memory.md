# CampusSignal — Project Memory

Concise, verified state for new sessions. Details live in the linked documents; do not copy them here. Never store secrets here.

**Last updated:** 2026-10-20 (Phase 0 finalization)

## 1. Project
CampusSignal (official name, P-4) — multi-college campus platform: isolated college spaces with official notices, student community, department pages, private academic info (timetable, attendance, results), and campus issue reporting. Spec: `PRD.md`.

## 2. Repository status (verified 2026-10-20)
- **No application code exists.** Implementation has not started.
- Git: branch `master`, **no commits**, no remote. All files untracked.
- `.gitignore` exists and was verified with `git check-ignore` (env files, venvs, `node_modules`, build output, local DBs/dumps/uploads, Caddy state, logs, and local AI-tool state: `.claude/settings.local.json`, `.impeccable/config.local.json`, `.impeccable/hook.cache.json`, `.impeccable/live/`).
- Root: `CLAUDE.md` (rewritten for CampusSignal), the six docs, `.gitignore`, and AI-tooling folders `.agent/`, `.agents/`, `.claude/`, `.codex/`, `.gemini/`, `.impeccable/` (~86 MB; skills/hooks incl. four copies of a Windows binary `impeccable.exe`; not product code). Whether to commit them is an open owner decision.
- `.impeccable/design.json` describes an unrelated design system ("DataSentry") — `Design.md` is authoritative.
- No `.env`, keys, or database files present.
- Directory structure in `architecture.md` §5 is **proposed**, not verified.

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
| 0 Setup & docs | IN PROGRESS — all doc decisions applied, `.gitignore` added; awaiting owner's first commit and tooling-folder decision |
| 1–11 | NOT STARTED |

Completed milestones (2026-10-20): documentation set; pre-development review; owner decisions P-4/P-7/P-8/P-9 applied; `CLAUDE.md` aligned; `.gitignore`. Nothing implemented.

## 7. Known issues / limitations
- MVP accepts that a network-level retry can create a duplicate post/comment/issue (until NFR-REL-002).
- Privileged-session idle precision is ±5 min (last_seen write throttling).

## 8. Open decisions
| ID | Decision | Needed by |
|---|---|---|
| P-1 | Hosting provider (staging + prod) | Phase 4 |
| P-2 | Transactional email provider | Phase 2 (non-local email) |
| P-3 | Pilot college + data-processing agreement | Before real data (Phase 10) |
| P-5 | Attendance edit window default (48 h assumed) | Phase 7 |
| P-6 | Error tracking (Sentry with scrubbing, or none) | Phase 10 |
| P-10 | Should platform-admin sessions also use privileged limits? (recommended: yes) | Phase 3 |
| — | Commit AI-tooling folders or keep them local | First commit |
Resolved: P-4, P-7, P-8, P-9 (2026-10-20). Assumptions to validate: PRD §21 (A1–A4).

## 9. Commands
None verified — no code exists. Planned commands are in `CLAUDE.md`; record verified versions here after Phase 1.

## 10. Test / verification status
No application tests exist. Documentation consistency checks (requirement IDs, phase mapping, rule references) and `git check-ignore` checks were run on 2026-10-20.

## 11. Next task
Owner: decide on tooling folders, make the first commit. Then Phase 1, first task: backend skeleton (uv project, FastAPI app factory, settings, error envelope, `/healthz`) + `docker-compose.yml` with Postgres 16 — see `Phases.md` Phase 1.
