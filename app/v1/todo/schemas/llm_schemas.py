"""Schemas shared between the LLM layer and prioritisation.

`PrioritySignals` is exactly what we ask the model for: narrow, bounded signals.
It deliberately does NOT contain a priority value — that one is computed by
`scoring.priority_score`.
"""

from pydantic import BaseModel, Field


class PrioritySignals(BaseModel):
    urgency: int = Field(ge=1, le=5)
    effort: int = Field(ge=1, le=5)
    blocks_others: bool
    reasoning: str = Field(default="", max_length=300)


FALLBACK_SIGNALS = PrioritySignals(
    urgency=3,
    effort=3,
    blocks_others=False,
    reasoning="LLM unavailable, neutral defaults used",
)
