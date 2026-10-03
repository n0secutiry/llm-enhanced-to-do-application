from fastapi import Depends
from loguru import logger

from app.database.mongo_db import get_todo_repository
from app.v1.llm.ollama import get_llm_service
from app.v1.llm.service import LLMService
from app.v1.todo.models import TitleSourceType
from app.v1.todo.repository import TodoRepository
from app.v1.todo.schemas.request_schemas import TodoCreateRequest, TodoUpdateRequest

FALLBACK_TITLE_LENGTH = 40


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

    async def create(self, data: TodoCreateRequest):
        document = data.model_dump()

        if document["title"] is not None:
            document["title_source"] = TitleSourceType.user
        else:
            document["title"] = self.__fallback_title(document["content"])
            document["title_source"] = TitleSourceType.fallback

        return await self.todo_repo.create(document)

    async def update(self, todo_id, data: TodoUpdateRequest):
        changes = data.model_dump(exclude_unset=True)

        if "title" in changes:
            changes["title_source"] = TitleSourceType.user

        return await self.todo_repo.update(todo_id, changes)

    async def generate_llm_title(self, todo_id, content):
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

    @staticmethod
    def __fallback_title(content: str) -> str:
        return " ".join(content.split())[:FALLBACK_TITLE_LENGTH]
