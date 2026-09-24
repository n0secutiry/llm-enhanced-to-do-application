from fastapi import Depends, Request
from loguru import logger
from pymongo import AsyncMongoClient

from app.config import settings
from app.v1.todo.repository import TodoRepository

ASYNC_MONGO_URI = (
    f"mongodb://{settings.MONGO_ROOT_USER}:{settings.MONGO_ROOT_PASSWORD}"
    f"@{settings.MONGO_HOST_DB}:{settings.MONGO_PORT_DB}/{settings.MONGO_NAME_DB}"
    "?authSource=admin"
)


async def running_mongo_db(app):
    client = AsyncMongoClient(
        ASYNC_MONGO_URI,
        connectTimeoutMS=settings.MONGO_TIMEOUT_CONNECT_MS,
        serverSelectionTimeoutMS=settings.MONGO_TIMEOUT_SELECTION_SERVER_MS,
    )
    app.state.mongo_db = client[settings.MONGO_NAME_DB]
    await client.admin.command("ping")
    logger.info("Succesful connect to mongo")
    return client


async def get_mongo_db(request: Request):
    return request.app.state.mongo_db


async def get_todo_repository(db=Depends(get_mongo_db)):
    collection = db["todos"]
    return TodoRepository(collection)
