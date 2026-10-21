from datetime import datetime

from sqlalchemy import DateTime, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class RateLimitCounter(Base):
    """Hits per key per fixed window (architecture.md §10). Purged by the jobs CLI."""

    __tablename__ = "rate_limit_counters"

    bucket_key: Mapped[str] = mapped_column(Text, primary_key=True)
    window_start: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), primary_key=True, index=True
    )
    count: Mapped[int] = mapped_column(Integer)
