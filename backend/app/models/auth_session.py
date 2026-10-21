import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, LargeBinary, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class AuthSession(Base):
    """Server-side sign-in session (AUTH-004). Only the SHA-256 of the cookie value is stored."""

    __tablename__ = "sessions"
    __table_args__ = (
        CheckConstraint("octet_length(id_hash) = 32", name="id_hash_length"),
        CheckConstraint("octet_length(csrf_secret) = 32", name="csrf_secret_length"),
        CheckConstraint("expires_at > created_at", name="expires_after_created"),
    )

    id_hash: Mapped[bytes] = mapped_column(LargeBinary, primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    csrf_secret: Mapped[bytes] = mapped_column(LargeBinary)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    # Absolute expiry for standard sessions; privileged limits are applied per request.
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
