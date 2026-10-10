"""Deterministic prompt augmentation.

Everything the model cannot know on its own — today's date, the real number of
days left, how many tasks are currently open — is computed here and injected
into the prompt as plain facts. No LLM call happens in this module, which keeps
it trivially testable.
"""

import datetime

from app.v1.todo.models import TodoModel
from app.v1.todo.scoring import days_left


def build_priority_context(
    todo: TodoModel,
    open_todos: int,
    now: datetime.datetime,
) -> dict[str, str]:
    remaining = days_left(todo.due_date, now)

    return {
        "today": now.date().isoformat(),
        "due_date": todo.due_date.date().isoformat() if todo.due_date else "none",
        "days_left": "unknown" if remaining is None else str(remaining),
        "status": str(todo.status),
        "tags": ", ".join(todo.tags) if todo.tags else "none",
        "open_todos": str(open_todos),
        "content": todo.content,
    }


def render_prompt(template: str, context: dict[str, str]) -> str:
    """Replace `{{ key }}` placeholders with context values."""
    prompt = template

    for key, value in context.items():
        prompt = prompt.replace("{{ " + key + " }}", value)

    return prompt
