import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    LargeBinary,
    Text,
    Uuid,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class TokenPurpose(StrEnum):
    VERIFY_EMAIL = "VERIFY_EMAIL"
    RESET_PASSWORD = "RESET_PASSWORD"  # noqa: S105  (token purpose name, not a password)


class UserToken(Base):
    """Single-use emailed token (AUTH-003, AUTH-006). Only the SHA-256 digest is stored."""

    __tablename__ = "user_tokens"
    __table_args__ = (
        CheckConstraint("purpose IN ('VERIFY_EMAIL', 'RESET_PASSWORD')", name="purpose"),
        CheckConstraint("octet_length(token_hash) = 32", name="token_hash_length"),
        CheckConstraint("expires_at > created_at", name="expires_after_created"),
        Index("ix_user_tokens_user_id_purpose", "user_id", "purpose"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, server_default=text("gen_random_uuid()")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    purpose: Mapped[str] = mapped_column(Text)
    token_hash: Mapped[bytes] = mapped_column(LargeBinary, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
