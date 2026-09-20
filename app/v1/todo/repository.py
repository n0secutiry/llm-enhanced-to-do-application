from datetime import datetime, timezone

from bson import ObjectId
from bson.errors import InvalidId

from app.v1.todo.models import TodoModel
from app.v1.todo.schemas.request_schemas import TodoCreateRequest


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
            result = await self.collection.find_one({"_id": ObjectId(id)})
            if not result:
                return None
            return TodoModel.model_validate(result)
        except InvalidId:
            return None
