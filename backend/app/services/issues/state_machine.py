"""The campus issue lifecycle as a pure transition table (PRD §9.8.1, architecture.md §7.1).

`transition_problem` says why a change isn't allowed, or None. It knows nothing about the
database: the caller works out which actors the person is for this issue (reporter, assignee,
coordinator, college admin) and the issue's reopen history, and maps the answer to an HTTP error
(INVALID and the reopen limits → 409, NOT_ALLOWED → 403, NOTE_REQUIRED → 422).
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum

from app.models import IssueStatus as S


class Actor(StrEnum):
    REPORTER = "REPORTER"
    ASSIGNEE = "ASSIGNEE"
    COORDINATOR = "COORDINATOR"
    COLLEGE_ADMIN = "COLLEGE_ADMIN"


class TransitionProblem(StrEnum):
    INVALID = "invalid_transition"
    NOT_ALLOWED = "not_allowed"
    NOTE_REQUIRED = "note_required"
    REOPEN_WINDOW_CLOSED = "reopen_window_closed"
    REOPEN_LIMIT = "reopen_limit_reached"


@dataclass(frozen=True)
class Rule:
    actors: frozenset[Actor]
    needs_note: bool


_STAFF = frozenset({Actor.COORDINATOR, Actor.COLLEGE_ADMIN})
_HANDLERS = _STAFF | {Actor.ASSIGNEE}

# College admins may reopen a RESOLVED issue as they may a REJECTED one (owner, 2026-10-25).
TRANSITIONS: dict[tuple[S, S], Rule] = {
    (S.SUBMITTED, S.ACKNOWLEDGED): Rule(_STAFF, needs_note=False),
    (S.ACKNOWLEDGED, S.IN_PROGRESS): Rule(_HANDLERS, needs_note=False),
    # The product never resolves anything by itself: a person and a note, always.
    (S.IN_PROGRESS, S.RESOLVED): Rule(_HANDLERS, needs_note=True),
    (S.SUBMITTED, S.REJECTED): Rule(_STAFF, needs_note=True),
    (S.ACKNOWLEDGED, S.REJECTED): Rule(_STAFF, needs_note=True),
    (S.RESOLVED, S.ACKNOWLEDGED): Rule(_STAFF | {Actor.REPORTER}, needs_note=True),
    (S.REJECTED, S.ACKNOWLEDGED): Rule(_STAFF, needs_note=True),
}

REOPEN_WINDOW = timedelta(days=14)
MAX_REPORTER_REOPENS = 2


def is_reporter_reopen(current: S, target: S, actors: frozenset[Actor]) -> bool:
    """A reopen allowed only because the person reported the issue: it counts against the
    reporter's limit. Someone who is also staff reopens as staff."""
    rule = TRANSITIONS.get((current, target))
    return current == S.RESOLVED and rule is not None and (rule.actors & actors) == {Actor.REPORTER}


def transition_problem(
    current: S,
    target: S,
    actors: frozenset[Actor],
    *,
    note_given: bool,
    resolved_at: datetime | None,
    reporter_reopens: int,
    now: datetime,
) -> TransitionProblem | None:
    rule = TRANSITIONS.get((current, target))
    if rule is None:
        return TransitionProblem.INVALID
    if not rule.actors & actors:
        return TransitionProblem.NOT_ALLOWED
    if rule.needs_note and not note_given:
        return TransitionProblem.NOTE_REQUIRED
    if is_reporter_reopen(current, target, actors):
        if resolved_at is None or now >= resolved_at + REOPEN_WINDOW:
            return TransitionProblem.REOPEN_WINDOW_CLOSED
        if reporter_reopens >= MAX_REPORTER_REOPENS:
            return TransitionProblem.REOPEN_LIMIT
    return None
