from bson import ObjectId
from bson.errors import InvalidId

from app.v1.todo.models import TodoModel


class TodoRepository:
    def __init__(self, collection):
        self.collection = collection

    async def create(self, document):
        result = await self.collection.insert_one(document)
        return result

    async def get_by_id(self, id):
        try:
            result = await self.collection.find_one({"_id": ObjectId(id)})
            return TodoModel.model_validate(result)
        except InvalidId:
            return None