<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/readme/hero-dark.svg">
  <img alt="CampusSignal: one platform for many colleges. A preview of the notices list with an urgent pinned notice and an unread notification." src="docs/readme/hero-light.svg" width="100%">
</picture>

<p align="center">
  <a href="#what-it-does"><b>What it does</b></a> ·
  <a href="#security"><b>Security</b></a> ·
  <a href="#architecture"><b>Architecture</b></a> ·
  <a href="#roadmap"><b>Roadmap</b></a> ·
  <a href="#getting-started"><b>Getting started</b></a> ·
  <a href="#docs"><b>Docs</b></a>
</p>

CampusSignal is a multi-college campus platform. It brings official notices, department pages, a moderated student community, academic records and campus problem reporting into one place, so students and staff stop juggling disconnected websites, messaging groups and notice boards.

Every college gets its own private space. People only ever see their own college, and the server enforces that on every request.

---

<a id="what-it-does"></a>

## ✨ What it does

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/readme/features-dark.svg">
  <img alt="Six areas and their status. Built: accounts and sessions; colleges, roles and joining. In progress: notices and notifications. Planned: campus issue reporting, moderated community, Academic Hub." src="docs/readme/features-light.svg" width="100%">
</picture>

| Area | Status | What's there |
| ---- | ------ | ------------ |
| 🔑 Accounts and sessions | ✅ Built | Registration, email verification, sign-in and out, password reset and change, server-side sessions with CSRF protection |
| 🏫 Colleges, roles, joining | ✅ Built | Colleges onboarded by platform admins; students join by roll number against the college roster, staff by invitation; approval queue; college and department admins; the **Manage** and **Platform** screens |
| 📢 Notices and notifications | 🟠 In progress | College and department notices with drafts, urgent pins, expiry and withdrawal; in-app notifications for urgent notices and join decisions. The backend is done; the screens are next |
| 🛠️ Campus issue reporting | Planned | Report a problem, follow its status, coordinators work the queue (Phase 5) |
| 👥 Moderated community | Planned | College and department feeds with reactions, reports and moderation (Phase 6) |
| 📚 Academic Hub | Planned | Timetable, attendance and results, shown only to the right people (Phase 7) |

Academic data in development and demos is synthetic and labelled "Demo data". CampusSignal never connects to college ERPs.

---

<a id="security"></a>

## 🔐 Security first

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/readme/isolation-dark.svg">
  <img alt="How a request is scoped: the session leads to the user's active membership, which fixes the college. Requests reach their own college; anything in another college answers 404, exactly like something that doesn't exist." src="docs/readme/isolation-light.svg" width="100%">
</picture>

Security is a core architectural requirement, not an afterthought:

* **The college is never taken from the client.** Campus routes derive it from the signed-in user's active membership in the database.
* **Another college's data doesn't exist for you.** Reading it answers `404`, the same as something that was never there, so nothing leaks by existence.
* **Every permission decision lives in one place** (`backend/app/policies/`), and lists, counts and single reads use the same rules.
* **The database backs it up:** college-scoped tables carry `college_id` with composite `(college_id, id)` foreign keys, so a row can't point into another college.
* **Sessions stay on the server** in HttpOnly cookies with CSRF tokens; passwords are hashed with Argon2id; faculty and admin sessions expire sooner.
* **Tests prove it:** every campus route is in a tenant-isolation suite, and a route inventory test fails if a new route skips it.

Real student or college data will not be introduced until a pilot college and a data agreement are in place.

---

<a id="architecture"></a>

## 🧭 How it fits together

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/readme/architecture-dark.svg">
  <img alt="Browser to Caddy to the FastAPI backend (routers, policies, services, repositories) to PostgreSQL 17, with a mailer and an hourly jobs CLI." src="docs/readme/architecture-light.svg" width="100%">
</picture>

| Layer    | Choice |
| -------- | ------ |
| Frontend | React 19, TypeScript, Vite, Tailwind CSS 4, shadcn/ui, TanStack Query, React Router |
| Backend  | Python 3.12, FastAPI, SQLAlchemy 2 (sync), Alembic, Pydantic v2, psycopg 3 |
| Database | PostgreSQL 17: a hosted Supabase project for development; a disposable PostgreSQL 17 in CI |
| Tests    | pytest, Vitest + Testing Library, Playwright + axe |
| CI       | GitHub Actions (`.github/workflows/backend.yml`, `.github/workflows/frontend.yml`) |

Details and the reasons behind each choice are in [`architecture.md`](architecture.md). Docker is not needed.

---

<a id="roadmap"></a>

## 🗺️ Roadmap

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/readme/roadmap-dark.svg">
  <img alt="Phases 0 to 3 are done, phase 4 (notices and notifications) is in progress, phases 5 to 11 are next. Release alpha after phase 4, beta after phase 6, MVP after phase 10." src="docs/readme/roadmap-light.svg" width="100%">
</picture>

* [x] **Phase 0–1:** requirements, architecture, design system; backend, database, frontend shell and CI
* [x] **Phase 2:** accounts, email verification, sessions, password reset, platform admins
* [x] **Phase 3:** colleges, departments, roster, joining and approval, roles, tenant isolation, Manage and Platform screens, `seed-demo`
* [ ] **Phase 4:** notices ✅ and notifications ✅ (backend), screens next; staging deployment deferred
* [ ] **Phase 5–11:** campus issues, community, Academic Hub, home screens, hardening, launch

The checklist is updated only when work is completed and verified. [`Phases.md`](Phases.md) has every phase's tasks and definition of done.

---

<a id="docs"></a>

## 📖 Project documentation

The project follows documentation-driven development: these documents are authoritative, and the code follows them.

| Document                             | Description                                                              |
| ------------------------------------ | ------------------------------------------------------------------------ |
| [`PRD.md`](PRD.md)                   | Product requirements, user stories, and MVP scope                        |
| [`architecture.md`](architecture.md) | Technical architecture, data model, security, and architecture decisions |
| [`Rules.md`](Rules.md)               | Engineering standards and security requirements                          |
| [`Phases.md`](Phases.md)             | Development roadmap and definitions of done                              |
| [`Design.md`](Design.md)             | Design system, screens, navigation, and components                       |
| [`CLAUDE.md`](CLAUDE.md)             | Project instructions for AI-assisted development                         |
| [`memory.md`](memory.md)             | Current project state and next steps                                     |

The README pictures are generated from the Design.md colour tokens by [`docs/readme/build_svgs.py`](docs/readme/build_svgs.py) (`python docs/readme/build_svgs.py`). Edit that script, not the SVGs.

---

<a id="getting-started"></a>

## 🚀 Getting Started

Commands are shown for **Windows PowerShell** and **bash** (macOS, Linux, Git Bash) where they differ. Run each block from the repository root unless it says otherwise.

### Prerequisites

| Tool | Version | Notes |
| ---- | ------- | ----- |
| [uv](https://docs.astral.sh/uv/) | 0.13 or later | Installs and pins Python 3.12 for the backend automatically |
| [Node.js](https://nodejs.org/) | 22 or later (CI uses 24) | Includes npm |
| Git | any recent | |
| A Supabase project | free plan is fine | Development database only. Use the **Session pooler** connection string and turn **off** the Data API (Dashboard → Integrations → Data API) |

### 1. Configure the backend

```powershell
# PowerShell
cd backend
Copy-Item .env.example .env
```

```bash
# bash
cd backend
cp .env.example .env
```

Edit `backend/.env` and set:

* `APP_ENV=local` and `APP_ORIGIN=http://localhost:5173` (already in the example).
* `DATABASE_URL` — your Supabase **Session pooler** string, with two changes: the scheme becomes `postgresql+psycopg://`, and `?sslmode=require` goes on the end. URL-encode special characters in the password.

`.env` is git-ignored. Never commit it, paste it into issues, or share it.

### 2. Install dependencies and migrate the database

```bash
# backend/ (same command in PowerShell and bash)
uv sync
uv run alembic upgrade head
```

`alembic upgrade head` only moves the database forward. Never run `alembic downgrade` against Supabase.

```bash
# frontend/ (same command in PowerShell and bash)
cd ../frontend
npm ci
```

### 3. Start the app (two terminals)

```bash
# Terminal 1 — backend/
uv run uvicorn app.main:app --reload
```

```bash
# Terminal 2 — frontend/
npm run dev
```

Open **http://localhost:5173** to reach the sign-in page. **http://localhost:5173/status** shows the live API and database status. The Vite dev server forwards `/api`, `/healthz` and `/readyz` to the backend on port 8000.

Quick checks with the backend running:

```powershell
# PowerShell
Invoke-RestMethod http://127.0.0.1:8000/healthz   # status: ok
Invoke-RestMethod http://127.0.0.1:8000/readyz    # status: ready
```

```bash
# bash
curl http://127.0.0.1:8000/healthz   # {"status":"ok"}
curl http://127.0.0.1:8000/readyz    # {"status":"ready"}
```

API docs (local only): http://127.0.0.1:8000/api/v1/docs

### 4. Operator commands

Run these from `backend/`, on the server or locally. They use the same `.env` settings as the API. The commands are the same in PowerShell and bash.

```bash
# Create a platform-admin account. You're asked for the password twice.
uv run python -m app.cli create-platform-admin --email ops@example.org --display-name "Platform Ops"

# Add two fictional demo colleges (Northfield Institute, Riverside College) with departments,
# a college admin, a department-admin faculty member and a student roster each. You're asked
# for one password, used for all the demo accounts. Only with APP_ENV=local or ci.
uv run python -m app.cli seed-demo

# Run the retention purges. The deployment scheduler runs this every hour.
uv run python -m app.jobs run-due
```

Platform admins can only be created this way, not through the app or the API. The command creates a new, already-verified account. It refuses an email that already has an account: an existing account is never promoted, so platform admins stay separate from college members. The password can't be passed as an argument, which keeps it out of shell history.

`seed-demo` adds only what is missing, so running it again is safe. The demo accounts and roll numbers are listed at the top of `backend/app/services/demo_seed.py`. The students on the rosters have no accounts: to try joining, register with a roster email (for example `nf-cse-002@northfield.example`), verify it, then join Northfield with the roll number `NF-CSE-002`. `NF-CSE-001` has no roster email, so that request waits in the approval queue.

`run-due` deletes:

* expired sessions
* sign-in tokens more than 7 days past their expiry
* rate-limit counters older than 1 day
* audit-log entries older than 2 years
* notifications older than 90 days

It writes one JSON log line per purge with the number of rows deleted. It exits with code 1 if any purge failed. Running it again is safe.

---

## 🧪 Testing

Backend, from `backend/`:

```bash
uv run pytest -q                                  # unit tests; integration tests skip without TEST_DATABASE_URL
uv run ruff check . ; uv run ruff format --check . ; uv run mypy
```

Frontend, from `frontend/`:

```bash
npm test             # Vitest: components, API client, theme, WCAG token contrast
npm run lint
npm run typecheck
npm run build
```

Browser smoke tests (Playwright + axe), from `frontend/`. The first run needs the Chromium build:

```bash
npx playwright install chromium
npm run e2e
```

The browser tests build the app, serve it on port 4173 and mock every backend call, so they don't need the backend or a database. They run at 1280 px and 390 px (touch) and fail on any WCAG A/AA violation that axe finds.

### Integration tests

The database integration tests **downgrade migrations and create roles**, so they only run against a throwaway PostgreSQL 17 and refuse anything else: the host must be `localhost`, the database name must end in `_test`, and Supabase hosts are always rejected. GitHub Actions runs them on every push and pull request. To run them yourself against a local disposable PostgreSQL 17:

```powershell
# PowerShell, backend/
$env:TEST_DATABASE_URL = "postgresql+psycopg://postgres:postgres@localhost:5432/campussignal_test"
uv run pytest -m integration -rs
Remove-Item Env:TEST_DATABASE_URL
```

```bash
# bash, backend/
TEST_DATABASE_URL="postgresql+psycopg://postgres:postgres@localhost:5432/campussignal_test" uv run pytest -m integration -rs
```

**Never point `TEST_DATABASE_URL` at Supabase.**

### Full-stack E2E (real API, database and email)

These tests run against the real backend: the account journeys (register, open the verification link from the email, sign in and out, reset a password) and the Phase 3 exit demo (a platform admin creates a college and invites its admin, the admin accepts, adds a department and imports the roster, and a student registers with a roster email and joins by roll number).

* Emails are caught by [Mailpit](https://mailpit.axllent.org/), and the test reads them through Mailpit's API.
* The run writes accounts to the database. Use a **separate** disposable database whose name ends in `_test`, on `localhost`; the config refuses anything else.
* Each run registers six accounts from one address. The API allows 10 registrations per address per hour, so run it once an hour locally, or empty the `rate_limit_counters` table of the test database between runs.
* GitHub Actions runs it on every push and pull request, using Postgres and Mailpit service containers.

To run it yourself, start Mailpit (the standalone binary, no Docker needed) and create an empty database such as `campussignal_e2e_test`. Then, from `frontend/`:

```powershell
# PowerShell, frontend/  (Mailpit running: mailpit --smtp 127.0.0.1:1025 --listen 127.0.0.1:8025)
$env:E2E_DATABASE_URL = "postgresql+psycopg://postgres:postgres@localhost:5432/campussignal_e2e_test"
npm run e2e:fullstack
Remove-Item Env:E2E_DATABASE_URL
```

```bash
# bash, frontend/  (Mailpit running: mailpit --smtp 127.0.0.1:1025 --listen 127.0.0.1:8025)
E2E_DATABASE_URL="postgresql+psycopg://postgres:postgres@localhost:5432/campussignal_e2e_test" npm run e2e:fullstack
```

The run migrates that database, then starts uvicorn on port 8000 and `vite preview` on port 4174, which forwards `/api` to the API. Stop any backend already using port 8000 first. Mailpit's inbox is at http://127.0.0.1:8025.

---

## 🛠️ Troubleshooting

| Symptom | Cause and fix |
| ------- | ------------- |
| Backend exits with `validation error for Settings` | A required setting is missing or invalid. Check `backend/.env` has `APP_ENV`, `APP_ORIGIN` and `DATABASE_URL`; the URL must start with `postgresql+psycopg://` and end with `sslmode=require`. The error names the setting but never prints its value. |
| `Error loading ASGI app. Attribute "app" not found` | Run uvicorn from `backend/` with `app.main:app` (or `app.main:app_factory --factory`). |
| `[Errno 10048]` / `address already in use` on port 8000 | Another backend is already running. Stop it, or find it: PowerShell `Get-NetTCPConnection -LocalPort 8000`, bash `lsof -i :8000`. The frontend proxy expects port 8000. |
| `/readyz` returns 503 with `"database": "unreachable"` | The database can't be reached. Free Supabase projects **pause after a week of inactivity** — restore it from the Supabase dashboard. Also check your network and the `DATABASE_URL` host. |
| `/readyz` returns 503 with `"migrations": "pending"` | Run `uv run alembic upgrade head` in `backend/`. |
| The page loads at `http://127.0.0.1:5173` but not, or vice versa | Vite listens on `localhost`, which can resolve to IPv6 only. Use **http://localhost:5173**. |
| The status page (`/status`) says the API is unreachable | The backend isn't running on port 8000. Start it (terminal 1) and click **Check again**. |
| PowerShell: `npm.ps1 cannot be loaded because running scripts is disabled` | Use `npm.cmd` instead of `npm`, or allow scripts for your user: `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`. |
| Windows: `npm ci` fails with `EPERM: operation not permitted, unlink ... .node` | A running Vite dev or preview server has the native module open. Stop `npm run dev` / `npm run e2e`, then rerun `npm ci`. If it was interrupted, `npm install` restores `node_modules`. |
| `npm run e2e`: `Executable doesn't exist` | Install the browser once: `npx playwright install chromium`. |
| `npm run e2e`: port 4173 already in use | Stop the other `vite preview`, or let Playwright reuse it (it does locally). |
| Integration tests show `SKIPPED` | Expected locally without `TEST_DATABASE_URL`. They run in CI. |
| `uv` can't find Python 3.12 | `uv sync` downloads it automatically; check your network, or run `uv python install 3.12`. |

---

## 🤝 Development Principles

CampusSignal follows these principles:

1. **Security by design** — permissions and data isolation must be enforced server-side.
2. **Documentation-driven development** — implementation should follow the documented requirements.
3. **Incremental delivery** — each phase must satisfy its definition of done.
4. **Testable changes** — claims of successful testing must be backed by tests that actually ran.
5. **Privacy-conscious design** — minimize unnecessary exposure of personal and academic information.

---

## 📄 License

No license has been specified yet. Until a license is added, all rights are reserved.
