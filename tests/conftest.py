"""Shared test fixtures.

Repository and API tests run against a real MongoDB (the `mongodb_services`
container), but in a separate `*-test` database that is wiped before every test.
If Mongo is unreachable, the tests are skipped instead of failing.
"""

import os

import httpx
import pytest
import pytest_asyncio
from pymongo import AsyncMongoClient

from app.config import settings
from app.database.mongo_db import get_todo_repository
from app.v1.llm.ollama import get_llm_service
from app.v1.todo.repository import TodoRepository
from app.v1.todo.schemas.llm_schemas import PrioritySignals

TEST_MONGO_HOST = os.getenv("TEST_MONGO_HOST", "localhost")
TEST_DB_NAME = f"{settings.MONGO_NAME_DB}-test"

TEST_MONGO_URI = (
    f"mongodb://{settings.MONGO_ROOT_USER}:{settings.MONGO_ROOT_PASSWORD}"
    f"@{TEST_MONGO_HOST}:{settings.MONGO_PORT_DB}/?authSource=admin"
)


@pytest_asyncio.fixture
async def todo_collection():
    client: AsyncMongoClient = AsyncMongoClient(
        TEST_MONGO_URI, serverSelectionTimeoutMS=2000
    )

    try:
        await client.admin.command("ping")
    except Exception:
        await client.close()
        pytest.skip(f"Mongo is not available at {TEST_MONGO_HOST}")

    collection = client[TEST_DB_NAME]["todos"]
    await collection.delete_many({})

    yield collection

    await collection.delete_many({})
    await client.close()


@pytest_asyncio.fixture
async def repo(todo_collection):
    return TodoRepository(todo_collection)


class FakeLLMService:
    """LLM stub: never calls a model, returns ready-made answers."""

    priority_prompt = "fake priority prompt: {{ content }}"

    def __init__(self, title="Title from LLM", title_source="llm"):
        self.title = title
        self.title_source = title_source
        self.calls = []
        self.priority_calls = []
        self.signals = PrioritySignals(
            urgency=4,
            effort=2,
            blocks_others=True,
            reasoning="fake signals",
        )

    async def create_title(self, prompt):
        self.calls.append(prompt)
        return {"title": self.title, "title_source": self.title_source}

    async def create_priority_signals(self, prompt):
        self.priority_calls.append(prompt)
        return self.signals


@pytest.fixture
def fake_llm():
    return FakeLLMService()


@pytest_asyncio.fixture
async def client(repo, fake_llm):
    """App with overridden dependencies: test Mongo plus a fake LLM.

    Requests go through the ASGI transport, so the app runs in the same event
    loop as the Mongo client from the fixture, and `lifespan` never starts:
    neither Ollama nor the production database is needed for tests.
    """
    from app.main import app

    app.dependency_overrides[get_todo_repository] = lambda: repo
    app.dependency_overrides[get_llm_service] = lambda: fake_llm

    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as async_client:
        yield async_client

    app.dependency_overrides.clear()
