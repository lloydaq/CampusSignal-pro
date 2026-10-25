"""Builds the README illustrations: python docs/readme/build_svgs.py (stdlib only).

Each picture is written twice, `<name>-light.svg` and `<name>-dark.svg`, from the colour
tokens in Design.md §3.1/§3.2, and README.md picks one with <picture> and
prefers-color-scheme. Brand rules from Design.md apply here too: deep blue primary, one warm
"signal" accent used sparingly, no gradients or glows. Motion is CSS only and switches off
under prefers-reduced-motion. Edit this file, rerun it, and commit the SVGs it writes.
"""

from pathlib import Path
from xml.sax.saxutils import escape

OUT = Path(__file__).parent

THEMES = {
    "light": {
        "bg": "#F6F7F9", "surface": "#FFFFFF", "sunken": "#EEF1F5", "border": "#DDE2EA",
        "strong": "#868FA0", "text": "#121826", "muted": "#4A5263", "subtle": "#646C7C",
        "primary": "#1D3C8F", "on_primary": "#FFFFFF", "primary_subtle": "#E8EEFB",
        "accent": "#B8460B", "accent_subtle": "#FDEEE4", "accent_fg": "#9A3A09",
        "success": "#15803D", "success_subtle": "#E7F6EC", "success_fg": "#166534",
        "warning_subtle": "#FEF6DC", "warning_fg": "#854D0E",
        "danger": "#B42318", "danger_subtle": "#FDECEA", "danger_fg": "#912018",
    },
    "dark": {
        "bg": "#0F1420", "surface": "#171D2B", "sunken": "#121827", "border": "#2A3245",
        "strong": "#6E788E", "text": "#E7EAF0", "muted": "#A6AFBF", "subtle": "#8A93A5",
        "primary": "#93AEF5", "on_primary": "#0F1420", "primary_subtle": "#1F2A47",
        "accent": "#FF9566", "accent_subtle": "#3A2219", "accent_fg": "#FF9566",
        "success": "#5BD08A", "success_subtle": "#12301F", "success_fg": "#5BD08A",
        "warning_subtle": "#33290F", "warning_fg": "#F5C25B",
        "danger": "#FF8A80", "danger_subtle": "#3A1A1C", "danger_fg": "#FF8A80",
    },
}

HEAD = "'Space Grotesk','Segoe UI','Helvetica Neue',Arial,sans-serif"
BODY = "'IBM Plex Sans','Segoe UI','Helvetica Neue',Arial,sans-serif"
MONO = "'IBM Plex Mono',ui-monospace,SFMono-Regular,Menlo,Consolas,monospace"

MOTION = """
@keyframes rise { from { opacity: 0; transform: translateY(14px); } to { opacity: 1; transform: none; } }
@keyframes fade { from { opacity: 0; } to { opacity: 1; } }
@keyframes ping { 0% { transform: scale(1); opacity: .9; } 80%, 100% { transform: scale(2.6); opacity: 0; } }
@keyframes flow { to { stroke-dashoffset: -24; } }
@keyframes travel { 0% { transform: translateX(0); opacity: 0; } 8% { opacity: 1; } 92% { opacity: 1; } 100% { transform: translateX(var(--d)); opacity: 0; } }
@keyframes blocked { 0% { transform: translateX(0); opacity: 0; } 8% { opacity: 1; } 55%, 70% { transform: translateX(var(--d)); opacity: 1; } 100% { transform: translateX(var(--d)); opacity: 0; } }
@keyframes shake { 0%, 52%, 100% { transform: none; } 56% { transform: translateX(-3px); } 60% { transform: translateX(3px); } 64% { transform: none; } }
.rise { animation: rise .7s cubic-bezier(.2,.7,.2,1) both; }
.fade { animation: fade .9s ease-out both; }
.ping { transform-box: fill-box; transform-origin: center; animation: ping 2.4s cubic-bezier(0,0,.2,1) infinite; }
.flow { stroke-dasharray: 6 6; animation: flow 1.2s linear infinite; }
.travel { animation: travel 3.2s ease-in-out infinite; }
.blocked { animation: blocked 3.2s ease-in-out infinite; }
.shake { transform-box: fill-box; animation: shake 3.2s ease-in-out infinite; }
@media (prefers-reduced-motion: reduce) {
  .rise, .fade, .ping, .flow, .travel, .blocked, .shake { animation: none !important; }
  .ping, .travel, .blocked { display: none; }
}
"""


def t(x: float, y: float, text: str, *, size: int = 16, fill: str, weight: int = 400,
      family: str = BODY, anchor: str = "start", extra: str = "") -> str:
    return (
        f'<text x="{x}" y="{y}" font-family="{family}" font-size="{size}" font-weight="{weight}" '
        f'fill="{fill}" text-anchor="{anchor}" {extra}>{escape(text)}</text>'
    )


def text_width(text: str, size: float, factor: float = 0.56) -> float:
    """A rough width for laying out pills; the fallback fonts vary, so pills get slack."""
    return len(text) * size * factor


def pill(x: float, y: float, label: str, *, fg: str, bg: str, size: int = 13,
         border: str | None = None, mono: bool = False) -> tuple[str, float]:
    width = text_width(label, size, 0.62 if mono else 0.56) + 22
    stroke = f' stroke="{border}"' if border else ""
    svg = (
        f'<rect x="{x}" y="{y}" width="{width:.0f}" height="{size + 13}" rx="4" fill="{bg}"{stroke}/>'
        + t(x + width / 2, y + size + 4, label, size=size, fill=fg, weight=600,
            family=MONO if mono else BODY, anchor="middle")
    )
    return svg, width


def doc(width: int, height: int, title: str, desc: str, body: str, c: dict[str, str]) -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" role="img" aria-labelledby="t d">'
        f"<title id=\"t\">{escape(title)}</title><desc id=\"d\">{escape(desc)}</desc>"
        f"<style>{MOTION}</style>"
        f'<rect width="{width}" height="{height}" rx="12" fill="{c["bg"]}"/>'
        f"{body}</svg>\n"
    )


# --- icons (24 px line icons, Lucide-like, stroke 1.5) -----------------------------------------

ICONS = {
    "bell": '<path d="M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9"/><path d="M10.3 21a1.94 1.94 0 0 0 3.4 0"/>',
    "megaphone": '<path d="m3 11 18-5v12L3 14v-3z"/><path d="M11.6 16.8a3 3 0 1 1-5.8-1.6"/>',
    "users": '<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/>',
    "book": '<path d="M4 19.5v-15A2.5 2.5 0 0 1 6.5 2H20v20H6.5a2.5 2.5 0 0 1 0-5H20"/>',
    "wrench": '<path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"/>',
    "shield": '<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/><path d="m9 12 2 2 4-4"/>',
    "key": '<circle cx="7.5" cy="15.5" r="5.5"/><path d="m21 2-9.6 9.6"/><path d="m15.5 7.5 3 3L22 7l-3-3"/>',
    "school": '<path d="m4 6 8-4 8 4"/><path d="m18 10 4 2v8a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2v-8l4-2"/><path d="M14 22v-4a2 2 0 0 0-4 0v4"/><path d="M18 5v17"/><path d="M6 5v17"/>',
    "lock": '<rect width="18" height="11" x="3" y="11" rx="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/>',
}


def icon(name: str, x: float, y: float, color: str, scale: float = 1.0) -> str:
    return (
        f'<g transform="translate({x} {y}) scale({scale})" fill="none" stroke="{color}" '
        f'stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">{ICONS[name]}</g>'
    )


# --- 1. hero --------------------------------------------------------------------------------------


def hero(c: dict[str, str]) -> str:
    w, h = 1280, 440
    parts = [f'<rect x=".5" y=".5" width="{w - 1}" height="{h - 1}" rx="12" fill="none" stroke="{c["border"]}"/>']
    # Wordmark: the signal dot is a tspan so it always sits right after the name.
    parts.append(
        f'<text class="rise" x="72" y="150" font-family="{HEAD}" font-size="68" font-weight="700" '
        f'letter-spacing="-1.5" fill="{c["text"]}">CampusSignal<tspan fill="{c["accent"]}" '
        f'font-size="68">.</tspan></text>'
    )
    parts.append(
        f'<g class="rise" style="animation-delay:.15s">'
        + t(74, 200, "One platform. Many colleges. One connected campus.", size=24, fill=c["muted"])
        + "</g>"
    )
    parts.append(
        f'<g class="rise" style="animation-delay:.25s">'
        + t(74, 238, "Official notices, department pages, a moderated community, academic records", size=17, fill=c["subtle"])
        + t(74, 262, "and campus issue reporting, with every college kept in its own private space.", size=17, fill=c["subtle"])
        + "</g>"
    )
    x = 74
    chips = []
    for label in ("Notices", "Notifications", "Departments", "Community", "Academic Hub", "Issues"):
        svg, width = pill(x, 300, label, fg=c["primary"], bg=c["primary_subtle"], size=14)
        chips.append(svg)
        x += width + 10
    parts.append(f'<g class="rise" style="animation-delay:.35s">{"".join(chips)}</g>')
    tenant, width = pill(74, 344, "tenant-isolated by design", fg=c["muted"], bg=c["surface"], size=13, border=c["border"], mono=True)
    parts.append(f'<g class="rise" style="animation-delay:.45s">{tenant}</g>')

    # Product preview: a notices panel with a ringing bell.
    px, py, pw, ph = 812, 56, 404, 328
    parts.append(f'<g class="fade" style="animation-delay:.2s">')
    parts.append(f'<rect x="{px}" y="{py}" width="{pw}" height="{ph}" rx="8" fill="{c["surface"]}" stroke="{c["border"]}"/>')
    parts.append(t(px + 24, py + 42, "Notices", size=22, fill=c["text"], weight=700, family=HEAD))
    parts.append(t(px + 24, py + 64, "Northfield Institute", size=13, fill=c["subtle"]))
    bx, by = px + pw - 52, py + 22
    parts.append(icon("bell", bx, by, c["muted"]))
    parts.append(f'<circle class="ping" cx="{bx + 20}" cy="{by + 3}" r="5" fill="none" stroke="{c["accent"]}" stroke-width="2"/>')
    parts.append(f'<circle cx="{bx + 20}" cy="{by + 3}" r="5" fill="{c["accent"]}" stroke="{c["surface"]}" stroke-width="2"/>')
    parts.append(f'<line x1="{px}" y1="{py + 84}" x2="{px + pw}" y2="{py + 84}" stroke="{c["border"]}"/>')
    rows = [
        ("Campus closed tomorrow", [("Urgent", c["danger_fg"], c["danger_subtle"]), ("College", c["primary"], c["primary_subtle"])], "Pinned · Office of the Principal"),
        ("Mid-term timetable", [("Department", c["muted"], c["sunken"])], "Computer Science · 2 h ago"),
        ("Hostel fee deadline", [("Important", c["warning_fg"], c["warning_subtle"]), ("College", c["primary"], c["primary_subtle"])], "Accounts office · yesterday"),
    ]
    for i, (title, badges, meta) in enumerate(rows):
        ry = py + 96 + i * 76
        parts.append(f'<g class="rise" style="animation-delay:{.55 + i * .18:.2f}s">')
        parts.append(f'<rect x="{px + 16}" y="{ry}" width="3" height="60" rx="1.5" fill="{c["primary"]}"/>')
        bxx = px + 30
        for label, fg, bg in badges:
            svg, bw = pill(bxx, ry + 2, label, fg=fg, bg=bg, size=11)
            parts.append(svg)
            bxx += bw + 6
        parts.append(t(px + 30, ry + 40, title, size=17, fill=c["text"], weight=600, family=HEAD))
        parts.append(t(px + 30, ry + 59, meta, size=12, fill=c["subtle"]))
        parts.append("</g>")
    parts.append("</g>")
    return doc(w, h, "CampusSignal", "CampusSignal: one platform for many colleges. A preview of the notices list with an urgent pinned notice and an unread notification.", "".join(parts), c)


# --- 2. features ----------------------------------------------------------------------------------

FEATURES = [
    ("key", "Accounts and sessions", ["Registration, email verification, password", "reset, server-side sessions with CSRF."], "built"),
    ("school", "Colleges, roles, joining", ["Roster or invite to join, approval queue,", "college and department admins."], "built"),
    ("megaphone", "Notices and notifications", ["College and department notices with", "urgent pins. Notification bell next."], "progress"),
    ("wrench", "Campus issue reporting", ["Report a problem, follow its status,", "coordinators work the queue."], "planned"),
    ("users", "Moderated community", ["College and department feeds with", "reactions, reports and moderation."], "planned"),
    ("book", "Academic Hub", ["Timetable, attendance and results,", "visible only to the right people."], "planned"),
]


def features(c: dict[str, str]) -> str:
    w, h = 1280, 520
    status = {
        "built": ("Built", c["success_fg"], c["success_subtle"]),
        "progress": ("In progress", c["warning_fg"], c["warning_subtle"]),
        "planned": ("Planned", c["muted"], c["sunken"]),
    }
    parts = [t(40, 58, "What it does", size=28, fill=c["text"], weight=700, family=HEAD)]
    parts.append(t(40, 86, "Built in vertical slices, each with allow, cross-college and wrong-role tests.", size=16, fill=c["muted"]))
    cw, ch, gap = 386, 186, 21
    for i, (name, title, lines, state) in enumerate(FEATURES):
        col, row = i % 3, i // 3
        x, y = 40 + col * (cw + gap), 118 + row * (ch + gap)
        parts.append(f'<g class="rise" style="animation-delay:{.08 * i:.2f}s">')
        parts.append(f'<rect x="{x}" y="{y}" width="{cw}" height="{ch}" rx="8" fill="{c["surface"]}" stroke="{c["border"]}"/>')
        parts.append(f'<rect x="{x + 22}" y="{y + 22}" width="44" height="44" rx="8" fill="{c["primary_subtle"]}"/>')
        parts.append(icon(name, x + 32, y + 32, c["primary"]))
        label, fg, bg = status[state]
        svg, pw = pill(0, 0, label, fg=fg, bg=bg, size=12)
        parts.append(f'<g transform="translate({x + cw - 22 - pw:.0f} {y + 30})">{svg}</g>')
        if state == "progress":
            parts.append(f'<circle class="ping" cx="{x + cw - 22 - pw - 12:.0f}" cy="{y + 42}" r="4" fill="none" stroke="{c["accent"]}" stroke-width="2"/>')
            parts.append(f'<circle cx="{x + cw - 22 - pw - 12:.0f}" cy="{y + 42}" r="4" fill="{c["accent"]}"/>')
        parts.append(t(x + 22, y + 104, title, size=20, fill=c["text"], weight=700, family=HEAD))
        for j, line in enumerate(lines):
            parts.append(t(x + 22, y + 134 + j * 22, line, size=15, fill=c["muted"]))
        parts.append("</g>")
    return doc(w, h, "Features", "Six areas of CampusSignal and their status: accounts and colleges are built, notices and notifications are in progress, issues, community and the Academic Hub are planned.", "".join(parts), c)


# --- 3. tenant isolation --------------------------------------------------------------------------


def isolation(c: dict[str, str]) -> str:
    w, h = 1280, 500
    parts = [t(40, 58, "Every request belongs to one college", size=28, fill=c["text"], weight=700, family=HEAD)]
    parts.append(t(40, 86, "The college comes from your ACTIVE membership in the database, never from the request.", size=16, fill=c["muted"]))

    # The request pipeline.
    steps = [
        ("Signed-in user", "session cookie", "users"),
        ("Active membership", "looked up server-side", "key"),
        ("college_id", "Northfield Institute", "school"),
    ]
    for i, (title, sub, ic) in enumerate(steps):
        x, y = 40, 132 + i * 112
        parts.append(f'<g class="rise" style="animation-delay:{.1 * i:.1f}s">')
        parts.append(f'<rect x="{x}" y="{y}" width="300" height="84" rx="8" fill="{c["surface"]}" stroke="{c["border"]}"/>')
        parts.append(icon(ic, x + 20, y + 30, c["primary"]))
        parts.append(t(x + 60, y + 38, title, size=18, fill=c["text"], weight=600, family=MONO if title == "college_id" else HEAD))
        parts.append(t(x + 60, y + 62, sub, size=14, fill=c["muted"]))
        parts.append("</g>")
        if i < 2:
            parts.append(f'<line class="flow" x1="{x + 150}" y1="{y + 84}" x2="{x + 150}" y2="{y + 112}" stroke="{c["strong"]}" stroke-width="2"/>')

    # Two colleges.
    def college(x: float, y: float, name: str, items: list[str], active: bool) -> str:
        stroke = c["primary"] if active else c["border"]
        fill = c["surface"] if active else c["sunken"]
        text = c["text"] if active else c["subtle"]
        out = [f'<rect x="{x}" y="{y}" width="380" height="150" rx="8" fill="{fill}" stroke="{stroke}" stroke-width="{2 if active else 1}"/>']
        out.append(icon("school" if active else "lock", x + 20, y + 22, c["primary"] if active else c["subtle"]))
        out.append(t(x + 56, y + 40, name, size=19, fill=text, weight=700, family=HEAD))
        for k, item in enumerate(items):
            out.append(f'<rect x="{x + 20}" y="{y + 64 + k * 26}" width="8" height="8" rx="2" fill="{c["primary"] if active else c["strong"]}"/>')
            out.append(t(x + 38, y + 72 + k * 26, item, size=14, fill=c["muted"] if active else c["subtle"]))
        return "".join(out)

    parts.append(f'<g class="fade" style="animation-delay:.3s">{college(860, 120, "Northfield Institute", ["notices, members, roster", "departments and audit log", "only Northfield's people"], True)}</g>')
    parts.append(f'<g class="fade" style="animation-delay:.4s">{college(860, 306, "Riverside College", ["a different college", "its rows carry its own college_id", "composite keys keep them apart"], False)}</g>')

    # Allowed path.
    sx, sy = 340, 386
    parts.append(f'<path d="M{sx} {sy} H520 V195 H860" fill="none" stroke="{c["success"]}" stroke-width="2.5"/>')
    parts.append(f'<g transform="translate(560 175)">{pill(0, 0, "200 · your college", fg=c["success_fg"], bg=c["success_subtle"], size=13)[0]}</g>')
    parts.append(f'<circle class="travel" style="--d:330px" cx="525" cy="195" r="6" fill="{c["success"]}"/>')
    # Blocked path.
    parts.append(f'<path d="M520 386 H730" fill="none" stroke="{c["danger"]}" stroke-width="2.5" stroke-dasharray="8 6"/>')
    parts.append(f'<circle class="blocked" style="--d:195px" cx="525" cy="386" r="6" fill="{c["danger"]}"/>')
    parts.append(
        f'<g class="shake"><rect x="738" y="364" width="44" height="44" rx="8" fill="{c["danger_subtle"]}" stroke="{c["danger"]}"/>'
        f'<path d="M750 376 l20 20 M770 376 l-20 20" stroke="{c["danger"]}" stroke-width="3" stroke-linecap="round"/></g>'
    )
    parts.append(f'<g transform="translate(560 410)">{pill(0, 0, "404 · same as not found", fg=c["danger_fg"], bg=c["danger_subtle"], size=13)[0]}</g>')
    return doc(w, h, "Tenant isolation", "How a request is scoped: the user's session leads to their active membership, which fixes the college. Requests reach their own college (200); anything in another college answers 404, exactly like something that doesn't exist.", "".join(parts), c)


# --- 4. architecture ------------------------------------------------------------------------------


def architecture(c: dict[str, str]) -> str:
    w, h = 1280, 470
    parts = [t(40, 58, "How it fits together", size=28, fill=c["text"], weight=700, family=HEAD)]
    parts.append(t(40, 86, "A modular monolith on one origin: no microservices, no queues, no WebSockets.", size=16, fill=c["muted"]))

    def box(x: float, y: float, bw: float, bh: float, title: str, lines: list[str], *, strong: bool = False, mono: bool = False) -> str:
        out = [f'<rect x="{x}" y="{y}" width="{bw}" height="{bh}" rx="8" fill="{c["surface"]}" stroke="{c["primary"] if strong else c["border"]}" stroke-width="{2 if strong else 1}"/>']
        out.append(t(x + 18, y + 32, title, size=18, fill=c["text"], weight=700, family=HEAD))
        for k, line in enumerate(lines):
            out.append(t(x + 18, y + 56 + k * 21, line, size=13, fill=c["muted"], family=MONO if mono else BODY))
        return "".join(out)

    parts.append(f'<g class="rise">{box(40, 140, 220, 120, "Browser", ["React SPA", "TanStack Query", "cookies, no tokens"])}</g>')
    parts.append(f'<g class="rise" style="animation-delay:.1s">{box(320, 140, 200, 120, "Caddy", ["TLS, static files", "/api → backend", "security headers"])}</g>')
    # FastAPI layers.
    parts.append(f'<g class="rise" style="animation-delay:.2s">')
    parts.append(f'<rect x="580" y="116" width="360" height="300" rx="8" fill="{c["surface"]}" stroke="{c["primary"]}" stroke-width="2"/>')
    parts.append(t(598, 148, "FastAPI backend", size=18, fill=c["text"], weight=700, family=HEAD))
    layers = [
        ("api/v1", "routers: parse, call, respond"),
        ("policies", "every permission decision"),
        ("services", "business rules, transactions"),
        ("repositories", "queries scoped by college_id"),
    ]
    for k, (name, desc) in enumerate(layers):
        ly = 166 + k * 58
        accent = name == "policies"
        parts.append(f'<rect x="598" y="{ly}" width="324" height="46" rx="6" fill="{c["primary_subtle"] if accent else c["sunken"]}"/>')
        parts.append(t(614, ly + 21, name, size=14, fill=c["primary"] if accent else c["text"], weight=600, family=MONO))
        parts.append(t(614, ly + 38, desc, size=12, fill=c["muted"]))
    parts.append("</g>")
    parts.append(f'<g class="rise" style="animation-delay:.3s">{box(1000, 140, 240, 120, "PostgreSQL 17", ["composite (college_id, id)", "foreign keys, row locks", "append-only audit log"], strong=False)}</g>')
    parts.append(f'<g class="rise" style="animation-delay:.4s">{box(1000, 300, 240, 116, "Jobs CLI", ["hourly retention purges", "sessions, tokens,", "notifications, audit"])}</g>')
    parts.append(f'<g class="rise" style="animation-delay:.5s">{box(320, 300, 200, 116, "Mailer", ["SMTP after commit", "Mailpit locally", "tokens never logged"])}</g>')

    def arrow(x1: float, y1: float, x2: float, y2: float) -> str:
        return (
            f'<line class="flow" x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{c["strong"]}" stroke-width="2"/>'
        )

    parts.append(arrow(260, 200, 320, 200))
    parts.append(arrow(520, 200, 580, 200))
    parts.append(arrow(940, 200, 1000, 200))
    parts.append(arrow(1120, 300, 1120, 260))
    parts.append(arrow(580, 358, 520, 358))
    return doc(w, h, "Architecture", "Browser to Caddy to the FastAPI backend (routers, policies, services, repositories) to PostgreSQL 17, with a mailer and an hourly jobs CLI.", "".join(parts), c)


# --- 5. roadmap -----------------------------------------------------------------------------------

PHASES = [
    ("0", "Setup", "done"), ("1", "Foundation", "done"), ("2", "Identity", "done"),
    ("3", "Colleges", "done"), ("4", "Notices", "now"), ("5", "Issues", "next"),
    ("6", "Community", "next"), ("7", "Academic", "next"), ("8", "Home", "next"),
    ("9", "Hardening", "next"), ("10", "Launch", "next"), ("11", "Post-MVP", "next"),
]
RELEASES = {"4": "Release α", "6": "Release β", "10": "MVP"}


def roadmap(c: dict[str, str]) -> str:
    w, h = 1280, 290
    parts = [t(40, 58, "Roadmap", size=28, fill=c["text"], weight=700, family=HEAD)]
    parts.append(t(40, 86, "Phase 4 in progress: notices are built; the notification bell is next.", size=16, fill=c["muted"]))
    left, right, y = 90, 1190, 170
    step = (right - left) / (len(PHASES) - 1)
    done_x = left + step * 4
    parts.append(f'<line x1="{left}" y1="{y}" x2="{right}" y2="{y}" stroke="{c["border"]}" stroke-width="4" stroke-linecap="round"/>')
    parts.append(f'<line x1="{left}" y1="{y}" x2="{done_x}" y2="{y}" stroke="{c["primary"]}" stroke-width="4" stroke-linecap="round"/>')
    for i, (num, name, state) in enumerate(PHASES):
        x = left + step * i
        parts.append(f'<g class="rise" style="animation-delay:{.05 * i:.2f}s">')
        if state == "done":
            parts.append(f'<circle cx="{x}" cy="{y}" r="15" fill="{c["primary"]}"/>')
            parts.append(f'<path d="M{x - 6} {y} l4 4 l8 -8" fill="none" stroke="{c["on_primary"]}" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/>')
        elif state == "now":
            parts.append(f'<circle class="ping" cx="{x}" cy="{y}" r="15" fill="none" stroke="{c["accent"]}" stroke-width="2"/>')
            parts.append(f'<circle cx="{x}" cy="{y}" r="15" fill="{c["surface"]}" stroke="{c["accent"]}" stroke-width="3"/>')
            parts.append(f'<circle cx="{x}" cy="{y}" r="5" fill="{c["accent"]}"/>')
        else:
            parts.append(f'<circle cx="{x}" cy="{y}" r="15" fill="{c["surface"]}" stroke="{c["strong"]}" stroke-width="2"/>')
        parts.append(t(x, y + 44, num, size=13, fill=c["subtle"], family=MONO, anchor="middle"))
        parts.append(t(x, y + 64, name, size=14, fill=c["text"] if state != "next" else c["muted"], weight=600 if state != "next" else 400, anchor="middle"))
        if num in RELEASES:
            svg, pw = pill(0, 0, RELEASES[num], fg=c["primary"], bg=c["primary_subtle"], size=11)
            parts.append(f'<g transform="translate({x - pw / 2:.0f} {y - 52})">{svg}</g>')
        parts.append("</g>")
    return doc(w, h, "Roadmap", "Phases 0 to 3 are done, phase 4 (notices and notifications) is in progress, phases 5 to 11 are next. Release alpha after phase 4, beta after phase 6, MVP after phase 10.", "".join(parts), c)


PICTURES = {
    "hero": hero,
    "features": features,
    "isolation": isolation,
    "architecture": architecture,
    "roadmap": roadmap,
}


def main() -> None:
    for name, build in PICTURES.items():
        for theme, colours in THEMES.items():
            (OUT / f"{name}-{theme}.svg").write_text(build(colours), encoding="utf-8")
            print(f"wrote {name}-{theme}.svg")


if __name__ == "__main__":
    main()
