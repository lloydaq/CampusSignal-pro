"""Community: posts, comments and reactions (COMMUNITY-001…005).

Three tables. A post is visible to its college or to one department (named exactly when the
visibility is DEPARTMENT); its author, department, comments and reactions are in the same
college (composite foreign keys). Posts and comments are soft-deleted (`deleted_at`) and may be
hidden by moderators (`status`). One reaction per member per post is a unique constraint;
reactions go with their post.

Downgrade drops all three tables (and with them every post, comment and reaction).

Revision ID: 0010
Revises: 0009
Create Date: 2026-11-03
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010"
down_revision: str | Sequence[str] | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "posts",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("college_id", sa.Uuid(), nullable=False),
        sa.Column("author_membership_id", sa.Uuid(), nullable=False),
        sa.Column("visibility", sa.Text(), nullable=False),
        sa.Column("department_id", sa.Uuid(), nullable=True),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), server_default=sa.text("'VISIBLE'"), nullable=False),
        sa.Column("edited_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "(visibility = 'DEPARTMENT') = (department_id IS NOT NULL)",
            name=op.f("ck_posts_department_scope"),
        ),
        sa.CheckConstraint("status IN ('VISIBLE', 'HIDDEN')", name=op.f("ck_posts_status")),
        sa.CheckConstraint(
            "visibility IN ('COLLEGE', 'DEPARTMENT')", name=op.f("ck_posts_visibility")
        ),
        sa.CheckConstraint(
            "char_length(body) BETWEEN 1 AND 5000", name=op.f("ck_posts_body_length")
        ),
        sa.ForeignKeyConstraint(
            ["college_id", "author_membership_id"],
            ["college_memberships.college_id", "college_memberships.id"],
            name="fk_posts_author_membership",
        ),
        sa.ForeignKeyConstraint(
            ["college_id", "department_id"],
            ["departments.college_id", "departments.id"],
            name="fk_posts_department",
        ),
        sa.ForeignKeyConstraint(
            ["college_id"], ["colleges.id"], name=op.f("fk_posts_college_id_colleges")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_posts")),
        sa.UniqueConstraint("college_id", "id", name=op.f("uq_posts_college_id_id")),
    )
    op.create_index(
        "ix_posts_author_created",
        "posts",
        ["college_id", "author_membership_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_posts_feed",
        "posts",
        [
            "college_id",
            "visibility",
            "department_id",
            sa.literal_column("created_at DESC"),
            sa.literal_column("id DESC"),
        ],
        unique=False,
    )
    op.create_table(
        "comments",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("college_id", sa.Uuid(), nullable=False),
        sa.Column("post_id", sa.Uuid(), nullable=False),
        sa.Column("author_membership_id", sa.Uuid(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), server_default=sa.text("'VISIBLE'"), nullable=False),
        sa.Column("edited_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("status IN ('VISIBLE', 'HIDDEN')", name=op.f("ck_comments_status")),
        sa.CheckConstraint(
            "char_length(body) BETWEEN 1 AND 2000", name=op.f("ck_comments_body_length")
        ),
        sa.ForeignKeyConstraint(
            ["college_id", "author_membership_id"],
            ["college_memberships.college_id", "college_memberships.id"],
            name="fk_comments_author_membership",
        ),
        sa.ForeignKeyConstraint(
            ["college_id", "post_id"], ["posts.college_id", "posts.id"], name="fk_comments_post"
        ),
        sa.ForeignKeyConstraint(
            ["college_id"], ["colleges.id"], name=op.f("fk_comments_college_id_colleges")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_comments")),
        sa.UniqueConstraint("college_id", "id", name=op.f("uq_comments_college_id_id")),
    )
    op.create_index(
        "ix_comments_author_created",
        "comments",
        ["college_id", "author_membership_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_comments_post_created",
        "comments",
        ["college_id", "post_id", "created_at", "id"],
        unique=False,
    )
    op.create_table(
        "reactions",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("college_id", sa.Uuid(), nullable=False),
        sa.Column("post_id", sa.Uuid(), nullable=False),
        sa.Column("membership_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["college_id", "membership_id"],
            ["college_memberships.college_id", "college_memberships.id"],
            name="fk_reactions_membership",
        ),
        sa.ForeignKeyConstraint(
            ["college_id", "post_id"],
            ["posts.college_id", "posts.id"],
            name="fk_reactions_post",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["college_id"], ["colleges.id"], name=op.f("fk_reactions_college_id_colleges")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_reactions")),
        sa.UniqueConstraint("post_id", "membership_id", name="uq_reactions_post_member"),
    )


def downgrade() -> None:
    op.drop_table("reactions")
    op.drop_index("ix_comments_post_created", table_name="comments")
    op.drop_index("ix_comments_author_created", table_name="comments")
    op.drop_table("comments")
    op.drop_index("ix_posts_feed", table_name="posts")
    op.drop_index("ix_posts_author_created", table_name="posts")
    op.drop_table("posts")
