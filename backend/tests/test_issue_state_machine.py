"""The issue lifecycle (PRD §9.8.1, ISSUE-002), checked exhaustively: every from, to and actor.

EXPECTED is written out from the PRD table independently of the implementation, so a change to
either has to be made on purpose in both. Owner decision 2026-10-25: college admins may reopen a
RESOLVED issue too, as they may a REJECTED one.
"""

from datetime import UTC, datetime, timedelta
from itertools import product

import pytest

from app.models import IssueStatus as S
from app.services.issues.state_machine import (
    MAX_REPORTER_REOPENS,
    REOPEN_WINDOW,
    Actor,
    TransitionProblem,
    is_reporter_reopen,
    transition_problem,
)

A = Actor
STAFF = frozenset({A.COORDINATOR, A.COLLEGE_ADMIN})
HANDLERS = STAFF | {A.ASSIGNEE}

# (from, to) -> (who may, note or reason required)
EXPECTED: dict[tuple[S, S], tuple[frozenset[Actor], bool]] = {
    (S.SUBMITTED, S.ACKNOWLEDGED): (STAFF, False),
    (S.ACKNOWLEDGED, S.IN_PROGRESS): (HANDLERS, False),
    (S.IN_PROGRESS, S.RESOLVED): (HANDLERS, True),
    (S.SUBMITTED, S.REJECTED): (STAFF, True),
    (S.ACKNOWLEDGED, S.REJECTED): (STAFF, True),
    (S.RESOLVED, S.ACKNOWLEDGED): (STAFF | {A.REPORTER}, True),
    (S.REJECTED, S.ACKNOWLEDGED): (STAFF, True),
}

NOW = datetime(2026, 10, 25, 9, 0, tzinfo=UTC)


def check(
    current: S,
    target: S,
    actors: frozenset[Actor],
    *,
    note: bool = True,
    resolved_at: datetime | None = NOW,
    reopens: int = 0,
) -> TransitionProblem | None:
    return transition_problem(
        current,
        target,
        actors,
        note_given=note,
        resolved_at=resolved_at,
        reporter_reopens=reopens,
        now=NOW,
    )


@pytest.mark.parametrize(("current", "target", "actor"), list(product(S, S, Actor)))
def test_every_transition_for_every_actor(current: S, target: S, actor: Actor) -> None:
    expected = EXPECTED.get((current, target))
    problem = check(current, target, frozenset({actor}))
    if expected is None:
        assert problem is TransitionProblem.INVALID
    elif actor in expected[0]:
        assert problem is None
    else:
        assert problem is TransitionProblem.NOT_ALLOWED


@pytest.mark.parametrize(("current", "target"), list(product(S, S)))
def test_nobody_without_a_role_changes_anything(current: S, target: S) -> None:
    problem = check(current, target, frozenset())
    assert problem in (TransitionProblem.INVALID, TransitionProblem.NOT_ALLOWED)


@pytest.mark.parametrize(("pair", "rule"), EXPECTED.items())
def test_notes_and_reasons_are_required_where_the_prd_says(
    pair: tuple[S, S], rule: tuple[frozenset[Actor], bool]
) -> None:
    actors, needs_note = rule
    problem = check(*pair, actors, note=False)
    assert problem is (TransitionProblem.NOTE_REQUIRED if needs_note else None)


def test_the_role_is_checked_before_the_note() -> None:
    # A reporter can't reject: they learn that, not that a reason is missing.
    assert check(S.SUBMITTED, S.REJECTED, frozenset({A.REPORTER}), note=False) is (
        TransitionProblem.NOT_ALLOWED
    )


def test_an_assignee_cannot_skip_acknowledgement() -> None:  # US-09
    assert check(S.SUBMITTED, S.IN_PROGRESS, frozenset({A.ASSIGNEE})) is TransitionProblem.INVALID


def test_staying_put_is_not_a_transition() -> None:
    for status in S:
        assert check(status, status, STAFF) is TransitionProblem.INVALID


class TestReporterReopens:
    reporter = frozenset({A.REPORTER})

    def test_within_the_window_and_under_the_limit(self) -> None:
        resolved = NOW - REOPEN_WINDOW + timedelta(minutes=1)
        assert check(S.RESOLVED, S.ACKNOWLEDGED, self.reporter, resolved_at=resolved) is None

    def test_after_the_window(self) -> None:
        resolved = NOW - REOPEN_WINDOW
        assert check(S.RESOLVED, S.ACKNOWLEDGED, self.reporter, resolved_at=resolved) is (
            TransitionProblem.REOPEN_WINDOW_CLOSED
        )

    def test_at_the_limit(self) -> None:
        assert (
            check(S.RESOLVED, S.ACKNOWLEDGED, self.reporter, reopens=MAX_REPORTER_REOPENS)
            is TransitionProblem.REOPEN_LIMIT
        )

    @pytest.mark.parametrize("staff", [A.COORDINATOR, A.COLLEGE_ADMIN])
    def test_staff_reopen_any_time_however_often(self, staff: Actor) -> None:
        long_ago = NOW - timedelta(days=400)
        assert (
            check(
                S.RESOLVED,
                S.ACKNOWLEDGED,
                frozenset({staff}),
                resolved_at=long_ago,
                reopens=MAX_REPORTER_REOPENS,
            )
            is None
        )

    def test_a_reporter_who_is_also_staff_reopens_as_staff(self) -> None:
        both = frozenset({A.REPORTER, A.COORDINATOR})
        assert not is_reporter_reopen(S.RESOLVED, S.ACKNOWLEDGED, both)
        assert check(S.RESOLVED, S.ACKNOWLEDGED, both, reopens=MAX_REPORTER_REOPENS) is None

    def test_only_a_reporter_reopen_counts_against_the_limit(self) -> None:
        assert is_reporter_reopen(S.RESOLVED, S.ACKNOWLEDGED, self.reporter)
        assert not is_reporter_reopen(S.RESOLVED, S.ACKNOWLEDGED, frozenset({A.COORDINATOR}))
        assert not is_reporter_reopen(S.REJECTED, S.ACKNOWLEDGED, frozenset({A.COLLEGE_ADMIN}))


def test_the_limits_match_the_prd() -> None:
    assert timedelta(days=14) == REOPEN_WINDOW
    assert MAX_REPORTER_REOPENS == 2
