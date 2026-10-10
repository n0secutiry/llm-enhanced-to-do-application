"""LLM service tests: a fake Ollama client covers every failure path.

These tests never touch a real model, so they run anywhere and stay fast.
"""

import asyncio

import pytest

from app.v1.llm.service import LLMService
from app.v1.todo.schemas.llm_schemas import FALLBACK_SIGNALS


class FakeOllama:
    """Replays a scripted list of answers or exceptions, one per call."""

    def __init__(self, *answers):
        self.answers = list(answers)
        self.calls = 0

    async def generate(self, **kwargs):
        self.calls += 1
        answer = self.answers.pop(0) if self.answers else self.answers_default()

        if isinstance(answer, Exception):
            raise answer

        if answer == "hang":
            await asyncio.sleep(10)

        return {"response": answer}

    @staticmethod
    def answers_default():
        return '{"title": "default"}'


@pytest.fixture(autouse=True)
def fast_retries(monkeypatch):
    """Keep retry pauses out of the test runtime."""
    monkeypatch.setattr("app.v1.llm.service.RETRY_PAUSE_S", 0)


async def test_valid_answer_is_used_as_is():
    service = LLMService(FakeOllama('{"title": "Book a clinic check-up"}'))

    result = await service.create_title("Call the clinic and book a check-up")

    assert result == {"title": "Book a clinic check-up", "title_source": "llm"}


async def test_garbage_answer_falls_back_to_the_text():
    service = LLMService(FakeOllama("not a json at all", "still broken", "{}"))

    result = await service.create_title("Call the clinic and book a check-up")

    assert result["title_source"] == "fallback"
    assert result["title"] == "Call the clinic and book a check-up"
    assert service.ollama.calls == 3, "all three attempts should be used"


async def test_too_long_title_is_rejected_and_falls_back():
    long_title = "x" * 200
    service = LLMService(FakeOllama(*[f'{{"title": "{long_title}"}}'] * 3))

    result = await service.create_title("some note text")

    assert result["title_source"] == "fallback"


async def test_retry_recovers_after_one_bad_answer():
    service = LLMService(FakeOllama("broken", '{"title": "Second attempt wins"}'))

    result = await service.create_title("some note text")

    assert result == {"title": "Second attempt wins", "title_source": "llm"}
    assert service.ollama.calls == 2


async def test_timeout_falls_back(monkeypatch):
    monkeypatch.setattr("app.v1.llm.service.settings.OLLAMA_TIMEOUT_S", 0.01)
    service = LLMService(FakeOllama("hang", "hang", "hang"))

    result = await service.create_title("Call the clinic and book a check-up")

    assert result["title_source"] == "fallback"


async def test_missing_ollama_client_falls_back_without_calls():
    service = LLMService(None)

    result = await service.create_title("Call the clinic and book a check-up")

    assert result["title_source"] == "fallback"


async def test_fallback_title_is_cleaned_up():
    service = LLMService(None)

    result = await service.create_title("  text   with    messy\n\nspacing  ")

    assert result["title"] == "text with messy spacing"


async def test_long_input_is_truncated_before_the_call(monkeypatch):
    monkeypatch.setattr("app.v1.llm.service.settings.OLLAMA_INPUT_LIMIT", 50)
    captured = {}

    class CapturingOllama(FakeOllama):
        async def generate(self, **kwargs):
            captured["prompt"] = kwargs["prompt"]
            return await super().generate(**kwargs)

    service = LLMService(CapturingOllama('{"title": "ok title"}'))
    await service.create_title("word " * 500)

    assert len(captured["prompt"]) < 2000


async def test_priority_signals_are_parsed():
    answer = (
        '{"urgency": 5, "effort": 2, "blocks_others": true, "reasoning": "blocker"}'
    )
    service = LLMService(FakeOllama(answer))

    signals = await service.create_priority_signals("prompt")

    assert signals.urgency == 5
    assert signals.effort == 2
    assert signals.blocks_others is True


async def test_out_of_range_signals_fall_back_to_neutral_defaults():
    answer = '{"urgency": 99, "effort": 0, "blocks_others": true, "reasoning": "x"}'
    service = LLMService(FakeOllama(answer, answer, answer))

    signals = await service.create_priority_signals("prompt")

    assert signals == FALLBACK_SIGNALS


async def test_priority_signals_without_ollama_use_defaults():
    signals = await LLMService(None).create_priority_signals("prompt")

    assert signals == FALLBACK_SIGNALS
