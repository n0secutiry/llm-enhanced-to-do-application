"""Deterministic priority scoring.

The LLM only supplies narrow signals (`urgency`, `effort`, `blocks_others`).
The final number is computed here, by plain Python, so the result is
explainable, reproducible and testable without ever calling a model.
"""

import datetime

from app.config import settings
from app.v1.todo.schemas.llm_schemas import PrioritySignals

OVERDUE_BOOST = 3.0
TODAY_BOOST = 2.0
SOON_BOOST = 1.0
SOON_DAYS = 3


def days_left(due_date: datetime.datetime | None, now: datetime.datetime) -> int | None:
    """Full days between `now` and the deadline. Negative means overdue."""
    if due_date is None:
        return None

    due = _as_utc(due_date)
    current = _as_utc(now)

    return (due.date() - current.date()).days


def deadline_boost(days: int | None) -> float:
    """Extra score the deadline alone contributes."""
    if days is None:
        return 0.0

    if days < 0:
        return OVERDUE_BOOST

    if days == 0:
        return TODAY_BOOST

    if days <= SOON_DAYS:
        return SOON_BOOST

    return 0.0


def priority_score(signals: PrioritySignals, days: int | None) -> float:
    """Combine LLM signals and the deadline into a single score.

    score = w1*urgency + w2*(6 - effort) + w3*blocks_others + deadline_boost

    `6 - effort` inverts the effort scale: with everything else equal, a quick
    task should be done before a slow one. Effort is 1..5, so the inverted
    value stays inside the same 1..5 range.
    """
    score = (
        settings.PRIORITY_WEIGHT_URGENCY * signals.urgency
        + settings.PRIORITY_WEIGHT_EFFORT * (6 - signals.effort)
        + settings.PRIORITY_WEIGHT_BLOCKS * int(signals.blocks_others)
        + deadline_boost(days)
    )

    return round(score, 2)


def _as_utc(value: datetime.datetime) -> datetime.datetime:
    """MongoDB returns naive datetimes; treat those as UTC."""
    if value.tzinfo is None:
        return value.replace(tzinfo=datetime.timezone.utc)

    return value.astimezone(datetime.timezone.utc)
