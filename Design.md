# CampusSignal — UI/UX Design Specification

| | |
|---|---|
| Status | Specification v0.1 — no UI implemented yet |
| Last updated | 2026-10-20 |
| Applies to | All screens in `PRD.md` MVP scope; roles per `PRD.md` §11 |
| Note | `.impeccable/design.json` in this repo describes an unrelated project ("DataSentry") and is **not** a source for CampusSignal. This file is authoritative. |

---

## 1. Design principles

1. **Information first.** Every screen answers one primary question (e.g., "What do I need to know today?"). Decide hierarchy before styling.
2. **Dense, not cluttered.** Lists and tables over card grids. Whitespace separates groups, not every item.
3. **Official looks official.** Notices have a distinct, sober treatment; student posts are conversational. Never mixed in one undifferentiated stream.
4. **Audience is always visible.** Every notice and post shows who can see it (Department / College) as a badge.
5. **Restraint.** One brand color (deep blue), one warm accent used sparingly, neutral everything else. Color carries meaning, not decoration.
6. **Predictable.** Same component, same behavior everywhere. Familiar patterns (lists, tabs, dialogs) over novel ones.
7. **Honest.** Empty states state facts ("No notices in the last 30 days"), never filler. No fake numbers.
8. **Accessible by construction.** Contrast, focus, labels, and non-color status cues are part of every component spec.

## 2. Visual direction

**"Notice board, engineered."** A calm, paper-light utility with a confident deep-blue identity — closer to a well-made transit app or a university library catalogue than to a startup dashboard. Typography does most of the work: a distinctive geometric grotesk for headings, a highly legible humanist sans for reading, and monospaced figures for codes and numbers (roll numbers, subject codes, percentages).

The **signal** motif — the brand's single warm accent — marks *things that need your attention*: unread indicators, the current-item marker in navigation, and the CampusSignal wordmark dot. It is never used for large fills or backgrounds.

Avoid: gradients, glassmorphism, glows, neon, illustration-heavy empty states, oversized hero banners, emoji in UI chrome.

## 3. Design tokens

Tokens are CSS custom properties on `:root` / `[data-theme="dark"]`, mapped into the Tailwind theme (`bg-surface`, `text-muted`, …). Components use **semantic** tokens only; raw palette values never appear in components (`Rules.md` R-3.1). Contrast ratios below were computed with the WCAG 2 formula against the listed background.

### 3.1 Color — light theme

| Token | Value | Use | Contrast |
|---|---|---|---|
| `--bg` | `#F6F7F9` | App background | — |
| `--surface` | `#FFFFFF` | Panels, list containers, dialogs | — |
| `--surface-sunken` | `#EEF1F5` | Table headers, input backgrounds when filled, code blocks | — |
| `--border` | `#DDE2EA` | Dividers, list separators (decorative) | — |
| `--border-strong` | `#868FA0` | Input borders, focusable component boundaries | 3.26 on surface, 3.04 on bg (darkened from `#8A93A3`, which was 2.89 on bg; found by the Phase 1 contrast check) |
| `--text` | `#121826` | Primary text | 17.7 on surface |
| `--text-muted` | `#4A5263` | Secondary text, metadata | 7.8 on surface |
| `--text-subtle` | `#646C7C` | Timestamps, helper text (never sole carrier of meaning) | 5.3 on surface |
| `--primary` | `#1D3C8F` | Primary buttons, links, active nav, official notice rule | 10.0 vs white |
| `--primary-hover` | `#16306F` | Hover/pressed | 12.5 vs white |
| `--primary-subtle` | `#E8EEFB` | Selected rows, official notice header band, College badge bg | primary text 8.6 |
| `--on-primary` | `#FFFFFF` | Text on primary | — |
| `--accent` | `#B8460B` | Signal: unread dot, nav current marker, wordmark dot | 5.4 on surface |
| `--accent-subtle` | `#FDEEE4` | Unread notification row background | accent-fg `#9A3A09` 6.2 |
| `--success` / `--success-subtle` / `--success-fg` | `#15803D` / `#E7F6EC` / `#166534` | Resolved, present, saved | fg 6.4 on subtle |
| `--warning` / `--warning-subtle` / `--warning-fg` | `#B7791F` / `#FEF6DC` / `#854D0E` | High priority, attendance low (P1), pending | fg 6.3 on subtle |
| `--danger` / `--danger-subtle` / `--danger-fg` | `#B42318` / `#FDECEA` / `#912018` | Urgent, errors, destructive, rejected | white on danger 6.6; fg 7.6 on subtle |
| `--on-danger` | `#FFFFFF` (dark theme: `#0F1420`) | Text and icons on solid `--danger` (destructive buttons) | 6.6 light / 8.1 dark |
| `--focus-ring` | `#1D3C8F` | 2 px ring + 2 px offset | 10.0 on surface |

Status base colors (`--success`, `--warning`, `--danger`) are for icons, borders and solid fills; text on light backgrounds uses the `-fg` variant (`--warning` is only 3.6:1 on white, so it is never used for text).

### 3.2 Color — dark theme

| Token | Value | Contrast |
|---|---|---|
| `--bg` | `#0F1420` | — |
| `--surface` | `#171D2B` | — |
| `--surface-sunken` | `#121827` | — |
| `--border` | `#2A3245` | decorative |
| `--border-strong` | `#6E788E` | 3.8 on surface |
| `--text` | `#E7EAF0` | 15.3 on bg |
| `--text-muted` | `#A6AFBF` | 7.6 on surface |
| `--text-subtle` | `#8A93A5` | 5.5 on surface |
| `--primary` | `#93AEF5` | 7.7 on surface (links, active states) |
| `--on-primary` | `#0F1420` | 8.4 on primary (buttons use dark text in dark theme) |
| `--primary-hover` | `#B3C6F8` | on-primary text 10.8 |
| `--primary-subtle` | `#1F2A47` | primary text 6.5 |
| `--accent` | `#FF9566` | 7.8 on surface |
| `--accent-subtle` | `#3A2219` | accent text 6.9 |
| `--success` / `--warning` / `--danger` | `#5BD08A` / `#F5C25B` / `#FF8A80` | 8.7 / 10.2 / 7.4 on surface; destructive buttons use `--bg` text on `--danger` (8.1) |
| `--success-subtle` / `--warning-subtle` / `--danger-subtle` | `#12301F` / `#33290F` / `#3A1A1C` | base color as text: 7.4 / 8.7 / 6.8 |
| `--success-fg` / `--warning-fg` / `--danger-fg` | same as the base colors | — |
| `--focus-ring` | `#93AEF5` | 8.4 on bg |

Theme: follows `prefers-color-scheme` by default; user override (Light / Dark / System) stored in `localStorage` (a UI preference, not sensitive). Both themes are designed, not inverted; status colors keep the same meaning.

### 3.3 Audience and content-type colors

| Marker | Treatment |
|---|---|
| **Official notice** | 3 px left rule in `--primary`, "Official" label + issuer ("Office of the Principal", "Dept. of Physics"), no avatar, heading font for title |
| **Student/staff post** | Avatar (initials), author name, role badge for faculty/staff, body font, no left rule |
| Audience badge: **Department** | Neutral outline badge `border-strong`, text "Dept · PHY" |
| Audience badge: **College** | `primary-subtle` fill, `primary` text, "College" |
| Audience badge: **Public** (P2, reserved) | `accent-subtle` fill, `accent` text — reserved now so the "Network" content is distinct when it ships |

### 3.4 Typography

| Role | Family | Fallback |
|---|---|---|
| Headings, wordmark, numbers in stats | **Space Grotesk** (500, 600) | system-ui, sans-serif |
| Body, UI | **IBM Plex Sans** (400, 500, 600) | system-ui, "Segoe UI", Roboto, sans-serif |
| Codes, roll numbers, tabular figures | **IBM Plex Mono** (400, 500) | ui-monospace, Consolas, monospace |

Self-hosted via @fontsource, `font-display: swap`, Latin subset only.

| Token | Size / line height | Use |
|---|---|---|
| `text-xs` | 12 / 16 | Badges, table meta |
| `text-sm` | 14 / 20 | Secondary UI, list metadata, table cells |
| `text-base` | 16 / 24 | Body, inputs (never smaller on mobile inputs — prevents iOS zoom) |
| `text-lg` | 18 / 28 | Lead text, notice body on desktop |
| `text-xl` | 20 / 28 | Section headings (h3) |
| `text-2xl` | 24 / 32 | Page titles on mobile (h1), h2 on desktop |
| `text-3xl` | 30 / 36 | Page titles on desktop (h1) |

Rules: one h1 per page; headings in Space Grotesk, letter-spacing −0.01em at ≥ 24 px; reading measure ≤ 72 ch; numbers in tables use `font-variant-numeric: tabular-nums`.

### 3.5 Spacing

4 px base. Scale: `0.5`=2, `1`=4, `2`=8, `3`=12, `4`=16, `5`=20, `6`=24, `8`=32, `10`=40, `12`=48, `16`=64. Page gutter: 16 mobile, 24 tablet, 32 desktop. Vertical rhythm between page sections: 32 (desktop), 24 (mobile). List item padding: 12 vertical × 16 horizontal.

### 3.6 Radii

Only three values: `--radius-sm` 4 px (inputs, buttons, badges, table containers), `--radius-md` 8 px (panels, dialogs, menus, toasts), `--radius-full` (avatars, unread dots, toggle). No other radii.

### 3.7 Elevation

| Token | Value | Use |
|---|---|---|
| `--shadow-0` | none | Default; panels rely on `--border` |
| `--shadow-1` | `0 1px 2px rgb(18 24 38 / 0.06), 0 1px 3px rgb(18 24 38 / 0.08)` | Sticky headers, popovers, menus |
| `--shadow-2` | `0 8px 24px rgb(18 24 38 / 0.16)` | Dialogs, toasts |

Dark theme uses borders + `--surface` lightness for elevation; shadows at 2× opacity on black.

### 3.8 Layout and breakpoints

| Token | Value |
|---|---|
| `sm` | 640 px |
| `md` | 768 px |
| `lg` | 1024 px |
| `xl` | 1280 px |
| `--content-max` | 1120 px (app content) |
| `--reading-max` | 720 px (notice/post detail) |
| `--rail-width` | 232 px (desktop navigation) |
| `--container-auth` | 400 px (signed-out screens; Tailwind `max-w-auth`) |

Grid: single column < `lg`; at ≥ `lg`, navigation rail + main column; a secondary column (280 px) only where it carries real context (e.g., issue detail metadata), never for ads/"tips".

### 3.9 Focus

`outline: 2px solid var(--focus-ring); outline-offset: 2px` on `:focus-visible` for all interactive elements, never removed. Inside dark-filled elements (primary button) the offset keeps the ring on the page background.

### 3.10 Motion

| Token | Value | Use |
|---|---|---|
| `--duration-fast` | 120 ms | Hover, press, toggles |
| `--duration-base` | 200 ms | Dialog/menu open, toast enter |
| `--ease-out` | `cubic-bezier(0.2, 0, 0, 1)` | Entering |
| `--ease-in` | `cubic-bezier(0.4, 0, 1, 1)` | Exiting (exit ≈ 75% of enter duration) |

Only opacity and ≤ 8 px translate. No page-transition animations, no looping animations except loading spinners in buttons. `prefers-reduced-motion: reduce` → durations 0 (skeleton shimmer becomes static).

### 3.11 Icons

Lucide (bundled with shadcn/ui) only, 1.5 px stroke, 16 px in dense UI / 20 px in navigation. Icons accompany labels; icon-only buttons require `aria-label` and a tooltip.

## 4. Navigation and information architecture

Navigation is built from `/me` capabilities. Users see only sections they can use.

| Section | Student | Faculty/Staff | Dept admin | College admin | Issue coord. |
|---|---|---|---|---|---|
| Home | ✓ | ✓ | ✓ | ✓ | ✓ |
| Notices | ✓ | ✓ | ✓ (+ Compose) | ✓ (+ Compose) | ✓ |
| Academics (timetable, attendance, results) | ✓ | — | — | — | — |
| Teaching (sections, attendance, assessments) | — | Faculty only | ✓ if faculty | — | — |
| Community (college feed, department feed) | ✓ | ✓ | ✓ | ✓ | ✓ |
| Issues (mine; + Assigned to me if any) | ✓ | ✓ | ✓ | ✓ (+ Queue) | ✓ (+ Queue) |
| Manage (members, departments, roster, academic setup, moderation, audit) | — | — | Dept-scoped items | All | — |
| Platform (colleges, users, audit) | Separate `PlatformShell`, platform admins only | | | | |

**Desktop (≥ lg):** left navigation rail (one level, no nested trees). Top of rail: wordmark + college name (not a switcher in MVP — one active membership). Bottom: notifications bell with unread count, profile menu (Profile & settings, Theme, Sign out). Section sub-pages use **tabs** at the top of the main column (e.g., Academics: Timetable · Attendance · Results).

**Mobile (< lg):** top app bar (page title, notifications bell, profile avatar) + **bottom tab bar** with 4 items: Home, Notices, (Academics for students | Teaching for faculty | Issues for staff), Community; a 5th **More** item opens a sheet with remaining sections (Issues, Manage). Bottom bar hidden while typing in a composer.

**Depth:** maximum two levels (section → tab/detail). Breadcrumbs only in Manage and Platform.

**College context:** shown, not selectable, in MVP. Multi-college switching (P2) will add a switcher in the rail header.

## 5. Screen specifications

States legend: **L** loading, **E** empty, **X** error, **U** unauthorized/forbidden.

| # | Screen | Purpose / primary question | Hierarchy & major components | Important states |
|---|---|---|---|---|
| 1 | **Sign in / Register** | Get in | Centered single column (max 400 px), wordmark, form, secondary link. Register: name, email, password with requirements shown up-front. No marketing panel. | Field errors inline; generic sign-in error; 429 "Too many attempts, try again in N min"; verify-email sent screen with resend (cooldown visible) |
| 2 | **College verification & onboarding** | "Which college, and are you on its roster?" | Step 1 search/select college (combobox). Step 2 roll number (mono font) + explanation of how verification works. Result screens: Active → go to Home; Pending → status page naming the college and expected next step; Rejected → reason + "Contact your college office". | Unverified email → block with resend; an unknown roll number shows the same Pending screen as any other unmatched request (MEMBER-004) |
| 3 | **Student home** | "What do I need to know today?" | Ordered stack, no hero: (1) Urgent notices strip (only if any), (2) Today's classes (from timetable), (3) Attendance at a glance — one line per subject with percentage, mono figures, (4) My open issues with status, (5) Latest notices (5). Each block links to its section. | Each block has its own E state ("No classes today"); a failed block shows inline retry without breaking the page |
| 4 | **Academic Hub** | Container | Tabs: Timetable · Attendance · Results. Term name shown. "Demo data" banner when the college has `is_demo` set. | No current term → "Your college hasn't set up the current term yet." |
| 5 | **Attendance** | "Am I attending enough?" | Table: Subject (code + name), Held, Attended, %, trend-free. Row → session list (date, slot, status with icon + text). | E: "No attendance has been recorded for this term yet." |
| 6 | **Results** | "How did I do?" | Grouped by subject; table of published assessments: name, date, score / max, "Revised" tag where applicable. No GPA computation in MVP. | E: "No results have been published yet." Unpublished assessments never hinted at |
| 7 | **Timetable** | "Where am I supposed to be?" | Mobile: day selector (Mon–Sat) + list for the day. Desktop: week grid (rows = time, cols = days), entries show subject code, room. Today highlighted with `primary-subtle`. | E per day: "No classes" |
| 8 | **Notices** | "What has the college officially said?" | Filters (category, department) as a compact row; Urgent pinned group; list of NoticeItems (title, issuer, date, category, priority, audience badge). "Past notices" link. Compose button for publishers. | E: "No current notices." Detail: reading width, issuer block, dates (published, updated, expires) |
| 9 | **Community feed** | "What are people discussing?" | Tabs: College · My department. Composer collapsed at top (expands inline). PostItems: author, role badge, audience badge, body, reaction count, comment count, overflow menu (Report; Edit/Delete for author). Infinite "Load more" button (not auto-infinite scroll — keeps footer reachable and keyboard friendly). | E: "No posts yet. Start the first discussion." (with composer focus) |
| 10 | **Post creation & discussion** | Write / discuss | Composer: textarea with character count, visibility selector (College / My department) defaulting to department, explicit audience badge preview, Post button. Post detail: post, comments list chronological, comment box at bottom. | Validation inline; 429 shown as inline error with wait time; hidden-by-moderator view for author with reason |
| 11 | **Department page** | "What's happening in my department?" | Header (name, code, description, department admins), Department notices (current), link to department feed. No metrics. | Archived department → read-only notice |
| 12 | **Events** | — | **Deferred (P1, Phase 11).** Not shown in navigation in MVP. | — |
| 13 | **Issue submission** | Report a problem quickly | Single form: category (radio list with icons), title, location, description; helper text about what happens next. Submit → confirmation with tracking link. | Rate-limit message; idempotent retries |
| 14 | **Issue tracking** | "Is it being fixed?" | Mine list: status badge, title, location, age. Detail: status stepper (Submitted → Acknowledged → In progress → Resolved; Rejected shown as terminal branch), timeline of updates (internal ones visible only to staff, labelled "Internal"), actions available to the viewer only. Coordinator queue: table with filters, oldest first, bulk-free. | Duplicate → banner showing the canonical issue's status and resolution date only (no link to its details, ISSUE-006); 409 version conflict → "Updated by someone else" + reload |
| 15 | **Profile & settings** | Manage account | Sections: Profile (display name), Membership (college, department, kind — read-only), Security (change password, sign out all devices), Appearance (theme). | Password errors inline |
| 16 | **Faculty home / Teaching** | "Which classes need me?" | Today's classes with "Take attendance" action; sections list; section page tabs: Attendance (sessions list + Take attendance), Assessments (list, create, score entry grid, publish), Students (roster: name, roll no.) | Attendance grid: all Present by default, toggle per row, keyboard (↑/↓ move, P/A/E set), sticky Save bar showing counts; leave-page guard on unsaved changes; edit window closed → read-only with explanation |
| 17 | **College administration (Manage)** | Run the college space | Sub-pages: Members (pending queue first with verification flag and roster-vs-account comparison, then directory with filters — admin only), Invites, Roles, Departments, Roster import (template download, upload, row-error table), Academic setup (terms, subjects, sections, timetable, enrollment — dept-scoped for dept admins), Section records (read-only attendance sessions and results per section), Moderation queue, Audit log (table, filters). Tables, not cards. | Destructive actions (end membership, revoke role, withdraw notice) use confirmation dialog stating consequence and requiring reason where PRD requires |
| 18 | **Platform administration** | Operate platform | Separate shell with a neutral header labelled "Platform". Colleges table (name, slug, status, members count), college detail (status actions, admin invites), Users (search by email, suspend), Platform audit log. No access to college content. | Status transitions confirmed with reason |

## 6. Components

Built on shadcn/ui; listed with usage rules.

| Component | Rules |
|---|---|
| **Button** | Variants: `primary` (one per view region), `secondary` (outline), `ghost` (toolbar/overflow), `destructive`. Sizes: `sm` 32 px, `md` 40 px (default), mobile min touch 44 px via padding. Pending state: spinner + label kept ("Saving…"), disabled. Never icon-only without `aria-label`. |
| **Input / Textarea** | Label above, helper below, error replaces helper (`aria-describedby`), `--border-strong` border, `--danger` border + icon on error. Character counter on bounded textareas. |
| **Select / Combobox** | Native-like select for ≤ 7 options; combobox with search for colleges, members. |
| **Dialog** | For confirmation and short forms only; focus trapped; Esc closes unless dirty (then confirm discard). Destructive confirm button names the action ("Withdraw notice"). |
| **Toast** | For confirmations of completed background-safe actions ("Notice published"). Never for errors that need action — those are inline. Auto-dismiss 5 s, pausable, `role="status"`. |
| **NavItem** | Icon + label; current item: `primary` text, `primary-subtle` bg, 3 px `accent` marker at the leading edge; unread count pill. |
| **NoticeItem** | Official treatment (§3.3); priority shown as text badge (Urgent = danger, High = warning, Normal = none); expired shows "Expired". |
| **PostItem** | Social treatment (§3.3); relative time with absolute on hover/title; "edited" tag. |
| **StatusBadge** | Issue: Submitted (neutral), Acknowledged (primary-subtle), In progress (warning-subtle), Resolved (success-subtle), Rejected (danger-subtle). Attendance: Present / Absent / Excused. Always icon + text. |
| **AudienceBadge** | Department / College / (Public reserved). Required on NoticeItem and PostItem. |
| **Table** | For admin lists, attendance, results. Sticky header, sortable columns only where backend supports sort, row actions in trailing overflow menu. On mobile, tables of > 3 columns collapse to stacked rows (label: value). |
| **Tabs** | Section sub-navigation; URL-synced (`?tab=`) so back/refresh work. |
| **Pagination** | Cursor "Load more" for feeds/lists; tables in Manage use "Load more" too (cursor API). Show "Showing N" count of loaded items; no fake total pages. |
| **EmptyState** | Icon (Lucide, 24 px, `text-subtle`), one-line factual title, optional one-line guidance, optional single action only if the viewer can perform it. No illustrations. |
| **Skeleton** | Matches final layout shape (lines for list items, row blocks for tables). Shown after 150 ms delay to avoid flashes. |
| **ErrorState** | Title ("Couldn't load notices"), plain cause when known (offline / server error), Retry button, request ID in small mono text for support. |
| **ConfirmDialog** | Required for destructive or irreversible actions; includes reason textarea when the PRD requires a reason. |

A component is created only when used in ≥ 2 places or when it encapsulates accessibility behavior (`Rules.md` R-3.8).

## 7. Interaction behavior

| Situation | Behavior |
|---|---|
| Loading | Skeleton after 150 ms; keep previous data visible while refetching (TanStack `placeholderData`), subtle top progress bar on refetch only if > 1 s |
| Empty feed / no notices / no attendance | Factual EmptyState per screen table (§5); actions only if permitted |
| Failed API request | Inline ErrorState in the affected region; other regions unaffected; automatic retry ×2 for GET with backoff, none for mutations |
| Unauthorized (403) | In-place message: "You don't have access to this." + link Home. 404 shows "Not found" (same for cross-college). Never reveal whether the object exists |
| Expired session (401) | Faculty/admin sessions expire after 24 h idle or 7 days (AUTH-013), so this is common for them. Modal "Your session ended. Sign in again" with form; unsaved form state kept in memory and restored after sign-in |
| Form validation | Validate on blur and submit; first invalid field focused on submit; summary at top for forms > 5 fields; server 422 mapped to fields |
| Duplicate submission | Submit disabled while pending (MVP). `Idempotency-Key` on create requests arrives with NFR-REL-002 (P1) |
| Network interruption | Offline banner (`navigator.onLine` + failed fetch) at top: "You're offline. Changes won't be saved." Mutations disabled while offline; queued writes are **not** attempted (no offline sync in MVP) |
| Destructive actions | ConfirmDialog; no undo promises unless implemented; soft-deleted user content says "Deleted" for the author |
| Concurrent edit (409) | Inline banner with "Reload" keeping the user's unsaved input visible for copy |
| Mobile navigation | Bottom bar persistent; "More" sheet; back button returns to previous list scroll position (TanStack cache + scroll restoration) |
| Theme switching | Instant, no transition animation on colors; preference persisted; `color-scheme` CSS property set so native controls match |

## 8. Design quality restrictions

Prohibited in all shipped UI:
- Hero sections or oversized welcome banners inside authenticated pages ("Welcome back, Aarav! 🎉").
- Putting every metric in its own card; KPI card grids.
- Radii other than §3.6; arbitrary color, spacing, or font-size values.
- Mixed icon sets or styles; emoji in UI chrome, labels, or empty states.
- Fake activity feeds, fake academic records, fake issue statistics, sample "John Doe" content in production.
- Decorative charts or charts without meaningful, real data.
- Buttons or links that do nothing; "Coming soon" placeholders presented as features.
- Animations beyond §3.10; parallax; auto-playing carousels.
- Gradients, glassmorphism, glows, neon colors.
- Status conveyed by color alone.
- Notices and posts styled the same.

## 9. Verification

- Phase 1: token contrast script verifies every text/background pair listed in §3.1–3.2 (fails CI under 4.5:1 for text, 3:1 for UI boundaries).
- Every UI change: screenshots at 390 px and 1280 px in light and dark (`Rules.md` R-3.11).
- Phase 9: axe checks on all screens, keyboard-only walkthrough, NVDA pass on J1–J5.
