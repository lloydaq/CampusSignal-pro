"""Phase 9d: p95 latency of the hot reads on a large synthetic college (NFR-PERF-001).

Seeds ONE college with 20,000 members and 100,000 posts (plus notices, issues and
notifications) into a DISPOSABLE local database, then times the list and detail endpoints a
student and an admin hit most, in-process through the real app (TestClient: no network, one
client at a time). This is a local baseline for spotting slow queries, not the NFR's
measurement (50 concurrent users on the reference deployment, which waits for Phase 10).

    export PERF_DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/perf_test
    PYTHONPATH=. \\
        uv run python scripts/perf_check.py [--seed] [--requests 200]

All data is synthetic and labelled demo (the college is `is_demo`).
"""

import argparse
import os
import statistics
import sys
import time
from collections.abc import Callable

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, make_url, text

from app.core.config import Settings
from app.core.security import hash_password
from app.main import create_app

MEMBERS = 20_000
POSTS = 100_000
PASSWORD = "perf-check-password-not-secret"  # noqa: S105 (throwaway synthetic accounts)
STUDENT = "perf-student-1@perf.example"
ADMIN = "perf-admin@perf.example"
P95_TARGET_MS = 300


def _disposable(url: str) -> str:
    parsed = make_url(url)
    if parsed.host not in {"localhost", "127.0.0.1", "::1"} or not (parsed.database or "").endswith(
        "_test"
    ):
        raise SystemExit("PERF_DATABASE_URL must be a local *_test database (it is filled up).")
    return url


SEED = """
INSERT INTO colleges (name, slug, timezone, status, is_demo)
VALUES ('Perf Demo College', 'perf-demo', 'Asia/Kolkata', 'ACTIVE', true);

INSERT INTO departments (college_id, code, name)
SELECT c.id, 'D' || g, 'Department ' || g FROM colleges c, generate_series(1, 8) g
WHERE c.slug = 'perf-demo';

-- Members: 1 is the student we sign in as; the last is the college admin (staff).
INSERT INTO users (email, password_hash, display_name, email_verified_at)
SELECT 'perf-student-' || g || '@perf.example', :hash, 'Student ' || g, now()
FROM generate_series(1, :members - 1) g;
INSERT INTO users (email, password_hash, display_name, email_verified_at)
VALUES ('perf-admin@perf.example', :hash, 'Perf Admin', now());

INSERT INTO college_memberships (user_id, college_id, kind, status, department_id)
SELECT u.id, c.id,
       CASE WHEN u.email = 'perf-admin@perf.example' THEN 'STAFF' ELSE 'STUDENT' END,
       'ACTIVE',
       (SELECT d.id FROM departments d WHERE d.college_id = c.id
        ORDER BY d.code OFFSET (abs(hashtext(u.email)) % 8) LIMIT 1)
FROM users u, colleges c
WHERE c.slug = 'perf-demo' AND u.email LIKE 'perf-%@perf.example';

INSERT INTO role_grants (college_id, membership_id, role)
SELECT m.college_id, m.id, 'COLLEGE_ADMIN' FROM college_memberships m
JOIN users u ON u.id = m.user_id WHERE u.email = 'perf-admin@perf.example';

-- Posts: a third to the author's department, the rest to the college, spread over 90 days.
INSERT INTO posts (college_id, author_membership_id, visibility, department_id, body,
                   created_at, updated_at)
SELECT m.college_id, m.id,
       CASE WHEN g % 3 = 0 THEN 'DEPARTMENT' ELSE 'COLLEGE' END,
       CASE WHEN g % 3 = 0 THEN m.department_id END,
       'Synthetic post ' || g,
       now() - (g || ' minutes')::interval * 1.3,
       now() - (g || ' minutes')::interval * 1.3
FROM generate_series(1, :posts) g
JOIN LATERAL (
    SELECT id, college_id, department_id FROM college_memberships
    WHERE college_id = (SELECT id FROM colleges WHERE slug = 'perf-demo')
    ORDER BY id OFFSET (g % (:members - 1)) LIMIT 1
) m ON true;

INSERT INTO notices (college_id, author_membership_id, title, body, category, scope, status,
                     priority, published_at, created_at, updated_at)
SELECT m.college_id, m.id, 'Notice ' || g, 'Synthetic notice ' || g, 'GENERAL', 'COLLEGE',
       'PUBLISHED', 'NORMAL', now() - (g || ' hours')::interval,
       now() - (g || ' hours')::interval, now() - (g || ' hours')::interval
FROM generate_series(1, 2000) g, college_memberships m
JOIN users u ON u.id = m.user_id WHERE u.email = 'perf-admin@perf.example';

INSERT INTO notifications (user_id, college_id, type, subject_type, subject_id, title, created_at)
SELECT u.id, m.college_id, 'NOTICE_PUBLISHED', 'NOTICE', gen_random_uuid(),
       'Important notice ' || g, now() - (g || ' minutes')::interval
FROM generate_series(1, 500) g, users u
JOIN college_memberships m ON m.user_id = u.id WHERE u.email = 'perf-student-1@perf.example';
"""


def seed(url: str) -> None:
    engine = create_engine(url)
    started = time.perf_counter()
    with engine.begin() as conn:
        if conn.execute(text("SELECT 1 FROM colleges WHERE slug = 'perf-demo'")).first():
            print("already seeded")
            return
        params = {"hash": hash_password(PASSWORD), "members": MEMBERS, "posts": POSTS}
        for statement in SEED.split(";\n"):
            if statement.strip():
                conn.execute(text(statement), params)
        conn.execute(text("ANALYZE"))
    print(f"seeded {MEMBERS} members, {POSTS} posts in {time.perf_counter() - started:.0f} s")


def signed_in(app_url: str, email: str) -> TestClient:
    values: dict[str, object] = {
        "app_env": "ci",
        "app_origin": "http://localhost:5173",
        "database_url": app_url,
        "email_backend": "memory",
    }
    settings = Settings(_env_file=None, **values)  # type: ignore[arg-type]
    client = TestClient(create_app(settings), headers={"Origin": "http://localhost:5173"})
    response = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    if response.status_code != 200:
        raise SystemExit(f"sign-in failed for {email}: {response.status_code}")
    return client


def timed(client: TestClient, path: str | Callable[[], str], n: int) -> list[float]:
    samples = []
    for _ in range(n):
        target = path() if callable(path) else path
        started = time.perf_counter()
        response = client.get(target)
        samples.append((time.perf_counter() - started) * 1000)
        if response.status_code != 200:
            raise SystemExit(f"{target}: {response.status_code} {response.text[:200]}")
    return samples


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--seed", action="store_true", help="fill the database first")
    parser.add_argument("--requests", type=int, default=200)
    args = parser.parse_args()
    url = _disposable(os.environ.get("PERF_DATABASE_URL", ""))
    if args.seed:
        seed(url)

    student = signed_in(url, STUDENT)
    admin = signed_in(url, ADMIN)
    deep = student.get("/api/v1/campus/posts?feed=college&limit=25")
    cursor = deep.json()["next_cursor"]
    for _ in range(40):  # 1,000 posts down the feed
        cursor = student.get(f"/api/v1/campus/posts?feed=college&cursor={cursor}").json()[
            "next_cursor"
        ]
    checks: list[tuple[str, TestClient, str]] = [
        ("college feed, first page", student, "/api/v1/campus/posts?feed=college"),
        (
            "college feed, 1,000 posts in",
            student,
            f"/api/v1/campus/posts?feed=college&cursor={cursor}",
        ),
        ("department feed", student, "/api/v1/campus/posts?feed=department"),
        ("notices", student, "/api/v1/campus/notices"),
        ("home (student)", student, "/api/v1/campus/home"),
        ("notifications", student, "/api/v1/me/notifications"),
        ("unread count", student, "/api/v1/me/notifications/unread-count"),
        ("me", student, "/api/v1/me"),
        ("members directory (admin)", admin, "/api/v1/campus/members?status=ACTIVE"),
        ("member search (admin)", admin, "/api/v1/campus/members?query=Student%2019"),
        ("home (admin)", admin, "/api/v1/campus/home"),
        ("moderation queue (admin)", admin, "/api/v1/campus/moderation/reports"),
    ]
    worst = 0.0
    print(f"{'endpoint':32} {'p50 ms':>8} {'p95 ms':>8}   ({args.requests} sequential requests)")
    for label, client, path in checks:
        timed(client, path, 5)  # warm-up
        samples = timed(client, path, args.requests)
        p50 = statistics.median(samples)
        p95 = statistics.quantiles(samples, n=20)[18]
        worst = max(worst, p95)
        flag = "" if p95 < P95_TARGET_MS else "  over 300 ms"
        print(f"{label:32} {p50:8.1f} {p95:8.1f}{flag}")
    print(f"worst p95: {worst:.1f} ms (target < {P95_TARGET_MS} ms, measured in Phase 10")
    print("at 50 concurrent users on the reference deployment)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
