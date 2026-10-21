# CampusSignal — Engineering Rules

These rules apply to every change, whether written by a person or an AI coding assistant.

- **MUST / MUST NOT** — mandatory. A change violating one is not done.
- **SHOULD / SHOULD NOT** — recommended. Deviate only with a stated reason in the PR or completion report.

Sources: requirements in `PRD.md`, structure in `architecture.md`, sequence in `Phases.md`, UI in `Design.md`, current state in `memory.md`. The project `CLAUDE.md` security rules are consistent with and included in §2.

---

## 1. Repository and implementation

| ID | Rule |
|---|---|
| R-1.1 | MUST read the relevant files and existing patterns before editing. MUST NOT assume a file's contents. |
| R-1.2 | MUST follow established conventions (naming, layering, folder layout in `architecture.md` §5) unless an ADR in `architecture.md` §23 changes them. |
| R-1.3 | MUST keep changes scoped to the requested phase/task. MUST NOT rewrite, reformat, or "clean up" unrelated files. |
| R-1.4 | MUST NOT replace a working implementation only to make it look cleaner. |
| R-1.5 | MUST keep each business rule in one place (service or policy). MUST NOT duplicate permission or validation logic across routers/components. |
| R-1.6 | MUST respect layers: routers (HTTP only) → services (logic, transactions) → repositories (queries) ; policies (authorization) ; schemas (I/O shapes). Frontend: features call the API client; components don't call `fetch` directly. |
| R-1.7 | MUST use explicit types: Python type hints on all functions (a static type checker is chosen in Phase 1 and then enforced in CI), TypeScript `strict`, no `any` without a comment explaining why. |
| R-1.8 | MUST NOT leave placeholder implementations (`TODO: implement`, `pass`, mocked returns) in production code paths. Unfinished features are not routed or are behind no UI. |
| R-1.9 | SHOULD create folders/modules only when a phase needs them. |
| R-1.10 | SHOULD keep functions under ~50 lines and modules focused on one concern. |
| R-1.11 | MUST use the terminology of `PRD.md` (college, membership, notice, post, campus issue, role grant). MUST NOT introduce synonyms (e.g., "institution", "tenant_id") in new code. |

## 2. Security

| ID | Rule |
|---|---|
| R-2.1 | MUST enforce authorization on the server for every protected endpoint by calling a function in `app/policies/`. MUST NOT write inline ad-hoc permission checks in routers. |
| R-2.2 | MUST derive the college from the session user's ACTIVE membership (`campus_context`). MUST NOT accept `college_id`, role, membership, author, or status from request bodies, query strings, or headers on campus endpoints. |
| R-2.3 | MUST load the object with a `college_id`-scoped query, then authorize it. Knowing an ID grants nothing. |
| R-2.4 | MUST return 404 (identical body to not-found) for objects in another college or not readable by the actor. 403 only when the actor can read the object but not perform the action. |
| R-2.5 | MUST apply the same visibility predicate in list, search, feed, and count queries as in single-object reads. |
| R-2.6 | MUST NOT treat frontend hiding as security. |
| R-2.7 | MUST validate all untrusted input with Pydantic schemas using `extra="forbid"` and explicit length/range limits. Response schemas MUST whitelist fields (never return ORM objects directly). |
| R-2.8 | MUST use SQLAlchemy bound parameters. MUST NOT build SQL with string formatting. |
| R-2.9 | MUST hash passwords with Argon2id; MUST store session/verification/reset/invite tokens only as SHA-256 hashes. |
| R-2.10 | MUST keep auth in server-side sessions with `HttpOnly; Secure; SameSite=Lax` cookies and CSRF tokens on unsafe methods. MUST NOT store tokens in `localStorage`/`sessionStorage`. |
| R-2.11 | MUST NOT log or include in error messages/notifications: passwords, cookies, session/CSRF/reset/invite tokens, scores, attendance values, roll numbers, emails. |
| R-2.12 | MUST apply rate limits listed in `PRD.md` to their operations; new sensitive operations (auth, creation of user content, invitations) MUST get a limit. |
| R-2.13 | MUST write an audit log entry for every action listed in ADMIN-006 inside the same transaction as the action. |
| R-2.14 | MUST validate uploads (when introduced in Phase 11): size limit, magic-byte type check, re-encode images, random storage keys, authorized download. |
| R-2.15 | MUST NOT bypass, weaken, or mock authorization to make a test pass. |
| R-2.16 | MUST NOT add platform-admin access to college content, notices, issues, or academic tables (ADMIN-008) without a PRD change. |
| R-2.17 | MUST NOT commit secrets. Configuration comes from environment variables; `.env.example` lists every variable without real values. |
| R-2.18 | MUST render user content safely: plain text for posts/comments; sanitized Markdown subset for notices; no `dangerouslySetInnerHTML` except through the sanitizing renderer. |
| R-2.19 | Academic data in development, demos, screenshots, and tests MUST be synthetic and labelled "Demo data". MUST NOT scrape or connect to college ERPs. |
| R-2.20 | MUST derive client IP only from the trusted reverse proxy; MUST NOT trust client-supplied forwarding headers. |
| R-2.21 | MUST NOT add endpoints that let non-admins enumerate members, roster entries, or roll numbers; responses to verification attempts MUST be uniform (MEMBER-004). |
| R-2.22 | MUST NOT grant any privilege to Supabase's `anon` or `authenticated` roles. Any function created in a migration MUST `REVOKE EXECUTE ON FUNCTION … FROM PUBLIC`; `SECURITY DEFINER` functions need explicit security review. Migrations MUST run as the role that owns application objects. |

**Security review checklist** (copy into each PR touching endpoints):
- [ ] Policy called for every new route; route inventory test passes.
- [ ] Repository queries include `college_id`.
- [ ] Allow, cross-college deny, wrong-role deny tests exist; deny bodies leak no fields.
- [ ] Lists use the same visibility predicate as detail.
- [ ] No new sensitive data in logs or notifications.
- [ ] Audit entries for sensitive actions.

## 3. Frontend

| ID | Rule |
|---|---|
| R-3.1 | MUST follow `Design.md`: use theme tokens only; MUST NOT use arbitrary Tailwind values (`text-[13px]`, `bg-[#123456]`) or inline color styles. |
| R-3.2 | MUST implement loading, empty, error, and (where relevant) success states for every data view. |
| R-3.3 | MUST give every form field a visible label, client validation mirroring server rules, server error mapping to fields, and a disabled/pending submit state. |
| R-3.4 | MUST use semantic HTML (buttons for actions, links for navigation, headings in order) and keep everything keyboard operable with visible focus. |
| R-3.5 | MUST NOT hardcode secrets, API keys, or environment-specific URLs. |
| R-3.6 | MUST NOT display fabricated data as real (no fake activity, fake stats, lorem ipsum in shipped screens). |
| R-3.7 | MUST NOT ship buttons or links that do nothing; unfinished features are absent, not disabled-forever. |
| R-3.8 | SHOULD extract a reusable component when the same UI appears in ≥ 2 features; SHOULD NOT create abstractions for single use. |
| R-3.9 | SHOULD keep components under ~200 lines; business rules belong in the backend, data fetching in feature hooks. |
| R-3.10 | MUST use shadcn/ui primitives for dialogs, menus, tabs, selects, toasts (accessibility built in) rather than hand-rolled equivalents. |
| R-3.11 | MUST check UI changes at 390 px and 1280 px widths (Playwright screenshots) and in both themes before reporting done. |

## 4. Backend

| ID | Rule |
|---|---|
| R-4.1 | MUST keep request/response schemas (`schemas/`), domain logic (`services/`), and persistence (`repositories/`, `models/`) separate. |
| R-4.2 | MUST return errors only through the envelope and codes in `architecture.md` §12. |
| R-4.3 | MUST wrap multi-step writes in a single transaction; MUST use row locks (`SELECT ... FOR UPDATE`) or optimistic `version` checks for contested updates (attendance, results, issues, capacity). |
| R-4.4 | MUST paginate every collection endpoint with cursors; max page size 50. |
| R-4.5 | MUST avoid N+1 queries on lists (eager loading/joins); feed tests assert query counts. |
| R-4.6 | MUST store instants as `timestamptz` UTC and calendar dates as `date` interpreted in the college timezone; MUST convert for display on the client using the college timezone from `/me`. |
| R-4.7 | MUST back business rules with DB constraints where expressible (uniqueness, checks, composite tenant FKs). |
| R-4.8 | MUST make schema changes only through reviewed Alembic migrations with a working downgrade or a documented reason why not. |
| R-4.9 | MUST keep the issue state machine and attendance edit-window logic as pure functions with unit tests. |
| R-4.10 | SHOULD keep endpoints synchronous (`def`) per ADR-08 unless a measured need arises. |

## 5. Testing

| ID | Rule |
|---|---|
| R-5.1 | MUST add tests for every new behavior. |
| R-5.2 | Every new endpoint MUST ship with: an allow test, a cross-college deny test, and a wrong-role deny test where roles apply. Deny tests MUST assert the response contains no private fields. |
| R-5.3 | New college-scoped endpoints MUST be registered in the tenant isolation suite. |
| R-5.4 | For security-sensitive work, SHOULD write failing tests first. |
| R-5.5 | MUST test edge cases and failures listed in `PRD.md` §16 that the change touches. |
| R-5.6 | MUST NOT delete, skip, or weaken tests to get a green build. A test may change only when the requirement changed, and the commit says so. |
| R-5.7 | MUST run the relevant checks before reporting completion: backend `pytest -q`, `ruff check .`, `ruff format --check .`; frontend `npm run typecheck`, `npm run lint`, `npm test`, `npm run build`; E2E for touched journeys. |
| R-5.8 | MUST report failures honestly with output. MUST NOT claim tests pass unless they were executed in this session. |
| R-5.9 | MUST use factories with at least two fictional colleges ("Northfield Institute", "Riverside College"); no real names or data. |

## 6. Documentation

| ID | Rule |
|---|---|
| R-6.1 | MUST update the relevant document when behavior changes (PRD for scope, architecture for structure/API, Design for UI patterns). |
| R-6.2 | MUST keep endpoint tables in `architecture.md` §11.1 consistent with implemented routes (OpenAPI is the detailed source). |
| R-6.3 | MUST record significant decisions as ADRs in `architecture.md` §23 and summarize in `memory.md`. |
| R-6.4 | MUST update `memory.md` after each completed task/phase: concise, verified facts only. MUST NOT copy whole sections of other documents into it. |
| R-6.5 | MUST mark requirements/phase items complete only after verification (R-8). |

## 7. Dependencies

| ID | Rule |
|---|---|
| R-7.1 | MUST justify every new dependency (what it replaces, why the standard library or an existing dependency is insufficient) in the PR/completion report. |
| R-7.2 | MUST check license and compatibility (Python 3.12, the React major pinned in Phase 1, Node LTS) before adding. |
| R-7.3 | MUST pin via lockfiles (`uv.lock`, `package-lock.json`) and commit them. |
| R-7.4 | MUST NOT commit `.env`, virtual environments, `node_modules`, build output, local databases, coverage output, or uploaded files. `.gitignore` covering them (and local AI-tool settings such as `.claude/settings.local.json`) MUST exist before the first commit. |
| R-7.5 | SHOULD run `npm audit` / `pip-audit` in CI and address high/critical findings. |

## 8. Completion protocol

A task or phase is complete only when **all** are true:

1. Acceptance criteria in `PRD.md` / `Phases.md` for the scope are satisfied.
2. Authorization and tenant boundaries verified by tests (R-5.2, R-5.3) and the security checklist (§2).
3. Relevant checks (R-5.7) were run in this session and pass.
4. Existing tests still pass (no unintended regressions).
5. Documentation updated (R-6.*), including `memory.md`.
6. Known limitations are written down in `memory.md`.

**Completion report format** (end of every task):

```
## Completed
- <what changed, with file paths>
## Verification
- <command> → <result> (actually executed)
## Security review
- <policies added, isolation tests added>
## Limitations / follow-ups
- <...>
## Next recommended task
- <phase + item>
```

## 9. Working with AI coding assistants

| ID | Rule |
|---|---|
| R-9.1 | MUST read `memory.md` first, then the current phase in `Phases.md`, then any doc sections the task touches. |
| R-9.2 | MUST propose a plan and wait for approval for any task larger than a small fix. |
| R-9.3 | MUST NOT silently start work belonging to a later phase. |
| R-9.4 | MUST state assumptions explicitly instead of inventing certainty; ask when a decision is security-, data-, or scope-relevant. |
| R-9.5 | MUST NOT run destructive commands (dropping databases, deleting data, force-pushing) without explicit user approval. |
