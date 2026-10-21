"""Audit log writer (PRD ADMIN-006, Rules R-2.13).

Entries are added to the caller's session so they commit or roll back together with the
action they describe. The table is append-only (trigger in migration 0003). Metadata must
never carry secrets or academic values: keys that look sensitive are refused outright,
so the mistake surfaces in tests instead of in the log.
"""

import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.core.logging import is_sensitive_key
from app.models.audit import AuditLog


def _check_metadata(value: Any, path: str = "metadata") -> None:
    if isinstance(value, dict):
        for key, inner in value.items():
            if is_sensitive_key(str(key)):
                raise ValueError(f"Audit {path} must not contain sensitive key {key!r}")
            _check_metadata(inner, f"{path}.{key}")
    elif isinstance(value, list | tuple):
        for item in value:
            _check_metadata(item, path)


def record_audit(
    session: Session,
    *,
    action: str,
    actor_user_id: uuid.UUID | None = None,
    college_id: uuid.UUID | None = None,
    target_type: str | None = None,
    target_id: str | None = None,
    reason: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> AuditLog:
    data = metadata or {}
    _check_metadata(data)
    entry = AuditLog(
        action=action,
        actor_user_id=actor_user_id,
        college_id=college_id,
        target_type=target_type,
        target_id=target_id,
        reason=reason,
        data=data,
    )
    session.add(entry)
    return entry
