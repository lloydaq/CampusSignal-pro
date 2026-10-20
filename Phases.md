# CampusSignal — Implementation Phases

| | |
|---|---|
| Last updated | 2026-10-20 |
| Current phase | **Phase 0 — in progress** (documentation drafted; pending decisions open) |

Status values: `NOT STARTED` · `IN PROGRESS` · `DONE (verified <date>)`. A phase is DONE only per §4 and `Rules.md` §8 — never because files exist.

---

## 1. Phase execution protocol

Every coding session working on a phase MUST:

1. Read `memory.md`, then this file's current phase, then the referenced sections of `PRD.md`, `architecture.md`, `Rules.md`, `Design.md`.
2. Inspect the actual repository and `git status`; reconcile with `memory.md` (repo wins; fix memory if it is wrong).
3. Identify the current phase and its unchecked tasks.
4. Propose a plan for the selected task(s); wait for approval for anything beyond a small fix.
5. Implement only work belonging to that phase. Do not silently start later phases.
6. Add or update tests per `Rules.md` §5.
7. Run the verification commands; record real results.
8. Review security and tenant isolation with the `Rules.md` §2 checklist.
9. Update `memory.md` (completed work, decisions, limitations).
10. Update task checkboxes/phase status here only after verification.
11. Finish with the completion report from `Rules.md` §8.

## 2. Incremental release strategy

| Release | After phase | Environment | Who uses it | Contents |
|---|---|---|---|---|
| α | 4 | Staging, synthetic data | Team + 2–3 friendly testers | Accounts, college onboarding, verification, departments, notices, in-app notifications |
| β | 6 | Staging, synthetic data | Internal pilot group | + campus issues, community |
| MVP | 10 | Production | Pilot college (after data agreement P-3) | + Academic Hub, home screens, hardening |
| 1.1 | 11 | Production | Pilot+ | P1 features |

Reordering versus the original outline (and why): **notices** precede academics because they are the simplest valuable module and validate the policy/tenant patterns on low-risk data; **in-app notifications** are built with notices (Phase 4) because later modules depend on them; **Academic Hub** comes after community/issues so the most sensitive data is built on matured, tested authorization patterns; **events** move to Phase 11 (P1).

## 3. Requirement → phase map (P0)

| Phase | Requirements |
|---|---|
| 1 | TENANT-004 (conventions), NFR-SEC-002/003/004, NFR-OPS-001, NFR-I18N-001 (setup) |
| 2 | AUTH-001…010, ADMIN-005, ADMIN-006 (infrastructure + auth events) |
| 3 | AUTH-013, MEMBER-001…011, TENANT-001…005, DEPT-001/002, ADMIN-001…004, ADMIN-007/008 |
| 4 | NOTICE-001…007, DEPT-003/004, NOTIF-001…005 (+ membership notifications) |
| 5 | ISSUE-001…009 |
| 6 | COMMUNITY-001…010 |
| 7 | ACADEMIC-001…010 |
| 8 | HOME-001…004, PROFILE-001 |
| 9 | NFR-SEC-*, NFR-PERF-001/002, NFR-A11Y-001, NFR-MAINT-001, PRD §17–§19 verification |
| 10 | NFR-REL-001, NFR-SEC-001, PRD §23 release criteria |
| 11 | All P1 items (PRD §12) |

---

## Phase 0 — Repository inspection, requirements validation, setup
**Status:** IN PROGRESS
**Objective:** A verified starting point and answered blocking decisions.
**Dependencies:** none.
**Included:** repository inspection; the six documentation files; decision log.
**Excluded:** any application code.

Tasks:
- [x] Inspect repository (no app code, no git repo, `CLAUDE.md` present — see `memory.md`).
- [x] Draft `PRD.md`, `architecture.md`, `Rules.md`, `Phases.md`, `Design.md`, `memory.md`.
- [x] Owner approved the documents; P-4 resolved — CampusSignal is the official name; `CLAUDE.md` rewritten to match (2026-10-20).
- [ ] Decide P-1 hosting (needed by Phase 4 for staging) and P-2 email provider (needed by Phase 2 for real delivery; Mailpit suffices locally). Not blocking Phase 0 exit.
- [x] `git init` (done by owner; branch `master`, no commits as of 2026-10-20).
- [x] Pre-development architecture review; documentation fixes applied (2026-10-20).
- [x] P-7, P-8, P-9 decided and applied to all documents (2026-10-20).
- [x] `.gitignore` added (R-7.4) and verified with `git check-ignore` (2026-10-20).
- [ ] Owner decides whether AI-tooling folders (`.agent/`, `.agents/`, `.claude/`, `.codex/`, `.gemini/`, `.impeccable/`, ~86 MB incl. four copies of a Windows binary) are committed.
- [ ] Owner makes the first commit (docs, `CLAUDE.md`, `.gitignore`); create GitHub repository.

**Definition of done / exit criteria:** owner has approved the documents; P-4, P-7, P-8, P-9 resolved; `.gitignore` in place; first commit exists. (P-1/P-2 are needed later, not for exit.)
**Risks:** scope creep from P2 ideas; mitigated by PRD §14.

---

## Phase 1 — Foundation
**Status:** NOT STARTED
**Objective:** Runnable, tested, empty application skeleton with CI.
**Dependencies:** Phase 0.
**Included:** project structure, config, DB connection, Alembic, error envelope, logging, health endpoints, frontend shell with design tokens, CI.
**Excluded:** users, auth, any domain tables.

| Area | Tasks |
|---|---|
| Backend | `backend/` with uv, FastAPI app factory, pydantic-settings config, SQLAlchemy engine/session, domain exception classes + envelope handler (`architecture.md` §12), request-ID + JSON logging + scrub filter, `/healthz`, `/readyz`, security headers middleware for dev |
| Frontend | Vite + React + TS strict, Tailwind with tokens from `Design.md` §3, shadcn/ui init, fonts via @fontsource, React Router with `AuthShell` placeholder route only, `apiClient` with envelope parsing, light/dark theme switch |
| Database | `docker-compose.yml` with Postgres 16 + Mailpit; Alembic initialized; first migration enabling `citext` (`gen_random_uuid()` is built into PostgreSQL 13+) |
| Tooling | ruff, pytest, Vitest, Playwright, ESLint; `.gitignore`, `.env.example`; GitHub Actions: backend lint+test with Postgres service, frontend typecheck+lint+test+build, Alembic up/down/check |
| Security | Settings refuse insecure production config; no secrets in repo |
| Testing | Tests for error envelope, request ID, readiness failure when DB down; token contrast check script for `Design.md` tokens |
| Docs | Update `memory.md` with verified layout and commands |

**Deliverables:** skeleton repo; green CI.
**Definition of done:** `docker compose up -d db`, `alembic upgrade head`, `uvicorn` and `npm run dev` work from a clean clone following README; CI green; `/readyz` returns 200.
**Exit criteria:** above verified in a session and recorded in `memory.md`.
**Risks:** Windows-specific tooling issues (owner develops on Windows) — document commands for PowerShell and bash.

---

## Phase 2 — Identity and platform bootstrap
**Status:** NOT STARTED
**Objective:** People can register, verify email, sign in/out, reset passwords; platform admin exists.
**Dependencies:** Phase 1; P-2 for non-local email.
**Included:** AUTH-001…010, ADMIN-005, audit-log infrastructure (ADMIN-006), rate limiting, CSRF incl. Origin checks on unauthenticated routes, sessions.
**Excluded:** colleges, memberships, email change (P1), TOTP (P2).

| Area | Tasks |
|---|---|
| Database | `users`, `sessions`, `user_tokens`, `audit_log` (+ app/maintenance DB roles), `rate_limit_counters` |
| Backend | Argon2id hashing; common-password list check; session create/rotate/expire; CSRF double-submit + Origin check; `current_user`/`current_actor` deps; rate limiter; `EmailSender` (console/SMTP); auth routes; `/me`; CLI `create-platform-admin`; Jobs CLI skeleton with session/token purge |
| Frontend | Sign-in, register, verify-email result, forgot/reset password, change password, sign-out; session-expiry handling (401 → sign-in with return URL) |
| Security | Generic login errors; reset request indistinguishable; sessions revoked on reset/suspension; tokens hashed |
| Testing | Unit: hashing, token expiry, rate windows. API: every AUTH acceptance criterion in PRD US-01; CSRF missing → 403; cross-origin login → 403; suspended user → cannot log in; per-email limit applies to non-existent emails. E2E: register → verify (Mailpit) → sign in |
| Docs | ADR updates if hashing params or session details change; `memory.md` |

**Definition of done:** US-01 criteria pass in automated tests; manual check of email flow via Mailpit.
**Risks:** email deliverability (verification emails in spam) — pick provider with SPF/DKIM (P-2).

---

## Phase 3 — Colleges, membership, departments, roles, tenant isolation
**Status:** NOT STARTED
**Objective:** A college can be onboarded and populated with verified members holding correct roles, with isolation proven by tests.
**Dependencies:** Phase 2.
**Included:** ADMIN-001…004, 007, 008; MEMBER-001…011; DEPT-001/002; TENANT-001…005; AUTH-013 (privileged sessions need roles, so they land here).
**Excluded:** notices, academic data, notifications (Phase 4 adds membership notifications).

| Area | Tasks |
|---|---|
| Database | `colleges` (incl. `is_demo`), `departments`, `roster_entries`, `college_memberships` (incl. `verification_flag`), `role_grants`, `invites`; composite `(college_id, id)` uniques and FKs; partial unique indexes per `architecture.md` §8.2 |
| Backend | `campus_context` dependency; policies module `membership.py`, `admin.py`; scoped repository base helpers requiring `college_id`; platform college CRUD and admin invites; roster CSV import (all-or-nothing); membership request flow (auto-activate / uniform pending response with verification flags); approval queue; admin-only member directory; faculty/staff invites; member management, grants (last-admin rule for revoke/end/suspend); platform-admin accounts blocked from memberships and invites (P-7); privileged-session check in `current_actor` (AUTH-013); college audit log endpoint |
| Frontend | College picker + roll number form; pending/rejected states; Manage → Members (queue, directory, invite, grants), Manage → Departments, Manage → Roster import with row-error table; Platform → Colleges |
| Security | No client `college_id` on campus routes; 404 cross-tenant; platform routes isolated |
| Testing | **Tenant isolation suite** and **route inventory test** created here and extended every later phase; US-02, US-03 (except notification), US-11 |
| Docs | `memory.md`; architecture §11.1 corrections if routes differ |

**Definition of done:** two seeded colleges; isolation suite covers all Phase 3 routes; all criteria green, including US-14 and US-17.
**Exit criteria:** a demo run: platform admin creates "Northfield Institute", invites admin, admin imports roster, student self-verifies.
**Risks:** roster format varies by college — keep CSV template documented and strict.

---

## Phase 4 — Notices, department pages, in-app notifications → **Release α**
**Status:** NOT STARTED
**Objective:** Official communication works end to end; first staging release.
**Dependencies:** Phase 3; P-1 decided for staging.
**Included:** NOTICE-001…007, DEPT-003/004, NOTIF-001…005, membership-decision notifications.
**Excluded:** scheduled publishing (NOTICE-011), audience by kind (NOTICE-012), attachments, read receipts (P1), email notifications.

| Area | Tasks |
|---|---|
| Database | `notices`, `notifications` |
| Backend | Notice policies (scope × role); visibility predicate shared by list/detail; draft/publish/edit/withdraw; notification service (same-transaction inserts, fan-out for HIGH/URGENT at publish); Jobs CLI: notification purge |
| Frontend | Notices list (urgent pinned, filters, past notices), notice detail, notice editor with preview, department page, notifications panel + unread badge with polling |
| Deploy | Staging environment per `architecture.md` §18 (Caddy + API + jobs + managed Postgres) with synthetic seed |
| Security | Markdown sanitization; scope leakage tests (department notices and drafts, list and direct GET) |
| Testing | US-04, US-12, US-15; notification count correctness; E2E J2 |

**Definition of done:** US-04, US-12, US-15 green; Release α deployed to staging and smoke-tested.
**Risks:** fan-out size for large colleges — measure insert time with 20k synthetic members.

---

## Phase 5 — Campus issues
**Status:** NOT STARTED
**Objective:** Issue reporting and handling workflow with full audit trail.
**Dependencies:** Phase 4 (notifications).
**Included:** ISSUE-001…009.
**Excluded:** photos (P1), "me too" (P2).

| Area | Tasks |
|---|---|
| Database | `campus_issues`, `issue_updates` |
| Backend | Pure state machine (`services/issues/state_machine.py`) implementing PRD §9.8.1; policies `can_read_issue`, `can_transition_issue`, `can_comment_issue`; assignment with `/campus/assignees` picker; duplicate marking with status-only projection; reporter reopen limit; internal updates; idempotent creation; rate limit; notifications to reporter/assignee |
| Frontend | Submit form, My issues, Issue detail with timeline, Coordinator queue with filters, Assigned to me |
| Testing | Exhaustive transition table tests (every from × to × role); US-08, US-09; isolation suite additions; E2E J5, J9 |

**Definition of done:** all transitions tested; internal updates and canonical-issue details never returned to the duplicate's reporter (asserted).

---

## Phase 6 — Community → **Release β**
**Status:** NOT STARTED
**Objective:** Moderated text community at college and department level.
**Dependencies:** Phase 4.
**Included:** COMMUNITY-001…010.
**Excluded:** images (P1), auto-hide (P1), cross-college network (P2).

| Area | Tasks |
|---|---|
| Database | `posts`, `comments`, `reactions`, `content_reports` |
| Backend | Feed queries with cursor pagination and shared visibility predicate; post/comment CRUD with soft delete; reaction toggle; reports; moderation queue and actions; rate limits; query-count tests |
| Frontend | College feed, department feed, composer with visibility selector and audience badge, post detail with comments, report dialog, moderation queue |
| Testing | US-10; dept-visibility leakage tests on feed and detail; N+1 guard; E2E post → comment → report → hide |

**Definition of done:** US-10 green; Release β on staging; internal pilot feedback collected in `memory.md`.

---

## Phase 7 — Academic Hub
**Status:** NOT STARTED
**Objective:** Authorized entry and viewing of timetable, attendance, and results.
**Dependencies:** Phase 3 (roles), Phase 4 (notifications).
**Included:** ACADEMIC-001…010.
**Excluded:** marks CSV, shortage warnings, read audits (P1); ERP integration (P2).

| Area | Tasks |
|---|---|
| Database | `academic_terms`, `subjects`, `class_sections`, `section_instructors`, `enrollments`, `timetable_entries` (overlap exclusion constraint, needs `btree_gist`), `attendance_sessions`, `attendance_records`, `assessments`, `assessment_results` |
| Backend | Academic policies per PRD §11 matrix; read-only section views for faculty/dept admin/college admin; edit-window pure function using college setting; optimistic concurrency; enrollment CSV import; attendance summary aggregate query; publish + revise flow with audit (before/after) and notifications |
| Frontend | Student: Academics (Timetable, Attendance, Results). Faculty: Teaching → sections, attendance grid, assessment score entry, publish dialog. Dept admin: subjects/sections/timetable/enrollment management |
| Security | No academic values in logs/notifications; every route in isolation suite; faculty-not-assigned → 404 |
| Testing | US-05, US-06, US-07; policy matrix tests for every role; concurrency test for attendance edits; E2E J3, J4, J6, J7 with synthetic "Demo data" |

**Definition of done:** US-05, US-06, US-07, US-13 green; all academic routes covered by allow/cross-college/wrong-role tests; access matrix tests green.
**Risks:** highest-sensitivity data — require a second review of policies before marking done.

---

## Phase 8 — Home screens, profile and cross-module integration
**Status:** NOT STARTED
**Objective:** Each role lands on a useful home; flows connect.
**Dependencies:** Phases 4–7.
**Included:** HOME-001…004, PROFILE-001.
**Excluded:** new data types; analytics charts.

| Area | Tasks |
|---|---|
| Backend | Aggregate `/campus/home` endpoint composed from existing services (no duplicated policy logic) |
| Frontend | Home per role; profile/settings; navigation finalized per `Design.md` §4 |
| Testing | Home endpoint isolation + role tests; E2E landing per role |

**Definition of done:** US-16 green; every home block shows real data or an honest empty state; no dead links.

---

## Phase 9 — Hardening: security, accessibility, responsiveness, performance
**Status:** NOT STARTED
**Objective:** Meet NFRs and release criteria evidence.
**Dependencies:** Phase 8.

| Area | Tasks |
|---|---|
| Security | Full `Rules.md` §2 checklist audit; dependency audit; CSP verification; session/cookie flags verified on staging; rate-limit tests; re-evaluate RLS (ADR-10) and record decision |
| Accessibility | axe in all E2E; manual keyboard and NVDA pass on J1–J5; contrast verification both themes |
| Performance | Seed 20k members / 100k posts synthetic; load test p95 < 300 ms (NFR-PERF-001); bundle budget check |
| Responsive | Screenshots at 360, 390, 768, 1280 px for every screen; fix issues |
| Testing | Coverage thresholds (NFR-MAINT-001) enforced in CI |

**Definition of done:** findings fixed or explicitly accepted by owner in `memory.md`.

---

## Phase 10 — Deployment and MVP release
**Status:** NOT STARTED
**Objective:** Production MVP at a pilot college.
**Dependencies:** Phase 9; P-3 data agreement signed.

Tasks: production environment; HTTPS/HSTS; backups configured and restore rehearsed; runbook (deploy, rollback, restore, incident contact); seed pilot college via platform CLI/UI; user guide pages for students, faculty, admins; release checklist from PRD §23 completed with evidence.

**Definition of done:** PRD §23 all checked with evidence links in `memory.md`.

---

## Phase 11 — Post-MVP (P1)
**Status:** NOT STARTED
Candidate order (validate with pilot feedback first): events + RSVP (EVENT-001/002) → scheduled notices (NOTICE-011) and audience by kind (NOTICE-012) → idempotency keys (NFR-REL-002) → issue photos (ISSUE-010) with storage abstraction → notice attachments (NOTICE-008) → marks CSV (ACADEMIC-011) → shortage warnings (ACADEMIC-012) → read receipts (NOTICE-009) → email change (AUTH-011) → urgent email digest (NOTIF-006) → auto-hide (COMMUNITY-012) → read audits (ACADEMIC-013) → section announcements (NOTICE-010) → health page (ADMIN-009).

Each item follows the same per-phase template (dependencies, tasks, tests, done) when started; add its section here before implementation.

## 4. Generic definition of done (all phases)

- [ ] Phase requirements' acceptance criteria automated and passing.
- [ ] Isolation suite and route inventory updated and passing.
- [ ] Lint, type checks, unit, API, E2E for touched journeys pass (executed this session).
- [ ] Migrations reviewed; up/down verified in CI.
- [ ] UI states (loading/empty/error) present; screenshots at mobile/desktop checked.
- [ ] Docs and `memory.md` updated; limitations recorded.
