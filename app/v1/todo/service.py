"""Business logic for todos.

Decisions that belong to the application — who owns a title, when to call the
LLM, how a priority is computed — live here. The repository only stores data,
the router only speaks HTTP.
"""

import datetime

from fastapi import Depends
from loguru import logger

from app.config import settings
from app.database.mongo_db import get_todo_repository
from app.v1.llm.ollama import get_llm_service
from app.v1.llm.service import LLMService
from app.v1.todo.context import build_priority_context, render_prompt
from app.v1.todo.models import TitleSourceType, TodoModel
from app.v1.todo.repository import TodoRepository
from app.v1.todo.schemas.request_schemas import TodoCreateRequest, TodoUpdateRequest
from app.v1.todo.scoring import days_left, deadline_boost, priority_score

FALLBACK_TITLE_LENGTH = 40
NEXT_TODOS_LIMIT = 3

# Fields a client may explicitly set to null
NULLABLE_FIELDS = {"due_date"}


def get_todo_service(
    todo_repo: TodoRepository = Depends(get_todo_repository),
    llm_service: LLMService = Depends(get_llm_service),
):
    return TodoService(
        todo_repo=todo_repo,
        llm_service=llm_service,
    )


class TodoService:
    def __init__(self, todo_repo, llm_service):
        self.todo_repo = todo_repo
        self.llm_service = llm_service

    async def create(self, data: TodoCreateRequest) -> TodoModel:
        document = data.model_dump()

        if document["title"] is not None:
            document["title_source"] = TitleSourceType.user
        else:
            document["title"] = self.__fallback_title(document["content"])
            document["title_source"] = TitleSourceType.fallback

        return await self.todo_repo.create(document)

    async def update(self, todo_id, data: TodoUpdateRequest) -> TodoModel | None:
        changes = data.model_dump(exclude_unset=True)

        # An explicit null is only meaningful for `due_date` ("drop the
        # deadline"). For the other fields it would wipe data, so it is ignored.
        changes = {
            field: value
            for field, value in changes.items()
            if value is not None or field in NULLABLE_FIELDS
        }

        if "title" in changes:
            changes["title_source"] = TitleSourceType.user

        return await self.todo_repo.update(todo_id, changes)

    async def generate_llm_title(self, todo_id, content) -> None:
        """Background task: replace a fallback title with a generated one."""
        generated = await self.llm_service.create_title(content)

        updated = await self.todo_repo.set_title(
            todo_id,
            title=generated["title"],
            title_source=generated["title_source"],
        )

        if updated:
            logger.info(f"Title generated for todo {todo_id}: {generated}")
        else:
            logger.info(
                f"Generated title for todo {todo_id} dropped: "
                "it already has a user title or the todo is gone"
            )

    async def regenerate_title(self, todo_id) -> TodoModel | None:
        """Explicit request: generate a title even over a user-provided one."""
        todo = await self.todo_repo.get_by_id(todo_id)

        if todo is None:
            return None

        generated = await self.llm_service.create_title(todo.content)

        return await self.todo_repo.update(
            todo_id,
            {
                "title": generated["title"],
                "title_source": generated["title_source"],
            },
        )

    async def prioritize(self, todo_id, now=None) -> TodoModel | None:
        """Ask the LLM for signals, then compute the score deterministically."""
        todo = await self.todo_repo.get_by_id(todo_id)

        if todo is None:
            return None

        now = now or datetime.datetime.now(datetime.timezone.utc)
        open_todos = await self.todo_repo.count_open()

        context = build_priority_context(todo, open_todos, now)
        prompt = render_prompt(self.llm_service.priority_prompt, context)

        signals = await self.llm_service.create_priority_signals(prompt)
        score = priority_score(signals, days_left(todo.due_date, now))

        logger.info(
            f"Todo {todo_id} prioritized: score={score} "
            f"signals={signals.model_dump(exclude={'reasoning'})}"
        )

        return await self.todo_repo.set_priority(
            todo_id,
            score=score,
            signals=signals.model_dump(),
        )

    async def prioritize_in_background(self, todo_id) -> None:
        if not settings.AUTO_PRIORITIZE:
            return

        await self.prioritize(todo_id)

    async def get_next(
        self, now=None
    ) -> tuple[list[tuple[TodoModel, str]], datetime.datetime]:
        """Top todos to work on now, each with a human-readable reason."""
        now = now or datetime.datetime.now(datetime.timezone.utc)
        todos = await self.todo_repo.get_next(NEXT_TODOS_LIMIT)

        return [(todo, self.explain(todo, now)) for todo in todos], now

    @staticmethod
    def explain(todo: TodoModel, now: datetime.datetime) -> str:
        """Why this todo is near the top — built from facts, not from the LLM."""
        parts = [f"score {todo.priority_score}"]
        remaining = days_left(todo.due_date, now)

        if remaining is not None and deadline_boost(remaining) > 0:
            if remaining < 0:
                parts.append(f"overdue by {abs(remaining)} day(s)")
            elif remaining == 0:
                parts.append("due today")
            else:
                parts.append(f"due in {remaining} day(s)")

        signals = todo.priority_signals

        if signals is None:
            parts.append("not prioritized yet")
        else:
            parts.append(f"urgency {signals.urgency}/5, effort {signals.effort}/5")

            if signals.blocks_others:
                parts.append("blocks other work")

            if signals.reasoning:
                parts.append(signals.reasoning)

        return "; ".join(parts)

    @staticmethod
    def __fallback_title(content: str) -> str:
        return " ".join(content.split())[:FALLBACK_TITLE_LENGTH]
