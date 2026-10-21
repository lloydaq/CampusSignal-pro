"""Identity and platform tables: users, sessions, user_tokens, audit_log, rate_limit_counters.

Phase 2 (PRD AUTH-001…010, ADMIN-005/006; architecture.md §8.2, §10).

- `users.email` is citext (case-insensitive unique, AUTH-001).
- Session IDs and email tokens are stored only as 32-byte SHA-256 digests.
- `audit_log` is append-only: a trigger rejects UPDATE, DELETE and TRUNCATE. The only
  exception is DELETE inside the retention purge, which sets the transaction-local flag
  `campussignal.audit_purge = on` (decided 2026-10-21: trigger now, separate least-
  privilege DB roles at deployment hardening). The trigger function's EXECUTE is revoked
  from PUBLIC (Rules R-2.22). Supabase API roles get no privileges on these tables:
  migration 0002's default-privilege changes apply because they are created by the same
  owning role.
- No percent signs in the SQL, so `alembic upgrade --sql` renders it unchanged (see 0002).

Downgrade drops the tables (and their data) and the trigger function.

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: str | Sequence[str] | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID_PK = sa.text("gen_random_uuid()")
NOW = sa.text("now()")


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), server_default=UUID_PK, nullable=False),
        sa.Column("email", postgresql.CITEXT(), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("display_name", sa.Text(), nullable=False),
        sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.Text(), server_default=sa.text("'ACTIVE'"), nullable=False),
        sa.Column("platform_role", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.CheckConstraint(
            "status IN ('ACTIVE', 'SUSPENDED', 'DEACTIVATED')", name=op.f("ck_users_status")
        ),
        sa.CheckConstraint(
            "platform_role IN ('PLATFORM_ADMIN')", name=op.f("ck_users_platform_role")
        ),
        sa.CheckConstraint(
            "char_length(display_name) BETWEEN 1 AND 60", name=op.f("ck_users_display_name_length")
        ),
        sa.CheckConstraint(
            "char_length(email) BETWEEN 3 AND 254", name=op.f("ck_users_email_length")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
        sa.UniqueConstraint("email", name=op.f("uq_users_email")),
    )

    op.create_table(
        "sessions",
        sa.Column("id_hash", sa.LargeBinary(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("csrf_secret", sa.LargeBinary(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("octet_length(id_hash) = 32", name=op.f("ck_sessions_id_hash_length")),
        sa.CheckConstraint(
            "octet_length(csrf_secret) = 32", name=op.f("ck_sessions_csrf_secret_length")
        ),
        sa.CheckConstraint(
            "expires_at > created_at", name=op.f("ck_sessions_expires_after_created")
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_sessions_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id_hash", name=op.f("pk_sessions")),
    )
    op.create_index(op.f("ix_sessions_user_id"), "sessions", ["user_id"])
    op.create_index(op.f("ix_sessions_expires_at"), "sessions", ["expires_at"])

    op.create_table(
        "user_tokens",
        sa.Column("id", sa.Uuid(), server_default=UUID_PK, nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("purpose", sa.Text(), nullable=False),
        sa.Column("token_hash", sa.LargeBinary(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "purpose IN ('VERIFY_EMAIL', 'RESET_PASSWORD')", name=op.f("ck_user_tokens_purpose")
        ),
        sa.CheckConstraint(
            "octet_length(token_hash) = 32", name=op.f("ck_user_tokens_token_hash_length")
        ),
        sa.CheckConstraint(
            "expires_at > created_at", name=op.f("ck_user_tokens_expires_after_created")
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_user_tokens_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_user_tokens")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_user_tokens_token_hash")),
    )
    op.create_index("ix_user_tokens_user_id_purpose", "user_tokens", ["user_id", "purpose"])
    op.create_index(op.f("ix_user_tokens_expires_at"), "user_tokens", ["expires_at"])

    op.create_table(
        "audit_log",
        sa.Column("id", sa.Uuid(), server_default=UUID_PK, nullable=False),
        sa.Column("college_id", sa.Uuid(), nullable=True),
        sa.Column("actor_user_id", sa.Uuid(), nullable=True),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("target_type", sa.Text(), nullable=True),
        sa.Column("target_id", sa.Text(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.ForeignKeyConstraint(
            ["actor_user_id"], ["users.id"], name=op.f("fk_audit_log_actor_user_id_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_audit_log")),
    )
    op.create_index(op.f("ix_audit_log_created_at"), "audit_log", ["created_at"])
    op.create_index("ix_audit_log_college_id_created_at", "audit_log", ["college_id", "created_at"])
    op.create_index(
        "ix_audit_log_actor_user_id_created_at", "audit_log", ["actor_user_id", "created_at"]
    )
    op.execute(
        """
        CREATE FUNCTION public.audit_log_append_only() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            IF TG_OP = 'DELETE'
               AND current_setting('campussignal.audit_purge', true) = 'on' THEN
                RETURN OLD;
            END IF;
            RAISE EXCEPTION 'audit_log is append-only'
                USING ERRCODE = 'insufficient_privilege', DETAIL = 'blocked: ' || TG_OP;
        END;
        $$
        """
    )
    op.execute("REVOKE EXECUTE ON FUNCTION public.audit_log_append_only() FROM PUBLIC")
    op.execute(
        "CREATE TRIGGER audit_log_no_update_delete BEFORE UPDATE OR DELETE ON public.audit_log "
        "FOR EACH ROW EXECUTE FUNCTION public.audit_log_append_only()"
    )
    op.execute(
        "CREATE TRIGGER audit_log_no_truncate BEFORE TRUNCATE ON public.audit_log "
        "FOR EACH STATEMENT EXECUTE FUNCTION public.audit_log_append_only()"
    )

    op.create_table(
        "rate_limit_counters",
        sa.Column("bucket_key", sa.Text(), nullable=False),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("count", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("bucket_key", "window_start", name=op.f("pk_rate_limit_counters")),
    )
    op.create_index(
        op.f("ix_rate_limit_counters_window_start"), "rate_limit_counters", ["window_start"]
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_rate_limit_counters_window_start"), table_name="rate_limit_counters")
    op.drop_table("rate_limit_counters")

    op.execute("DROP TRIGGER IF EXISTS audit_log_no_truncate ON public.audit_log")
    op.execute("DROP TRIGGER IF EXISTS audit_log_no_update_delete ON public.audit_log")
    op.execute("DROP FUNCTION IF EXISTS public.audit_log_append_only()")
    op.drop_index("ix_audit_log_actor_user_id_created_at", table_name="audit_log")
    op.drop_index("ix_audit_log_college_id_created_at", table_name="audit_log")
    op.drop_index(op.f("ix_audit_log_created_at"), table_name="audit_log")
    op.drop_table("audit_log")

    op.drop_index(op.f("ix_user_tokens_expires_at"), table_name="user_tokens")
    op.drop_index("ix_user_tokens_user_id_purpose", table_name="user_tokens")
    op.drop_table("user_tokens")

    op.drop_index(op.f("ix_sessions_expires_at"), table_name="sessions")
    op.drop_index(op.f("ix_sessions_user_id"), table_name="sessions")
    op.drop_table("sessions")

    op.drop_table("users")
