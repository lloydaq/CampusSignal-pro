# CampusSignal — Product Requirements Document

| | |
|---|---|
| Status | v0.2 — owner decisions P-4, P-7, P-8, P-9 applied (2026-10-20); remaining open decisions in §21 |
| Last updated | 2026-10-20 |
| Related | `architecture.md` (how), `Rules.md` (engineering rules), `Phases.md` (delivery order), `Design.md` (UI/UX), `memory.md` (current state) |

Labels used in this document:
- **[Decision]** — confirmed for planning purposes.
- **[Assumption]** — believed true, must be validated with at least one real college before Phase 10 release.
- **[Pending]** — not decided; listed in §21 and `memory.md`.

Each P0 requirement row is itself a testable acceptance criterion; §15 adds scenario-level criteria. The "Phase" column must match `Phases.md` §3 — if they disagree, fix both in the same change.

---

## 1. Product overview

CampusSignal is a multi-college web platform. Each participating college gets an isolated **college space** (a tenant) containing official notices, a student community, departmental pages, private academic information (timetable, attendance, results), and a campus issue reporting workflow. A small set of explicitly public content (college profile, later: public events) is visible across colleges.

## 2. Problem statement

Students in a typical college receive information through disconnected channels: notice boards, messaging groups, ERP portals that are often unusable on phones, and word of mouth. Specifically:

1. **Official notices get lost** among unofficial chat messages; students cannot tell which information is authoritative or current.
2. **Academic information is hard to reach** — attendance shortages are often discovered too late to act on.
3. **Campus problems go unreported or untracked** — a broken projector or a leaking tap is reported verbally, with no record and no feedback to the reporter.
4. **Student discussion lives in unmoderated groups** outside any college accountability, mixing official and unofficial content.
5. **Small colleges cannot afford custom systems**, and per-college tools do not share improvements.

## 3. Product vision

One trustworthy place where a student can see what their college officially said, where they stand academically, what is happening in their department, and whether the problem they reported is being fixed — with the guarantee that their college's private information never leaks to anyone outside it.

## 4. Goals and non-goals

### Goals (MVP)
- G1. A verified student can see their college's current official notices within two taps of signing in.
- G2. A student can see their own attendance per subject and their published results, entered by their assigned faculty.
- G3. A student can report a campus issue and see its status change until resolution.
- G4. Students can hold moderated text discussions scoped to their college or department.
- G5. Zero cross-college data exposure: no endpoint returns another college's private data, verified by automated tests.
- G6. A new college can be onboarded by a platform administrator without code changes.

### Non-goals (MVP)
- Replacing a college ERP, fee systems, admissions, or learning management systems.
- Integrations with university/ERP systems (manual entry and CSV import only).
- Real-time chat or direct messaging.
- Native mobile apps (responsive web only).
- AI/ML features of any kind.
- Payments or event ticketing.
- Cross-college community feeds (see §24, P2).

## 5. Target users and personas

| Persona | Description | Primary need |
|---|---|---|
| **Aarav — 2nd-year student** | Uses phone for everything, moderate data plan | Know about deadlines and attendance before it's too late |
| **Dr. Meera — assistant professor** | Teaches 3 sections, limited time | Record attendance and marks quickly; no duplicate data entry |
| **Prof. Rao — head of department (department admin)** | Responsible for department notices and timetable | Publish to department only, fix data errors with accountability |
| **Ms. Fernandes — college office administrator (college admin)** | Manages college-wide notices and student verification | Verify students without an ERP integration, control who has what role |
| **Ravi — maintenance supervisor (staff, issue coordinator)** | Handles infrastructure complaints | A clear queue of issues by location and priority |
| **Platform admin** | Operates CampusSignal itself | Onboard colleges, handle escalations, without access to academic records |

## 6. User pain points

| Pain point | Persona | Addressed by |
|---|---|---|
| Can't distinguish official from unofficial information | Student | Notices (visually and structurally separate from posts) |
| Attendance shortage discovered at semester end | Student | Attendance view with per-subject percentage |
| Paper attendance registers retyped later | Faculty | Attendance entry grid per class session |
| Complaints vanish with no feedback | Student, Staff | Campus issues with status tracking and audit |
| Anyone can claim to be a student | College admin | Roster-backed membership verification |
| Department notices spam the whole college | Dept admin | Audience-scoped notices |

## 7. Product principles

1. **Official is visually and structurally different from social.** Notices are never posts.
2. **Private by default, public by explicit choice.** Every object belongs to exactly one college unless explicitly marked public.
3. **Least privilege.** Roles grant the minimum; platform admins do not read college academic data.
4. **Every change to sensitive data is attributable** (who, when, why).
5. **Honest UI.** No fake data, no buttons that do nothing, empty states say what's actually true.
6. **Works without integrations.** Manual entry and CSV import are first-class.
7. **Ship small, usable slices.** Each release is usable on its own.

## 8. Core user journeys

| ID | Journey | Steps |
|---|---|---|
| J1 | Student joins | Register → verify email → choose college → enter roll number → auto-activated (roster email match) or queued for approval → sees college home |
| J2 | Read notices | Home → "Notices" list (urgent pinned) → notice detail |
| J3 | Check attendance | Academics → Attendance → per-subject percentage → session-level detail |
| J4 | Check results | Academics → Results → published assessments per subject |
| J5 | Report issue | Issues → New → category, location, description → submit → track status, receive notifications |
| J6 | Faculty takes attendance | Teaching → section → "Take attendance" → mark grid (default present) → save |
| J7 | Faculty publishes marks | Teaching → section → assessment → enter scores → publish → students notified |
| J8 | Admin verifies students | Manage → Members → pending queue → approve/reject with reason |
| J9 | Coordinator handles issue | Issues queue → acknowledge → assign → in progress → resolve with note |
| J10 | Platform onboards college | Platform → Colleges → create → invite first college admin |

## 9. Functional requirements

Priority: **P0** = required for a secure, usable MVP; **P1** = important, not required for first release; **P2** = future.
Phase column maps to `Phases.md`.

### 9.1 Authentication and identity (AUTH)

| ID | Requirement | Pri | Phase |
|---|---|---|---|
| AUTH-001 | A person can register with email, password, and display name. Email is stored case-insensitively and must be unique. | P0 | 2 |
| AUTH-002 | Passwords: min 10 chars, max 128, checked against a bundled list of common passwords; hashed with Argon2id. Plaintext never stored or logged. | P0 | 2 |
| AUTH-003 | Email verification: a single-use token (≥256 bits entropy, stored hashed) valid for 24 h is emailed on registration. Unverified accounts can sign in but cannot request college membership. Resend limited to 3/hour. | P0 | 2 |
| AUTH-004 | Sign-in creates a server-side session referenced by an opaque random ID in an `HttpOnly; Secure; SameSite=Lax` cookie. Standard sessions: idle timeout 7 days, absolute lifetime 30 days; privileged sessions are shorter (AUTH-013). Session ID rotates on sign-in and password change. Membership, role, and status are loaded on every request (never cached in the session), so changes take effect on the next request. | P0 | 2 |
| AUTH-005 | Sign-out deletes the server-side session. "Sign out of all devices" deletes all sessions of the user. | P0 | 2 |
| AUTH-006 | Password reset via emailed single-use token valid for 60 minutes; completing a reset revokes all existing sessions. Request endpoint responds identically whether or not the email exists. | P0 | 2 |
| AUTH-007 | Sign-in failures return one generic message. Rate limits: 5 failed attempts per normalized email per 15 min (keyed on the submitted email whether or not an account exists, so lockout does not reveal existence), 20 per client IP per 15 min; exceeding returns 429. Client IP is taken only from the trusted reverse proxy's header. | P0 | 2 |
| AUTH-008 | All state-changing requests, including unauthenticated ones (`/auth/login`, `/auth/register`, reset), require an allowed `Origin`. Requests with a session additionally require a valid CSRF token (double-submit). Prevents login CSRF and cross-site writes. | P0 | 2 |
| AUTH-009 | Account status `ACTIVE`, `SUSPENDED`, `DEACTIVATED`. Suspended/deactivated users cannot sign in; suspension revokes all sessions immediately. In the MVP only platform admins set these statuses (ADMIN-004); self-service deletion is P1. | P0 | 2 |
| AUTH-010 | User can change password (requires current password; revokes other sessions). | P0 | 2 |
| AUTH-011 | User can change email (re-verification required before the change takes effect). | P1 | 11 |
| AUTH-012 | Optional TOTP two-factor authentication for admin roles. | P2 | — |
| AUTH-013 | [Decision, P-8] **Privileged sessions**: a session whose user currently has an ACTIVE membership of kind FACULTY, or a COLLEGE_ADMIN or DEPARTMENT_ADMIN grant (roles with access to other students' academic records), has an idle timeout of 24 hours and an absolute lifetime of 7 days from sign-in. The tier is evaluated on every request from current roles, so gaining such a role applies the shorter limits immediately (an older session may end at once). Platform-admin accounts always use these privileged limits (P-10, decided 2026-10-21). Students, staff without these grants, and issue coordinators keep standard limits. Defaults are configurable and subject to the Phase 9 security review. | P0 | 3 |

### 9.2 College membership and verification (MEMBER)

[Decision] College email verification alone does **not** prove enrollment. Membership is proven against a **roster** the college supplies, or by **invitation** from a college admin.

| ID | Requirement | Pri | Phase |
|---|---|---|---|
| MEMBER-001 | A college admin can import a student roster CSV (roll number, full name, department code, program, admission year, optional institutional email). Import validates every row and reports row-level errors without partial import (all-or-nothing). | P0 | 3 |
| MEMBER-002 | A verified user without the PLATFORM_ADMIN role (P-7) can request student membership of an ACTIVE college by entering their roll number. | P0 | 3 |
| MEMBER-003 | If the roll number matches an unclaimed roster entry **and** that entry's email equals the user's verified email, membership activates automatically. | P0 | 3 |
| MEMBER-004 | Every other outcome returns the **same** response to the requester ("Request sent — your college will review it") so the endpoint cannot be used to discover which roll numbers exist or are claimed. The request becomes PENDING with a server-side `verification_flag`: `NO_ROSTER_EMAIL`, `EMAIL_MISMATCH`, `ROSTER_CLAIMED`, or `NO_ROSTER_MATCH`. Requests with a roster match appear in the queue of college admins and of department admins of the roster entry's department; `NO_ROSTER_MATCH` requests appear to college admins only. | P0 | 3 |
| MEMBER-005 | A roster entry can be held by at most one ACTIVE membership (DB-enforced). Approving a `ROSTER_CLAIMED` request fails with 409 until the existing membership is ended. | P0 | 3 |
| MEMBER-006 | Approvers can approve or reject a pending request; the queue shows the roster name, roll number, department and flag next to the requester's display name and verified email. Rejection requires a reason shown to the requester. `NO_ROSTER_MATCH` requests can only be rejected, or approved after a roster entry is added. Both actions are audit-logged. | P0 | 3 |
| MEMBER-007 | Faculty and staff join only via an email invitation from a college admin (single-use, 7-day expiry, bound to the invited email). Accepting a valid invite marks the account's email as verified. | P0 | 3 |
| MEMBER-008 | [Decision] A user has at most **one ACTIVE college membership** in the MVP. Multi-college membership is P2. | P0 | 3 |
| MEMBER-009 | Membership status `PENDING`, `ACTIVE`, `REJECTED`, `SUSPENDED`, `ENDED`. Only ACTIVE memberships grant any college access. | P0 | 3 |
| MEMBER-010 | Membership requests limited to 5 per user per 24 h. | P0 | 3 |
| MEMBER-011 | College admins can end or suspend memberships (e.g., graduation); ended memberships lose access immediately; their authored content remains attributed with the display name. Ending or suspending the membership of the college's last COLLEGE_ADMIN is rejected (409). | P0 | 3 |

### 9.3 Tenancy and roles (TENANT)

| ID | Requirement | Pri | Phase |
|---|---|---|---|
| TENANT-001 | The acting college for every campus request is derived server-side from the session user's ACTIVE membership. Any client-supplied college identifier on campus endpoints is ignored or rejected. | P0 | 3 |
| TENANT-002 | Requests for any college-scoped object belonging to another college return **404** with the same body as a non-existent object. | P0 | 3 |
| TENANT-003 | Lists, searches, feeds, and counts apply the same authorization as single-object reads. | P0 | 3 |
| TENANT-004 | Every college-scoped table carries `college_id`; cross-table references within a college are enforced with composite foreign keys including `college_id` (see `architecture.md` §9). | P0 | 1–3 |
| TENANT-005 | An automated tenant-isolation test suite seeds two colleges and attempts every college-scoped endpoint across tenants; all must deny. Suite runs in CI. | P0 | 3 → every phase |

### 9.4 Departments (DEPT)

| ID | Requirement | Pri | Phase |
|---|---|---|---|
| DEPT-001 | College admins create, rename, and archive departments (name, unique code). | P0 | 3 |
| DEPT-002 | College admins grant/revoke DEPARTMENT_ADMIN for a specific department to an ACTIVE faculty/staff member. Students cannot hold this role. | P0 | 3 |
| DEPT-003 | Each department has a page showing description, department admins (names only), current department notices, and department feed link. | P0 | 4 |
| DEPT-004 | Department admins can edit their department's description. | P0 | 4 |

### 9.5 Notices (NOTICE)

| ID | Requirement | Pri | Phase |
|---|---|---|---|
| NOTICE-001 | Notice fields: title (≤150), body (≤10,000, Markdown subset: paragraphs, bold, italic, lists, links), category (Academic, Examination, Administrative, Event, Facilities, General), priority (NORMAL, HIGH, URGENT), scope (COLLEGE or DEPARTMENT), optional expires_at. Notices are visible to everyone in their scope (students, faculty and staff alike); targeting by membership kind is P1 (NOTICE-012). | P0 | 4 |
| NOTICE-002 | COLLEGE_ADMIN publishes college-scope notices; DEPARTMENT_ADMIN publishes notices for their own department only. Nobody else can publish. | P0 | 4 |
| NOTICE-003 | States: DRAFT → PUBLISHED → WITHDRAWN. Publishing takes effect immediately and sets `published_at` (scheduled publishing is P1, NOTICE-011). Withdrawn notices are invisible to readers; withdrawal requires a reason and is audit-logged. | P0 | 4 |
| NOTICE-004 | Readers see only PUBLISHED notices whose scope includes them (scope COLLEGE = all ACTIVE members; scope DEPARTMENT = members whose home department is that department). College admins see all published notices in their college and department admins see all published notices of their departments. Drafts and withdrawn notices are visible only to members who may edit them (NOTICE-006). Expired notices disappear from the default list but remain in "Past notices". | P0 | 4 |
| NOTICE-005 | List order: URGENT unexpired pinned first, then by published_at descending; cursor-paginated (20/page); filterable by category and department. | P0 | 4 |
| NOTICE-006 | A notice may be edited or withdrawn by its author while they can still publish in its scope, or by any member who can publish in that scope (NOTICE-002). Editing a published notice records an "updated" timestamp shown to readers; edit history is audit-logged. | P0 | 4 |
| NOTICE-007 | HIGH/URGENT notices create an in-app notification for each targeted member. | P0 | 4 |
| NOTICE-008 | PDF attachments (≤10 MB, max 3 per notice). | P1 | 11 |
| NOTICE-009 | Read receipts ("x of y students opened") for URGENT notices. | P1 | 11 |
| NOTICE-010 | Section-level academic announcements by assigned faculty. | P1 | 11 |
| NOTICE-011 | Scheduled publishing: a future `publish_at`; the notice stays invisible to readers until then, and HIGH/URGENT notifications are sent once when it becomes visible (requires the Jobs CLI to run every minute). Deferred by P-9. | P1 | 11 |
| NOTICE-012 | Audience targeting by membership kind (ALL, STUDENTS, FACULTY_STAFF) within a scope. Deferred by P-9. | P1 | 11 |

### 9.6 Academic Hub (ACADEMIC)

[Decision] All academic data is entered manually or by CSV in the MVP. No ERP integration. In development and demos, academic data is synthetic and labelled "Demo data".

| ID | Requirement | Pri | Phase |
|---|---|---|---|
| ACADEMIC-001 | College admins manage academic terms (name, start, end; exactly one current term per college). | P0 | 7 |
| ACADEMIC-002 | Department admins (for their departments) and college admins manage subjects (code unique per college) and class sections (subject + term + section name), assign ACTIVE faculty members of the same college to sections, and enroll ACTIVE student members of the same college by uploading a CSV of roll numbers or selecting members. Removing an enrollment that already has attendance or results is rejected (409). | P0 | 7 |
| ACADEMIC-003 | Department admins (for their departments) and college admins manage timetable entries (section, weekday, start, end, room). Overlapping entries for the same section are rejected. | P0 | 7 |
| ACADEMIC-004 | Students see their own weekly timetable for the current term. | P0 | 7 |
| ACADEMIC-005 | Assigned faculty record attendance per section per class session (date + slot): each enrolled student PRESENT, ABSENT, or EXCUSED. One session per section/date/slot (DB-enforced). The date must fall within the section's term and not be in the future (college timezone). | P0 | 7 |
| ACADEMIC-006 | Assigned faculty may edit a session's attendance within 48 h of creation (configurable per college). After that, only a department admin of the section's department may edit, with a mandatory reason. All edits record previous value, new value, actor, reason in the audit log. | P0 | 7 |
| ACADEMIC-007 | Students see, per enrolled subject: sessions held, attended, percentage (EXCUSED excluded from denominator — [Assumption] to validate per college), and session-level history. They see no other student's data. | P0 | 7 |
| ACADEMIC-008 | Assigned faculty create assessments (name, type, max score, date) and enter scores (0 ≤ score ≤ max, or ABSENT). Scores are invisible to students until the assessment is published. | P0 | 7 |
| ACADEMIC-009 | An assessment is published by its section's assigned faculty or a department admin of the section's department. Publishing notifies enrolled students. Changing a score after publishing requires a reason, is audit-logged, and marks the result "Revised" for the student. | P0 | 7 |
| ACADEMIC-010 | Access matrix (§11) is enforced: faculty see only assigned sections; department admins see their department; college admins see their college; platform admins see none. Non-student access is through read-only section views (attendance sessions, assessment results); there is no "browse any student" search. | P0 | 7 |
| ACADEMIC-011 | CSV import of assessment scores. | P1 | 11 |
| ACADEMIC-012 | Attendance-shortage warning when below a college-configured threshold. | P1 | 11 |
| ACADEMIC-013 | Audit log entries for individual reads of a student's records by admins. | P1 | 11 |
| ACADEMIC-014 | ERP/LMS integration adapters. | P2 | — |

### 9.7 Community (COMMUNITY)

| ID | Requirement | Pri | Phase |
|---|---|---|---|
| COMMUNITY-001 | ACTIVE members create text posts (1–5,000 chars, plain text with auto-linked URLs) with visibility COLLEGE or DEPARTMENT (own home department only). | P0 | 6 |
| COMMUNITY-002 | College feed shows COLLEGE posts; department feed shows that department's posts to members of that department, its department admins, and college admins. Reverse-chronological, cursor-paginated (20/page). | P0 | 6 |
| COMMUNITY-003 | Comments (1–2,000 chars), single level (no nesting). | P0 | 6 |
| COMMUNITY-004 | One reaction per member per post ("Helpful"), toggleable; DB-enforced uniqueness. | P0 | 6 |
| COMMUNITY-005 | Authors can edit (shown as "edited") and delete their own posts/comments. Deletion is soft; content is removed from all reads. | P0 | 6 |
| COMMUNITY-006 | Any member can report a post or comment (reason: harassment, spam, misinformation, personal information, other + optional note). One open report per member per target. | P0 | 6 |
| COMMUNITY-007 | Moderators (college admins for all; department admins for their department's posts) see a reports queue and can hide content (with reason, author notified) or dismiss reports. Actions audit-logged. | P0 | 6 |
| COMMUNITY-008 | Post rate limit: 10 posts and 60 comments per member per hour. | P0 | 6 |
| COMMUNITY-009 | Faculty/staff posts display a role badge; posts never display the "Official" treatment reserved for notices. | P0 | 6 |
| COMMUNITY-010 | No anonymous posting. [Decision] | P0 | 6 |
| COMMUNITY-011 | Image attachments on posts. | P1 | 11 |
| COMMUNITY-012 | Auto-hide content after N distinct reports pending moderator review. | P1 | 11 |
| COMMUNITY-013 | Cross-college public "Network" feed (opt-in). | P2 | — |

### 9.8 Campus issues (ISSUE)

| ID | Requirement | Pri | Phase |
|---|---|---|---|
| ISSUE-001 | ACTIVE members submit an issue: category (Classroom equipment, Infrastructure, Water & sanitation, Electrical, Network/Wi-Fi, Library, Laboratory, Other), title (≤120), description (≤3,000), location text (≤200), optional building/room. | P0 | 5 |
| ISSUE-002 | Lifecycle and transitions exactly as in §9.8.1. Invalid transitions return 409. | P0 | 5 |
| ISSUE-003 | Issue visibility: reporter, ISSUE_COORDINATORs, COLLEGE_ADMINs, and the current assignee. Not visible to other students in the MVP. | P0 | 5 |
| ISSUE-004 | Coordinators assign an issue to an ACTIVE faculty/staff member of the same college; assignee sees "Assigned to me". | P0 | 5 |
| ISSUE-005 | Every status change, assignment, and comment creates an immutable IssueUpdate (actor, from, to, note, timestamp). Updates may be marked internal (hidden from reporter). The reporter may add public comments while the issue is not REJECTED; coordinators, college admins and the assignee may add public or internal comments. | P0 | 5 |
| ISSUE-006 | Coordinators can mark an issue duplicate of another same-college issue (sets REJECTED with reason DUPLICATE and link). The duplicate's reporter sees only the canonical issue's status and resolution date — never its title, description, location, updates, or reporter. | P0 | 5 |
| ISSUE-007 | Rate limit: 5 issues per member per 24 h. Coordinators can reject abusive reports with reason. | P0 | 5 |
| ISSUE-008 | Reporter receives in-app notification on each non-internal status change. | P0 | 5 |
| ISSUE-009 | Coordinator queue filters: status, category, assignee, age; sorted oldest-unacknowledged first. | P0 | 5 |
| ISSUE-010 | Optional photo evidence (≤3 images, JPEG/PNG/WebP, ≤5 MB each, EXIF stripped). | P1 | 11 |
| ISSUE-011 | "Me too" confirmations from other members on college-visible issues. | P2 | — |

#### 9.8.1 Issue lifecycle

| From | To | Who | Required |
|---|---|---|---|
| SUBMITTED | ACKNOWLEDGED | Coordinator, College admin | — |
| ACKNOWLEDGED | IN_PROGRESS | Coordinator, College admin, Assignee | — |
| IN_PROGRESS | RESOLVED | Coordinator, College admin, Assignee | Resolution note |
| SUBMITTED, ACKNOWLEDGED | REJECTED | Coordinator, College admin | Reason (incl. DUPLICATE + link) |
| RESOLVED | ACKNOWLEDGED (reopen) | Reporter within 14 days of resolution, at most 2 reporter reopens per issue; Coordinator anytime | Reason |
| REJECTED | ACKNOWLEDGED (reopen) | Coordinator, College admin | Reason |

The product never claims automatic resolution; RESOLVED always has a human actor and note.

### 9.9 Events (EVENT)

| ID | Requirement | Pri | Phase |
|---|---|---|---|
| EVENT-001 | College/department admins create events (title, description, start, end, location, organizer department or club name, visibility COLLEGE/DEPARTMENT). | P1 | 11 |
| EVENT-002 | Members RSVP (going / not going); optional capacity enforced with row locking. | P1 | 11 |
| EVENT-003 | College admins may mark an event PUBLIC; public events are visible to authenticated users of any college. | P2 | — |
| EVENT-004 | Event reminders 24 h before start for RSVP'd members. | P2 | — |

[Decision] Events are not in the first MVP release: notices with category "Event" cover announcements until EVENT-001 ships.

### 9.10 Notifications (NOTIF)

| ID | Requirement | Pri | Phase |
|---|---|---|---|
| NOTIF-001 | In-app notifications list (newest first, cursor-paginated) with unread count in the navigation. Only notifications without a college or belonging to the user's current ACTIVE membership's college are listed or counted. | P0 | 4 |
| NOTIF-002 | Notification types in MVP: membership decided, HIGH/URGENT notice published, issue status changed, issue assigned to me, assessment published/revised, my content hidden by moderator. Each type ships in the phase of its source module; the membership type ships in Phase 4. | P0 | 4–7 |
| NOTIF-003 | Mark one / mark all as read. Notifications older than 90 days are deleted. | P0 | 4 |
| NOTIF-004 | Notifications contain only references and non-sensitive titles; never scores or attendance values. | P0 | 4 |
| NOTIF-005 | Unread count refreshes on window focus and every 60 s while visible (polling; no WebSockets). | P0 | 4 |
| NOTIF-006 | Email digest for urgent notices (opt-out). | P1 | 11 |
| NOTIF-007 | Web push. | P2 | — |

### 9.11 Administration (ADMIN)

| ID | Requirement | Pri | Phase |
|---|---|---|---|
| ADMIN-001 | Platform admins create colleges (name, slug, timezone, optional recognized email domains) in state ONBOARDING, then activate or suspend them. A SUSPENDED college denies all campus access to its members. | P0 | 3 |
| ADMIN-002 | Platform admins invite the first college admin of a college. [Decision, P-7] An account with `PLATFORM_ADMIN` cannot hold or accept a college membership (operators who also work at a college use a separate account). A platform-issued admin invite to a college that already has a COLLEGE_ADMIN requires a reason, is audit-logged, and notifies the existing college admins. | P0 | 3 |
| ADMIN-003 | College admins grant/revoke COLLEGE_ADMIN, DEPARTMENT_ADMIN, ISSUE_COORDINATOR to ACTIVE members of their college. A college must always retain ≥1 COLLEGE_ADMIN (last one cannot be revoked). | P0 | 3 |
| ADMIN-004 | Platform admins can suspend/unsuspend or deactivate any user account platform-wide (with reason). | P0 | 3 |
| ADMIN-005 | Platform admin accounts are created only through a server-side CLI command, never through the UI or API. | P0 | 2 |
| ADMIN-006 | Audit log records: sign-in failures beyond threshold, role grants/revocations, membership decisions, suspensions, notice publish/edit/withdraw, attendance and score changes after initial entry or publication, moderation actions, issue transitions, college lifecycle changes. Entries are append-only and never contain passwords, tokens, or score/attendance values beyond what's needed to identify the change. | P0 | 2 → all |
| ADMIN-007 | College admins can view their college's audit log (filter by actor, action, date). Platform admins can view platform-level entries (college lifecycle, platform suspensions). | P0 | 3 |
| ADMIN-008 | Platform admins have **no** read access to college posts, notices drafts, academic records, or issues. [Decision] | P0 | 3 |
| ADMIN-009 | Platform health page: app version, DB reachable, migration revision, count of colleges/users. | P1 | 11 |

### 9.12 Home and profile (HOME, PROFILE)

| ID | Requirement | Pri | Phase |
|---|---|---|---|
| HOME-001 | Student home shows: unexpired URGENT notices (if any), today's classes, per-subject attendance percentage, own open issues, 5 latest notices. Each block has its own empty and error state. | P0 | 8 |
| HOME-002 | Faculty home shows today's classes from their sections and sections with no attendance recorded for a timetabled class in the last 7 days. | P0 | 8 |
| HOME-003 | Admin overview (college admins, department admins, issue coordinators) shows counts and links for only the queues the viewer can act on: pending membership requests, open content reports, unacknowledged issues. | P0 | 8 |
| HOME-004 | Home data is composed from existing services and policies; it exposes nothing the viewer could not read through the module endpoints. | P0 | 8 |
| PROFILE-001 | Users can change display name (1–60 chars), view their membership (college, department, kind — read-only), change password (AUTH-010), sign out of all devices (AUTH-005), and choose theme. | P0 | 8 |

## 10. Non-functional requirements

| ID | Requirement | Pri |
|---|---|---|
| NFR-SEC-001 | All traffic over HTTPS; HSTS enabled in production. | P0 |
| NFR-SEC-002 | Security headers: CSP (no inline scripts), `X-Content-Type-Options: nosniff`, `Referrer-Policy: strict-origin-when-cross-origin`, `frame-ancestors 'none'`. | P0 |
| NFR-SEC-003 | All input validated by schema at the API boundary; unknown fields rejected (`extra="forbid"`). | P0 |
| NFR-SEC-004 | Secrets only from environment; `.env` never committed. | P0 |
| NFR-PERF-001 | p95 API latency < 300 ms for list/detail endpoints at 50 concurrent users on the reference deployment (measured in Phase 9). | P0 |
| NFR-PERF-002 | Initial JS bundle ≤ 250 KB gzipped; route-level code splitting. | P0 |
| NFR-PERF-003 | Usable on a mid-range Android phone over 4G: Largest Contentful Paint < 2.5 s for Home. | P1 |
| NFR-A11Y-001 | WCAG 2.2 AA for all MVP screens (see §18). | P0 |
| NFR-REL-001 | Daily database backups retained 14 days; restore procedure tested before release. | P0 |
| NFR-REL-002 | `Idempotency-Key` support on create endpoints (posts, comments, issues) so network retries never create duplicates. Deferred by P-9 to Phase 11; MVP relies on disabled-while-pending submit buttons. | P1 |
| NFR-OPS-001 | Structured logs with request IDs; health and readiness endpoints. | P0 |
| NFR-I18N-001 | English UI in MVP; strings centralized to allow later localization. Dates shown in the college's timezone. | P0 |
| NFR-MAINT-001 | Backend test coverage of policies and services ≥ 90% lines; overall ≥ 80%. | P0 |

## 11. User roles and permissions

### Role model

- **Platform role** (on the user): `PLATFORM_ADMIN` or none.
- **Membership kind** (per college): `STUDENT`, `FACULTY`, `STAFF`.
- **Role grants** (per membership, additive): `COLLEGE_ADMIN`, `DEPARTMENT_ADMIN` (bound to one department; may hold several grants), `ISSUE_COORDINATOR`. Students cannot hold grants.

### Permission matrix (MVP)

✅ allowed · 🔸 limited (see note) · — not allowed

| Capability | Student | Faculty | Staff | Dept admin | College admin | Issue coord. | Platform admin |
|---|---|---|---|---|---|---|---|
| Read college notices (in scope) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | — |
| Publish notices | — | — | — | 🔸 own dept | ✅ college | — | — |
| Read college feed / post / comment / react | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | — |
| Read department feed | 🔸 own dept | 🔸 own dept | 🔸 own dept | ✅ granted depts | ✅ | 🔸 own dept | — |
| Moderate community | — | — | — | 🔸 own dept posts | ✅ | — | — |
| Own timetable/attendance/results | ✅ | n/a | n/a | n/a | n/a | n/a | — |
| Record attendance / enter marks | — | 🔸 assigned sections | — | 🔸 corrections in dept | — | — | — |
| Read academic records of others | — | 🔸 assigned sections | — | 🔸 dept | ✅ [Assumption] | — | — |
| Manage subjects, sections, timetable, enrollment | — | — | — | 🔸 dept | ✅ | — | — |
| Submit / track own issues | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | — |
| Triage/assign issues | — | — | — | — | ✅ | ✅ | — |
| Update assigned issues | — | 🔸 if assignee | 🔸 if assignee | 🔸 if assignee | ✅ | ✅ | — |
| Approve student memberships | — | — | — | 🔸 dept roster entries | ✅ | — | — |
| Member directory (search members) | — | — | — | 🔸 dept students + college faculty/staff | ✅ | 🔸 faculty/staff as assignees | — |
| Invite faculty/staff, grant roles, import roster | — | — | — | — | ✅ | — | — |
| College audit log | — | — | — | — | ✅ | — | — |
| Create/suspend colleges, platform user suspension | — | — | — | — | — | — | ✅ |

"Own dept" = the membership's home department. A department admin's powers apply only to departments in their grants.

## 12. Feature prioritization summary

| Module | P0 (MVP) | P1 | P2 |
|---|---|---|---|
| Auth | Register, verify, sessions, reset, rate limits, CSRF | Email change | TOTP |
| Membership | Roster verification, approvals, invites | — | Multi-college membership |
| Notices | Scoped notices, publish, edit, withdraw | Scheduling, audience by kind, attachments, read receipts, section announcements | — |
| Academic | Terms, sections, timetable, attendance, results | Marks CSV, shortage warning, read audits | ERP integration |
| Community | Text posts, comments, reactions, reports, moderation | Images, auto-hide | Cross-college network |
| Issues | Submit, lifecycle, assign, duplicates | Photos | "Me too" |
| Events | — | Events, RSVP | Public events, reminders |
| Notifications | In-app | Email digest | Push |
| Admin | College onboarding, roles, audit | Health page | — |
| Home & profile | Role home screens, profile/settings | — | — |

## 13. MVP scope

The MVP is everything marked P0, delivered across Phases 1–10 with two intermediate releases (see `Phases.md` §2):

- **Release α (after Phase 4, staging, synthetic data):** accounts, verification, departments, notices, in-app notifications.
- **Release β (after Phase 6, staging, internal pilot):** + campus issues, community.
- **MVP (after Phase 10, production):** + Academic Hub, role home screens, hardening, production deployment.

## 14. Explicitly excluded from the MVP

Events/RSVP; file and image uploads of any kind; email notifications other than account emails; push notifications; real-time updates; direct messaging; anonymous posting; cross-college feeds; multi-college membership; ERP/LMS integrations; fee/payment features; native apps; analytics dashboards with charts; AI features; TOTP.

## 15. User stories and acceptance criteria

Each story's criteria are testable; IDs reference §9.

**US-01 Student registration (AUTH-001..003)**
As a student, I want to create an account so I can join my college.
- [ ] Registering with a new email returns 201 and sends one verification email.
- [ ] Registering with an existing email (any case) returns the same success message without creating a second account and without revealing existence; the existing owner receives a "someone tried to register" email.
- [ ] Password "password1234" is rejected with a field-level error.
- [ ] Verification link used twice: second use shows "link already used".
- [ ] Verification link after 24 h shows "link expired" with a resend action.

**US-02 Join college via roster (MEMBER-002..005)**
- [ ] Roll number + verified email matching an unclaimed roster entry → membership ACTIVE, user lands on college home.
- [ ] Roll number matches but roster email absent → PENDING; user sees "Waiting for approval by <college>".
- [ ] Roll number already claimed → PENDING with flag `ROSTER_CLAIMED` visible to approvers only.
- [ ] Unknown roll number → response byte-identical (apart from IDs) to the roster-email-missing case; request flagged `NO_ROSTER_MATCH`, visible to college admins only.
- [ ] Unverified user → 403 with "Verify your email first".
- [ ] A user with an ACTIVE membership cannot request another (409).

**US-03 Approve membership (MEMBER-006)**
- [ ] Dept admin sees only requests whose roster entry is in their granted department.
- [ ] Rejecting without reason → 422.
- [ ] Approve/reject creates an audit entry (Phase 3) and a notification to the requester (added in Phase 4).
- [ ] A college admin of college B calling approve on college A's request → 404.

**US-04 Publish notice (NOTICE-001..005)**
- [ ] Dept admin publishing with scope COLLEGE → 403.
- [ ] Dept admin publishing to another department → 404 for that department.
- [ ] A DEPARTMENT-scope notice is absent for members of other departments (list and direct GET → 404).
- [ ] A DRAFT notice is absent for readers (list and direct GET → 404) and visible to its author.
- [ ] Request bodies containing `publish_at` or `audience` are rejected (422, unknown field) in the MVP.
- [ ] URGENT unexpired notice appears first regardless of date.

**US-05 View attendance (ACADEMIC-007)**
- [ ] Student sees one row per enrolled subject with held/attended/percentage matching the recorded sessions.
- [ ] Student with no sessions sees "No attendance has been recorded for this term yet."
- [ ] Requesting another student's attendance by any ID → 404.

**US-06 Record attendance (ACADEMIC-005..006)**
- [ ] Faculty not assigned to section → 404.
- [ ] Creating a second session for same section/date/slot → 409.
- [ ] Faculty edit after 48 h → 403 with message "Edit window closed — ask your department admin".
- [ ] Dept admin edit without reason → 422; with reason → audit entry includes old/new status.

**US-07 Publish results (ACADEMIC-008..009)**
- [ ] Score > max → 422.
- [ ] Before publish, student GET results excludes the assessment.
- [ ] After publish, enrolled students receive one notification each; non-enrolled receive none.
- [ ] Post-publish change without reason → 422; with reason → result shows "Revised".

**US-08 Report a campus issue (ISSUE-001..003, 007)**
- [ ] Valid submission returns 201 with status SUBMITTED.
- [ ] Sixth submission in 24 h → 429.
- [ ] Another student requesting the issue → 404.

**US-09 Handle an issue (ISSUE-002, 004..006)**
- [ ] Assignee moving SUBMITTED → IN_PROGRESS → 409 (must be acknowledged first).
- [ ] RESOLVED without note → 422.
- [ ] Internal update not returned to reporter.
- [ ] Assigning to a member of another college → 404.

**US-10 Post and moderate (COMMUNITY-001..007)**
- [ ] Department post invisible to members of other departments (feed and direct GET).
- [ ] Second reaction by same member → toggles off, never duplicates.
- [ ] Hidden post disappears from feed for everyone except moderators, and author is notified with reason.
- [ ] Dept admin cannot hide a COLLEGE-visibility post (403).

**US-11 Onboard a college (ADMIN-001..002)**
- [ ] Creating a college with an existing slug → 409.
- [ ] Members of an ONBOARDING or SUSPENDED college cannot access campus endpoints (403 `college_inactive`).
- [ ] Invited college admin accepting invite gets ACTIVE FACULTY/STAFF membership + COLLEGE_ADMIN grant.
- [ ] A platform admin account attempting to accept any college invite or request membership → 403 (P-7).

**US-12 Notifications (NOTIF-001..005, NOTICE-007)**
- [ ] Publishing an URGENT college notice creates exactly one notification per ACTIVE member of the college and none for other colleges; an URGENT department notice notifies only that department's members.
- [ ] A NORMAL notice creates no notifications.
- [ ] Editing an already-published HIGH notice creates no additional notifications.
- [ ] Mark-all-read sets unread count to 0; another user's notification ID → 404.
- [ ] No notification payload contains scores or attendance values (asserted on every type).

**US-13 Academic setup and timetable (ACADEMIC-001..004)**
- [ ] Creating a second current term → 409.
- [ ] Dept admin creating a section in another department → 404 for that subject.
- [ ] Enrollment CSV with an unknown or non-student roll number → 422 listing the rows; nothing enrolled.
- [ ] Overlapping timetable entry for the same section → 409.
- [ ] Student timetable shows only sections they are enrolled in for the current term.

**US-14 Roles and audit (ADMIN-003, ADMIN-006..008, MEMBER-011)**
- [ ] Revoking, ending, or suspending the last COLLEGE_ADMIN → 409.
- [ ] Granting any role to a STUDENT membership → 422.
- [ ] Each action in ADMIN-006 produces exactly one audit entry with actor, action, target, reason (where required) and no password, token, score or attendance value.
- [ ] College admin audit log never contains entries of another college; platform admin calling any `/campus/*` or academic route → 403/404.

**US-15 Department page (DEPT-003/004)**
- [ ] Department page lists only notices the viewer may read.
- [ ] Dept admin edits own department description; editing another department → 404.

**US-16 Home and profile (HOME-001..004, PROFILE-001)**
- [ ] Each home block shows real data or its empty state; a failing block does not hide other blocks.
- [ ] Admin overview shows only queues the viewer can act on (student sees none).
- [ ] Display name > 60 chars → 422.

**US-17 Privileged sessions (AUTH-004, AUTH-013)**
- [ ] A faculty session idle for > 24 h → 401 on next request; a student session idle for 24 h is still valid.
- [ ] A COLLEGE_ADMIN session older than 7 days since sign-in → 401 even if active; a student session of the same age is valid.
- [ ] Granting DEPARTMENT_ADMIN to a staff member whose session is 8 days old ends that session on their next request.
- [ ] An ISSUE_COORDINATOR-only staff session keeps standard limits.

## 16. Error states and edge cases

| Situation | Expected behavior |
|---|---|
| Session expired mid-form | 401 → UI preserves form input in memory, prompts sign-in, returns to form |
| Double-click submit | Buttons disable while pending. A network-level retry can still create a duplicate in the MVP (accepted risk; authors can delete; `Idempotency-Key` is P1, NFR-REL-002) |
| Membership ended while signed in | Next request returns 403 `membership_inactive`; UI shows explanation and support contact |
| College suspended | All campus endpoints 403 `college_inactive`; account settings still reachable |
| Roster re-import changes a claimed entry | Claimed entries cannot be deleted by re-import; import reports them as conflicts |
| Student moves department | College admin updates home department; department feed access changes immediately |
| Faculty unassigned from section | Loses access immediately; previously recorded attendance retains author attribution |
| Notice expires while being read | Remains readable at its URL with an "Expired" label |
| Concurrent attendance edits | Optimistic concurrency via `version` field; stale write → 409 "Changed by someone else, reload" |
| Issue assignee's membership ends | Issue returns to coordinator queue as unassigned; system IssueUpdate recorded |
| Deleted post with comments | Post and its comments disappear from reads; reports remain for moderators |
| Last college admin leaves | Revoking, ending or suspending the last COLLEGE_ADMIN rejected (409); if their user account is platform-suspended, the platform admin re-invites a college admin under ADMIN-002 |
| Enrollment removed after attendance/results exist | Rejected (409); records are never orphaned |
| Attendance for a future date or outside the term | 422 |
| Reporter reopens a resolved issue a third time | 403 with "Contact the facilities office"; coordinator may still reopen |
| User's membership moves to another college (after ending) | Notifications from the old college are no longer listed (NOTIF-001) |

## 17. Security and privacy requirements

Concrete controls (implementation detail in `architecture.md` §10 and §22, rules in `Rules.md` §2):

1. Every protected endpoint invokes an explicit policy function; CI test asserts each route is covered by a policy (route inventory test).
2. Object-level authorization: load object → check college and role → act. Knowing an ID grants nothing.
3. Cross-college access returns 404 with a body identical to not-found.
4. Mass assignment prevented: request schemas list only client-writable fields; `college_id`, `author_id`, `status`, roles are never read from bodies on campus endpoints.
5. Academic data, roll numbers, and emails never appear in logs, notifications, error messages, or URLs.
6. Profile exposure: other members see display name, membership kind, department. Roll number and email visible only to self, college admins, dept admins of their department, and faculty of their sections (roll number only).
7. Tokens (session, verification, reset, invite) stored only as SHA-256 hashes.
8. Rate limits per §9; responses 429 with `Retry-After`.
9. Audit log per ADMIN-006.
10. Data retention [Assumption, validate with colleges]: audit logs 2 years; notifications 90 days; sessions purged at expiry; ended memberships' academic records retained until the college requests deletion.
11. Account deletion (P1): removes personal data, keeps academic records under college ownership pseudonymized, keeps posts as "Former member".
12. No member enumeration: the member directory is available only to admins (§11); issue coordinators get an assignee picker limited to ACTIVE faculty/staff; membership requests never reveal roster contents (MEMBER-004).
13. Platform admins are separated from college data (ADMIN-008) and from college memberships (P-7).
14. Accounts able to read other students' academic records use shorter sessions (AUTH-013).
15. Demo/seed data is synthetic, uses fictional colleges ("Northfield Institute", "Riverside College"), and is visibly labelled.

## 18. Accessibility requirements

- WCAG 2.2 AA: text contrast ≥ 4.5:1 (≥ 3:1 for large text and UI component boundaries).
- All functionality operable by keyboard; visible focus indicator (see `Design.md` §3.9).
- Form fields have programmatic labels; errors are announced (`aria-live`) and linked with `aria-describedby`.
- Status (issue state, attendance status, priority) never conveyed by color alone.
- Respects `prefers-reduced-motion` and `prefers-color-scheme`.
- Touch targets ≥ 44×44 px on mobile.
- Automated axe checks in E2E for every MVP screen; manual screen-reader pass (NVDA) on J1–J5 before release.

## 19. Performance expectations

See NFR-PERF-*. Additionally: lists are paginated (never unbounded); attendance summary for a student computed by a single aggregate query; no N+1 queries on feeds (verified by query-count assertions in tests).

## 20. Analytics and success metrics

Privacy-respecting, server-side aggregate counts only (no third-party trackers in MVP). In the MVP these are computed by operators with documented read-only SQL queries (added to the runbook in Phase 10); there is no metrics dashboard.

| Metric | Target (first semester after launch at a pilot college) — [Assumption] |
|---|---|
| Verified students / roster size | ≥ 50% |
| Weekly active members / verified | ≥ 40% |
| Median time SUBMITTED → ACKNOWLEDGED | ≤ 2 working days |
| Issues RESOLVED within 14 days | ≥ 60% |
| Sections with attendance recorded weekly | ≥ 70% at pilot |
| Cross-tenant authorization failures in production | 0 |

Targets are hypotheses for a pilot; they are not claimed results.

## 21. Risks and assumptions

| # | Risk / assumption | Mitigation |
|---|---|---|
| R1 | Colleges may not supply rosters | Manual approval path (MEMBER-004); invite path for staff |
| R2 | Faculty adoption of attendance entry is uncertain | Fast grid with "all present" default; pilot with one department |
| R3 | Legal/data-protection obligations for academic data (e.g., India's DPDP Act 2023) | Data processing agreement with each college before real data; legal review pending |
| R4 | Community misuse | Reports, moderation, rate limits, no anonymity |
| R5 | Small team capacity | Phase plan with early releases; P1 deferrals |
| A1 | One active college per user is sufficient for MVP | Validate with pilot |
| A2 | College admins should read all academic data in their college | Validate with pilot; can be narrowed |
| A3 | EXCUSED excluded from attendance denominator | Make configurable if colleges differ |
| A4 | English-only UI acceptable | Strings centralized |

**Open decisions** (also tracked in `memory.md`): P-1 hosting provider; P-2 transactional email provider; P-3 pilot college and legal agreement; P-5 attendance edit window default; P-6 error-tracking service (Sentry or none); P-10 whether platform-admin sessions also use the privileged limits.

**Resolved 2026-10-20:** P-4 CampusSignal is the official name (`CLAUDE.md` updated); P-7 separate platform-admin accounts (ADMIN-002); P-8 privileged sessions 24 h idle / 7 d absolute (AUTH-013); P-9 scheduled publishing, idempotency keys and audience-by-kind deferred to P1 (NOTICE-011, NOTICE-012, NFR-REL-002).

## 22. Dependencies and external integrations

| Dependency | Purpose | MVP? |
|---|---|---|
| Transactional email (SMTP/API) | Verification, reset, invites | Yes (provider pending P-2) |
| PostgreSQL 17 (Supabase for development; production host pending P-1) | Primary datastore | Yes |
| Object storage (S3-compatible) | Attachments, images | No (P1) |
| College ERP / university systems | — | No; not assumed available |

## 23. MVP release criteria

- [ ] All P0 requirements implemented and their acceptance criteria covered by automated tests.
- [ ] Tenant-isolation suite passes for every college-scoped endpoint.
- [ ] Route inventory test: 100% of protected routes call a policy.
- [ ] No open critical/high findings from the Phase 9 security review.
- [ ] axe: zero serious/critical violations on MVP screens; manual keyboard + screen-reader pass done.
- [ ] Backup restore rehearsed on staging.
- [ ] Pilot college has signed the data agreement (P-3) before any real student data is entered.
- [ ] `memory.md` and docs reflect the released state.

## 24. Post-MVP roadmap

1. **Phase 11 (P1):** events + RSVP, scheduled notices and audience targeting, idempotency keys on create endpoints, notice attachments and read receipts, issue photos, marks CSV, attendance shortage warnings, email change, email digest for urgent notices, auto-hide on reports, health page.
2. **P2 candidates (require new PRD sections before work):** multi-college membership, public events and cross-college "Network" feed, TOTP, ERP/LMS adapters, web push, "me too" issue confirmations, PostgreSQL Row-Level Security as defense in depth, localization.
