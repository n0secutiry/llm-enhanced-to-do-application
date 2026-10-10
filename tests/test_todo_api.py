"""Endpoint tests: go through HTTP, with the LLM replaced by a fake."""

from bson import ObjectId


async def test_create_todo_with_user_title(client):
    response = await client.post(
        "/api/v1/todos",
        json={"title": "My title", "content": "some text"},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["title"] == "My title"
    assert body["title_source"] == "user"
    assert body["status"] == "open"
    assert ObjectId.is_valid(body["id"])


async def test_create_todo_without_title_uses_fallback_then_llm(client, fake_llm):
    response = await client.post(
        "/api/v1/todos",
        json={"content": "Call the clinic and book a check-up for Monday morning"},
    )

    assert response.status_code == 201
    body = response.json()
    # The response comes back immediately, with a temporary title from the text.
    assert body["title_source"] == "fallback"
    assert body["title"].startswith("Call the clinic")

    # Background tasks finish before the request completes,
    # so the LLM title must already be stored.
    todo = (await client.get(f"/api/v1/todos/{body['id']}")).json()
    assert todo["title"] == fake_llm.title
    assert todo["title_source"] == "llm"
    assert fake_llm.calls, "the background task should have called the LLM"


async def test_create_todo_validates_input(client):
    assert (await client.post("/api/v1/todos", json={})).status_code == 422

    response = await client.post("/api/v1/todos", json={"title": "A", "content": "x"})
    assert response.status_code == 422


async def test_get_todo_by_id(client):
    created = (
        await client.post("/api/v1/todos", json={"title": "A note", "content": "text"})
    ).json()

    response = await client.get(f"/api/v1/todos/{created['id']}")

    assert response.status_code == 200
    assert response.json()["id"] == created["id"]


async def test_get_todo_returns_404_for_unknown_and_invalid_id(client):
    assert (await client.get(f"/api/v1/todos/{ObjectId()}")).status_code == 404
    assert (await client.get("/api/v1/todos/abc")).status_code == 404


async def test_list_todos_with_filters_and_pagination(client):
    await client.post(
        "/api/v1/todos",
        json={"title": "Work", "content": "text", "tags": ["work"]},
    )
    await client.post(
        "/api/v1/todos",
        json={
            "title": "Home",
            "content": "text",
            "tags": ["home"],
            "status": "done",
        },
    )

    all_todos = (await client.get("/api/v1/todos")).json()
    assert all_todos["total"] == 2
    assert len(all_todos["items"]) == 2

    done = (await client.get("/api/v1/todos", params={"status": "done"})).json()
    assert done["total"] == 1
    assert done["items"][0]["title"] == "Home"

    tagged = (await client.get("/api/v1/todos", params={"tag": "work"})).json()
    assert tagged["total"] == 1

    page = (await client.get("/api/v1/todos", params={"limit": 1, "offset": 0})).json()
    assert page["total"] == 2, "total counts every match, not just the page"
    assert len(page["items"]) == 1


async def test_list_todos_rejects_bad_limit(client):
    assert (await client.get("/api/v1/todos", params={"limit": 0})).status_code == 422
    assert (
        await client.get("/api/v1/todos", params={"limit": 9999})
    ).status_code == 422


async def test_patch_updates_fields_and_marks_title_as_user(client):
    created = (
        await client.post("/api/v1/todos", json={"content": "text without a title"})
    ).json()

    response = await client.patch(
        f"/api/v1/todos/{created['id']}", json={"title": "Title set by the user"}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["title"] == "Title set by the user"
    assert body["title_source"] == "user"
    assert body["content"] == "text without a title", "PATCH keeps untouched fields"


async def test_patch_returns_404_for_unknown_id(client):
    response = await client.patch(
        f"/api/v1/todos/{ObjectId()}", json={"status": "done"}
    )

    assert response.status_code == 404


async def test_delete_todo_is_soft_and_idempotent(client):
    created = (
        await client.post(
            "/api/v1/todos", json={"title": "To be deleted", "content": "text"}
        )
    ).json()

    assert (await client.delete(f"/api/v1/todos/{created['id']}")).status_code == 204
    assert (await client.get(f"/api/v1/todos/{created['id']}")).status_code == 404
    assert (await client.delete(f"/api/v1/todos/{created['id']}")).status_code == 404
    assert (await client.get("/api/v1/todos")).json()["total"] == 0


async def test_patch_can_clear_due_date_but_not_other_fields(client):
    created = (
        await client.post(
            "/api/v1/todos",
            json={
                "title": "With a deadline",
                "content": "text",
                "due_date": "2026-12-31T00:00:00Z",
                "tags": ["work"],
            },
        )
    ).json()

    cleared = (
        await client.patch(f"/api/v1/todos/{created['id']}", json={"due_date": None})
    ).json()

    assert cleared["due_date"] is None, "null removes the deadline"

    # An explicit null for other fields is ignored instead of wiping data.
    kept = (
        await client.patch(
            f"/api/v1/todos/{created['id']}", json={"title": None, "tags": None}
        )
    ).json()

    assert kept["title"] == "With a deadline"
    assert kept["tags"] == ["work"]
