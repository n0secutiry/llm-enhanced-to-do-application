"""The only place that talks to the LLM.

Two jobs, both optional for the application to work:
  * `create_title`  — turn note text into a short title;
  * `create_priority_signals` — return narrow planning signals.

Both wrap the model in the same safety net: a timeout, retries, schema
validation and a deterministic fallback. Callers always get a usable answer.
"""

import asyncio
from pathlib import Path

from loguru import logger

from app.config import settings
from app.v1.llm.exception import LLMGenerationError
from app.v1.llm.schemas.response_schemas import LLMGeneratedTitleResponse
from app.v1.llm.tracing import trace_generation
from app.v1.todo.schemas.llm_schemas import FALLBACK_SIGNALS, PrioritySignals

PROMPTS_DIR = Path(__file__).resolve().parents[3] / "app" / "prompts"

TITLE_PROMPT_VERSION = "title-v2"
PRIORITY_PROMPT_VERSION = "priority-v1"

MAX_ATTEMPTS = 3
RETRY_PAUSE_S = 2


class LLMService:
    def __init__(self, ollama):
        self.ollama = ollama
        self.title_prompt = (PROMPTS_DIR / "prompt.txt").read_text(encoding="utf-8")
        self.priority_prompt = (PROMPTS_DIR / "priority_prompt.txt").read_text(
            encoding="utf-8"
        )

    async def create_title(self, content: str) -> dict:
        """Return `{"title": ..., "title_source": "llm" | "fallback"}`."""
        if not self.ollama:
            return self.__fallback_title(content)

        prompt = self.title_prompt.replace(
            "{{ content }}", content[: settings.OLLAMA_INPUT_LIMIT]
        )

        try:
            answer = await self.__generate(
                name="generate-title",
                prompt=prompt,
                schema=LLMGeneratedTitleResponse,
                prompt_version=TITLE_PROMPT_VERSION,
            )
        except LLMGenerationError as err:
            logger.warning(f"Title generation failed, using fallback: {err}")
            return self.__fallback_title(content)

        return {"title": answer.title, "title_source": "llm"}

    async def create_priority_signals(self, prompt: str) -> PrioritySignals:
        """Return LLM signals, or neutral defaults when the model fails."""
        if not self.ollama:
            return FALLBACK_SIGNALS

        try:
            return await self.__generate(
                name="priority-signals",
                prompt=prompt,
                schema=PrioritySignals,
                prompt_version=PRIORITY_PROMPT_VERSION,
            )
        except LLMGenerationError as err:
            logger.warning(f"Priority signals failed, using defaults: {err}")
            return FALLBACK_SIGNALS

    async def __generate(self, name, prompt, schema, prompt_version):
        """Call the model until it returns an answer that fits the schema."""
        for attempt in range(1, MAX_ATTEMPTS + 1):
            async with trace_generation(name, prompt, prompt_version) as generation:
                try:
                    raw = await asyncio.wait_for(
                        self.ollama.generate(
                            model=settings.OLLAMA_MODEL,
                            prompt=prompt,
                            format=schema.model_json_schema(),
                            stream=False,
                        ),
                        timeout=settings.OLLAMA_TIMEOUT_S,
                    )

                    answer = self.__extract_json(raw)
                    parsed = schema.model_validate_json(answer)

                    generation.finish(
                        output=answer,
                        usage=self.__extract_usage(raw),
                        attempt=attempt,
                    )
                    return parsed

                except asyncio.TimeoutError:
                    generation.finish(error="timeout", attempt=attempt)
                    logger.warning(f"{name}: timeout, attempt {attempt}/{MAX_ATTEMPTS}")
                    retry_pause = RETRY_PAUSE_S

                except Exception as err:
                    generation.finish(error=str(err), attempt=attempt)
                    logger.warning(
                        f"{name}: bad answer, attempt {attempt}/{MAX_ATTEMPTS}: {err}"
                    )
                    # A malformed answer is worth retrying immediately:
                    # waiting does not make the model smarter.
                    retry_pause = 0

            if attempt < MAX_ATTEMPTS and retry_pause:
                await asyncio.sleep(retry_pause)

        raise LLMGenerationError(f"{name} failed after {MAX_ATTEMPTS} attempts")

    @staticmethod
    def __extract_json(raw) -> str:
        """Ollama returns the JSON payload as a string in `response`."""
        if hasattr(raw, "response"):
            return raw.response

        return raw.get("response", "")

    @staticmethod
    def __extract_usage(raw) -> dict[str, int]:
        """Token counts Ollama reports, mapped to LangFuse usage fields."""

        def field(name):
            if hasattr(raw, name):
                return getattr(raw, name)

            return raw.get(name) if hasattr(raw, "get") else None

        prompt_tokens = field("prompt_eval_count") or 0
        output_tokens = field("eval_count") or 0

        if not (prompt_tokens or output_tokens):
            return {}

        return {
            "input": prompt_tokens,
            "output": output_tokens,
            "total": prompt_tokens + output_tokens,
        }

    @staticmethod
    def __fallback_title(content: str) -> dict:
        cleaned = " ".join(content.split())

        return {"title": cleaned[:40], "title_source": "fallback"}
