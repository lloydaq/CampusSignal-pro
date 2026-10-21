# CampusSignal 🏫

### One platform. Multiple colleges. One connected campus experience.

CampusSignal is a multi-college campus platform designed to bring academic information, student communities, department activities, official notices, and campus problem reporting into one unified digital space.

Instead of relying on disconnected websites, messaging groups, and notice boards, CampusSignal aims to provide students and staff with a centralized platform for their college life.

---

## 🎯 Vision

Build a connected campus ecosystem where students, faculty, and college administrators can access the information and tools they need in one place.

CampusSignal is designed to support multiple colleges while ensuring that each college's information and communities remain appropriately isolated.

## ✨ Planned Features

### 📚 Academic Management

* Student attendance tracking
* Examination marks and academic records
* Timetable access
* Role-based academic information access

### 👥 Student Community

* College-specific student communities
* Student posts and discussions
* Opportunities to connect with fellow students

### 🏢 Department Communities

* Department-specific announcements
* Event updates and activities
* Dedicated spaces for departmental communication

### 📢 News & Notices

* Official college announcements
* Department notices
* Centralized access to important updates

### 🛠️ Campus Issue Reporting

* Report campus problems
* Track reported issues
* Improve communication between students and college administrators

### 🏫 Multi-College Architecture

* Support for multiple colleges
* College-specific access and communities
* Role-based permissions
* Tenant isolation to protect college data

> **Note:** These are planned capabilities. Application implementation has not started yet.

---

## 🔐 Security First

Security is a core architectural requirement, not an afterthought.

CampusSignal's design emphasizes:

* Server-side session management
* Role-based authorization
* College-scoped data access
* Protection against cross-college data exposure
* Request validation and security controls
* Secure handling of sensitive information

Real student or college data will not be introduced until the pilot college and applicable data agreement have been established.

---

## 🗺️ Development Roadmap

CampusSignal follows a phased development plan.

| Phase          | Focus                                                                       |
| -------------- | --------------------------------------------------------------------------- |
| Phase 0        | Planning, requirements, architecture, and project setup                     |
| Phase 1        | Foundation: backend, database, frontend shell, CI                           |
| Phase 2        | Identity: registration, email verification, sessions, platform admin        |
| Phase 3 onward | Colleges and tenant isolation, notices, issues, community, Academic Hub ... |

Refer to [`Phases.md`](Phases.md) for the complete roadmap and acceptance criteria.

**Current status:** Phase 1 (Foundation) is in progress. The backend and database are done; the frontend shell, CI and this setup guide are awaiting review. Accounts don't exist yet — the app's start page says so and shows live service status.

---

## 📖 Project Documentation

The project is being developed with documentation-driven planning.

| Document                             | Description                                                              |
| ------------------------------------ | ------------------------------------------------------------------------ |
| [`PRD.md`](PRD.md)                   | Product requirements, user stories, and MVP scope                        |
| [`architecture.md`](architecture.md) | Technical architecture, data model, security, and architecture decisions |
| [`Rules.md`](Rules.md)               | Engineering standards and security requirements                          |
| [`Phases.md`](Phases.md)             | Development roadmap and definitions of done                              |
| [`Design.md`](Design.md)             | Design system, screens, navigation, and components                       |
| [`CLAUDE.md`](CLAUDE.md)             | Project instructions for AI-assisted development                         |
| [`memory.md`](memory.md)             | Current project state and next steps                                     |

---

## 🚧 Project Status

* [x] Product requirements, architecture, security and design documented
* [x] Backend foundation (FastAPI, settings, error envelope, logging, `/healthz`)
* [x] Database (PostgreSQL 17, SQLAlchemy, Alembic migrations, `/readyz`)
* [x] Backend CI with integration tests on a disposable PostgreSQL 17
* [ ] Frontend shell, frontend CI and setup guide (implemented, awaiting review)
* [ ] Authentication (Phase 2)
* [ ] Core features (Phase 3 onward)
* [ ] Deployment (Phase 10)

The checklist is updated only when work is completed and verified.

---

## 🧰 Technology Stack

| Layer    | Choice |
| -------- | ------ |
| Frontend | React 19, TypeScript, Vite, Tailwind CSS 4, shadcn/ui, TanStack Query, React Router |
| Backend  | Python 3.12, FastAPI, SQLAlchemy 2 (sync), Alembic, Pydantic v2, psycopg 3 |
| Database | PostgreSQL 17 — a hosted Supabase project for development; a disposable PostgreSQL 17 in CI |
| Tests    | pytest, Vitest + Testing Library, Playwright + axe |
| CI       | GitHub Actions (`.github/workflows/backend.yml`, `.github/workflows/frontend.yml`) |

Details and the reasons behind each choice are in [`architecture.md`](architecture.md). Docker is not needed.

---

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

Open **http://localhost:5173**. The start page shows the live API and database status. The Vite dev server forwards `/api`, `/healthz` and `/readyz` to the backend on port 8000.

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

---

## 🧪 Testing

Backend, from `backend/`:

```bash
uv run pytest -q                                  # unit tests; 6 integration tests skip locally
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

The six database integration tests **downgrade migrations and create roles**, so they only run against a throwaway PostgreSQL 17 and refuse anything else: the host must be `localhost`, the database name must end in `_test`, and Supabase hosts are always rejected. GitHub Actions runs them on every push and pull request. To run them yourself against a local disposable PostgreSQL 17:

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
| The start page says the API is unreachable | The backend isn't running on port 8000. Start it (terminal 1) and click **Check again**. |
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
