"""Repository tests: exercise MongoDB access without going through HTTP."""

from datetime import datetime, timezone

from bson import ObjectId

from app.v1.todo.schemas.request_schemas import TodoUpdateRequest


def todo_document(title="Buy milk", **overrides):
    document = {
        "title": title,
        "title_source": "user",
        "content": "milk, bread, eggs",
        "status": "open",
        "tags": ["shop"],
        "due_date": None,
    }
    document.update(overrides)
    return document


async def test_create_returns_saved_todo(repo):
    todo = await repo.create(todo_document())

    assert todo is not None
    assert todo.title == "Buy milk"
    assert todo.title_source == "user"
    assert todo.priority_score == 0.0
    assert todo.deleted_at is None
    assert todo.created_at.tzinfo is None or todo.created_at <= datetime.now(
        timezone.utc
    ).replace(tzinfo=None)


async def test_get_by_id_returns_none_for_unknown_and_invalid_id(repo):
    assert await repo.get_by_id(str(ObjectId())) is None
    assert await repo.get_by_id("abc") is None


async def test_update_changes_only_passed_fields(repo):
    todo = await repo.create(todo_document())

    updated = await repo.update(todo.id, {"status": "done"})

    assert updated.status == "done"
    assert updated.title == todo.title
    assert updated.content == todo.content
    assert updated.updated_at >= todo.updated_at


async def test_update_returns_none_for_unknown_id(repo):
    assert await repo.update(str(ObjectId()), {"status": "done"}) is None


async def test_soft_delete_hides_todo_but_keeps_document(repo, todo_collection):
    todo = await repo.create(todo_document())

    assert await repo.soft_delete(todo.id) is True
    assert await repo.get_by_id(todo.id) is None
    assert await repo.soft_delete(todo.id) is False

    raw = await todo_collection.find_one({"_id": ObjectId(todo.id)})
    assert raw is not None, "soft delete must not remove the document"
    assert raw["deleted_at"] is not None


async def test_set_title_only_replaces_fallback_titles(repo):
    todo = await repo.create(todo_document(title_source="fallback"))

    assert await repo.set_title(todo.id, "Title from LLM", "llm") is True

    updated = await repo.get_by_id(todo.id)
    assert updated.title == "Title from LLM"
    assert updated.title_source == "llm"

    # The second attempt is rejected: the title is no longer a fallback one.
    assert await repo.set_title(todo.id, "Another title", "llm") is False


async def test_get_items_filters_and_counts(repo):
    await repo.create(todo_document(title="Work", status="open", tags=["work"]))
    await repo.create(todo_document(title="Home", status="done", tags=["home"]))
    await repo.create(todo_document(title="Work 2", status="open", tags=["work"]))

    items, total = await repo.get_items(None, None, None, limit=10, offset=0)
    assert total == 3
    assert len(items) == 3

    items, total = await repo.get_items("done", None, None, limit=10, offset=0)
    assert total == 1
    assert items[0].title == "Home"

    items, total = await repo.get_items(None, "work", None, limit=10, offset=0)
    assert total == 2


async def test_get_items_paginates_and_sorts_by_priority(repo):
    low = await repo.create(todo_document(title="Low priority"))
    high = await repo.create(todo_document(title="High priority"))
    await repo.update(high.id, {"priority_score": 9.5})

    items, total = await repo.get_items(None, None, None, limit=1, offset=0)
    assert total == 2
    assert len(items) == 1
    assert items[0].id == high.id

    items, _ = await repo.get_items(None, None, None, limit=1, offset=1)
    assert items[0].id == low.id


async def test_get_items_skips_deleted(repo):
    todo = await repo.create(todo_document())
    await repo.soft_delete(todo.id)

    items, total = await repo.get_items(None, None, None, limit=10, offset=0)

    assert total == 0
    assert items == []


async def test_update_schema_sends_only_set_fields(repo):
    """TodoUpdateRequest with exclude_unset leaves untouched fields alone."""
    todo = await repo.create(todo_document())

    changes = TodoUpdateRequest(status="in_progress").model_dump(exclude_unset=True)
    updated = await repo.update(todo.id, changes)

    assert changes == {"status": "in_progress"}
    assert updated.status == "in_progress"
    assert updated.title == todo.title
