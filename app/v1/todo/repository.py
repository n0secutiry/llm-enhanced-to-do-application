from bson import ObjectId


class TodoRepository:
    def __init__(self, client):
        self.client = client

    async def create(self, document):
        result = await self.client.insert_one(document)
        return result

    async def get_by_id(self, id):
        result = await self.client.find_one({"_id": ObjectId(id)})
        return self._to_entity(result) if result else None