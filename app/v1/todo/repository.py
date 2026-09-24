import asyncio
from datetime import datetime, timezone
from typing import Any

from bson import ObjectId
from bson.errors import InvalidId
from pymongo import ReturnDocument

from app.v1.todo.models import TodoModel
from app.v1.todo.schemas.request_schemas import TodoCreateRequest, TodoUpdateRequest


class TodoRepository:
    def __init__(self, collection):
        self.collection = collection

    async def create(self, document: TodoCreateRequest):
        user_data = document.model_dump()
        server_fields = {
            "title_source": "user",
            "priority_score": 0.0,
            "priority_signals": None,
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
            "deleted_at": None,
        }

        full_document = user_data | server_fields
        new_document = await self.collection.insert_one(full_document)
        result = await self.get_by_id(new_document.inserted_id)
        return result

    async def get_by_id(self, id):
        try:
            result = await self.collection.find_one(
                {"_id": ObjectId(id), "deleted_at": None}
            )
            if not result:
                return None
            return TodoModel.model_validate(result)
        except InvalidId:
            return None

    async def update(self, id, data: TodoUpdateRequest) -> TodoModel | None:
        changes = data.model_dump(exclude_unset=True)

        if not changes:
            return await self.get_by_id(id)

        changes["updated_at"] = datetime.now(timezone.utc)

        try:
            result = await self.collection.find_one_and_update(
                {"_id": ObjectId(id), "deleted_at": None},
                {"$set": changes},
                return_document=ReturnDocument.AFTER,
            )
        except InvalidId:
            return None

        if not result:
            return None

        return TodoModel.model_validate(result)

    async def soft_delete(self, id) -> bool:
        now = datetime.now(timezone.utc)

        try:
            result = await self.collection.update_one(
                {"_id": ObjectId(id), "deleted_at": None},
                {"$set": {"deleted_at": now, "updated_at": now}},
            )
        except InvalidId:
            return False

        return result.modified_count == 1

    async def get_items(
        self, status, tag, priority_gte, limit, offset
    ) -> tuple[list[TodoModel], int]:
        query: dict[str, Any] = {"deleted_at": None}

        if status:
            query["status"] = status

        if tag:
            query["tags"] = tag

        if priority_gte is not None:
            query["priority_score"] = {"$gte": priority_gte}

        cursor = (
            self.collection.find(query)
            .sort("priority_score", -1)
            .skip(offset)
            .limit(limit)
        )
        list_length = limit if limit > 0 else None

        items_task = cursor.to_list(length=list_length)
        count_task = self.collection.count_documents(query)

        raw_items, total = await asyncio.gather(items_task, count_task)
        items = [TodoModel(**item) for item in raw_items]

        return items, total
