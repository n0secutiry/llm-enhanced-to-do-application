"""Tests for prioritisation: the LLM is faked, the formula is real."""

import datetime

from bson import ObjectId

from app.v1.todo.context import build_priority_context, render_prompt
from app.v1.todo.models import TodoModel
from app.v1.todo.scoring import days_left, priority_score
from app.v1.todo.service import TodoService

NOW = datetime.datetime(2026, 6, 15, 12, 0, tzinfo=datetime.timezone.utc)


def todo_model(**overrides):
    document = {
        "_id": ObjectId(),
        "title": "Fix the payment module",
        "title_source": "user",
        "content": "the module crashes on large amounts",
        "status": "open",
        "tags": ["backend", "urgent"],
        "due_date": NOW + datetime.timedelta(days=2),
    }
    document.update(overrides)

    return TodoModel.model_validate(document)


def test_context_contains_facts_the_model_cannot_know():
    context = build_priority_context(todo_model(), open_todos=7, now=NOW)

    assert context["today"] == "2026-06-15"
    assert context["due_date"] == "2026-06-17"
    assert context["days_left"] == "2"
    assert context["open_todos"] == "7"
    assert context["tags"] == "backend, urgent"
    assert context["status"] == "open"


def test_context_handles_a_todo_without_deadline():
    context = build_priority_context(todo_model(due_date=None), open_todos=0, now=NOW)

    assert context["due_date"] == "none"
    assert context["days_left"] == "unknown"


def test_render_prompt_injects_every_placeholder():
    template = "today={{ today }} days={{ days_left }} text={{ content }}"
    context = build_priority_context(todo_model(), open_todos=1, now=NOW)

    prompt = render_prompt(template, context)

    assert "{{" not in prompt
    assert "today=2026-06-15" in prompt


async def test_prioritize_endpoint_stores_score_and_signals(client, fake_llm):
    created = (
        await client.post(
            "/api/v1/todos",
            json={"title": "Pay the invoice", "content": "due this week"},
        )
    ).json()

    response = await client.post(f"/api/v1/todos/{created['id']}/prioritize")

    assert response.status_code == 200
    body = response.json()

    # Signals come from the model, the score is computed by the formula.
    assert body["priority_signals"]["urgency"] == 4
    assert body["priority_signals"]["effort"] == 2
    assert body["priority_signals"]["blocks_others"] is True
    assert body["priority_score"] == priority_score(fake_llm.signals, None)
    assert fake_llm.priority_calls, "the service should have called the LLM"


async def test_prioritize_returns_404_for_unknown_todo(client):
    response = await client.post(f"/api/v1/todos/{ObjectId()}/prioritize")

    assert response.status_code == 404


async def test_deadline_increases_the_score(client):
    soon = (
        await client.post(
            "/api/v1/todos",
            json={
                "title": "Deadline today",
                "content": "text",
                "due_date": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            },
        )
    ).json()
    later = (
        await client.post(
            "/api/v1/todos", json={"title": "No deadline", "content": "text"}
        )
    ).json()

    soon_score = (await client.post(f"/api/v1/todos/{soon['id']}/prioritize")).json()[
        "priority_score"
    ]
    later_score = (await client.post(f"/api/v1/todos/{later['id']}/prioritize")).json()[
        "priority_score"
    ]

    assert soon_score - later_score == 2.0


async def test_next_returns_top_todos_with_reasons(client):
    for title in ("First", "Second", "Third", "Fourth"):
        created = (
            await client.post("/api/v1/todos", json={"title": title, "content": "text"})
        ).json()
        await client.post(f"/api/v1/todos/{created['id']}/prioritize")

    response = await client.get("/api/v1/todos/next")

    assert response.status_code == 200
    body = response.json()
    assert len(body["items"]) == 3, "next returns at most three suggestions"

    scores = [item["priority_score"] for item in body["items"]]
    assert scores == sorted(scores, reverse=True)

    for item in body["items"]:
        assert "urgency 4/5" in item["reason"]
        assert "blocks other work" in item["reason"]


async def test_next_skips_finished_and_deleted_todos(client):
    done = (
        await client.post("/api/v1/todos", json={"title": "Done", "content": "text"})
    ).json()
    deleted = (
        await client.post("/api/v1/todos", json={"title": "Gone", "content": "text"})
    ).json()

    await client.patch(f"/api/v1/todos/{done['id']}", json={"status": "done"})
    await client.delete(f"/api/v1/todos/{deleted['id']}")

    body = (await client.get("/api/v1/todos/next")).json()

    assert body["items"] == []


def test_explain_marks_a_todo_that_was_never_prioritized():
    reason = TodoService.explain(todo_model(priority_signals=None), NOW)

    assert "not prioritized yet" in reason


def test_explain_mentions_an_overdue_deadline():
    overdue = todo_model(due_date=NOW - datetime.timedelta(days=4))

    assert "overdue by 4 day(s)" in TodoService.explain(overdue, NOW)


async def test_new_todo_is_prioritized_in_the_background(client):
    """AUTO_PRIORITIZE makes `next` useful without an explicit call."""
    await client.post("/api/v1/todos", json={"title": "Fresh", "content": "text"})

    body = (await client.get("/api/v1/todos/next")).json()

    assert body["items"][0]["priority_score"] > 0


async def test_regenerate_title_overwrites_a_user_title(client, fake_llm):
    created = (
        await client.post(
            "/api/v1/todos", json={"title": "Old title", "content": "some text"}
        )
    ).json()

    response = await client.post(f"/api/v1/todos/{created['id']}/regenerate-title")

    assert response.status_code == 200
    body = response.json()
    assert body["title"] == fake_llm.title
    assert body["title_source"] == "llm"


async def test_regenerate_title_returns_404_for_unknown_todo(client):
    response = await client.post(f"/api/v1/todos/{ObjectId()}/regenerate-title")

    assert response.status_code == 404


def test_days_left_matches_what_the_context_reports():
    todo = todo_model()

    assert days_left(todo.due_date, NOW) == 2
