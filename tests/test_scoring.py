"""Scoring tests: pure functions, no MongoDB and no LLM involved."""

import datetime

from app.v1.todo.schemas.llm_schemas import FALLBACK_SIGNALS, PrioritySignals
from app.v1.todo.scoring import days_left, deadline_boost, priority_score

NOW = datetime.datetime(2026, 6, 15, 12, 0, tzinfo=datetime.timezone.utc)


def signals(urgency=3, effort=3, blocks_others=False):
    return PrioritySignals(
        urgency=urgency,
        effort=effort,
        blocks_others=blocks_others,
        reasoning="test",
    )


def test_days_left_handles_past_today_future_and_missing_deadline():
    assert days_left(NOW - datetime.timedelta(days=2), NOW) == -2
    assert days_left(NOW, NOW) == 0
    assert days_left(NOW + datetime.timedelta(days=5), NOW) == 5
    assert days_left(None, NOW) is None


def test_days_left_treats_naive_datetime_as_utc():
    """MongoDB returns naive datetimes, they must not break the maths."""
    naive_due = datetime.datetime(2026, 6, 18, 9, 0)

    assert days_left(naive_due, NOW) == 3


def test_deadline_boost_follows_the_rules():
    assert deadline_boost(-1) == 3.0
    assert deadline_boost(0) == 2.0
    assert deadline_boost(1) == 1.0
    assert deadline_boost(3) == 1.0
    assert deadline_boost(4) == 0.0
    assert deadline_boost(None) == 0.0


def test_higher_urgency_scores_higher():
    low = priority_score(signals(urgency=1), None)
    high = priority_score(signals(urgency=5), None)

    assert high > low


def test_quick_task_beats_slow_one_when_everything_else_is_equal():
    quick = priority_score(signals(effort=1), None)
    slow = priority_score(signals(effort=5), None)

    assert quick > slow


def test_blocking_other_work_adds_score():
    blocking = priority_score(signals(blocks_others=True), None)
    plain = priority_score(signals(blocks_others=False), None)

    assert blocking > plain


def test_overdue_task_beats_a_task_due_next_month():
    overdue = priority_score(
        signals(), days_left(NOW - datetime.timedelta(days=1), NOW)
    )
    later = priority_score(signals(), days_left(NOW + datetime.timedelta(days=30), NOW))

    assert overdue - later == 3.0


def test_note_without_deadline_gets_no_boost():
    with_deadline = priority_score(signals(), 0)
    without_deadline = priority_score(signals(), None)

    assert with_deadline - without_deadline == 2.0


def test_score_is_deterministic():
    first = priority_score(signals(urgency=4, effort=2, blocks_others=True), 1)
    second = priority_score(signals(urgency=4, effort=2, blocks_others=True), 1)

    assert first == second


def test_fallback_signals_still_produce_a_usable_score():
    score = priority_score(FALLBACK_SIGNALS, days_left(NOW, NOW))

    assert score > 0


def test_spearman_detects_perfect_agreement_and_reversal():
    from scripts.prompt_ab import spearman

    assert spearman([1, 2, 3, 4], [10, 20, 30, 40]) == 1.0
    assert spearman([1, 2, 3, 4], [40, 30, 20, 10]) == -1.0
    assert abs(spearman([1, 2, 3, 4], [10, 10, 10, 10])) == 0.0


def test_spearman_handles_ties():
    from scripts.prompt_ab import spearman

    assert 0 < spearman([1, 2, 3, 4], [10, 20, 20, 30]) < 1.0
