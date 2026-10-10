"""Optional LangFuse tracing for LLM calls.

Tracing stays completely off while the LangFuse keys are empty, so the
application behaves identically with or without an account. A traced call
records the prompt, the raw answer, latency, token counts, the model name and
the prompt version — enough to compare two prompt versions later.

Tracing must never break a request: every failure here is swallowed and logged.
"""

import time
from contextlib import asynccontextmanager

from loguru import logger

from app.config import settings

_client = None
_client_ready = False


def get_langfuse_client():
    """Build the client lazily; return None when tracing is not configured."""
    global _client, _client_ready

    if not (settings.LANGFUSE_PUBLIC_KEY and settings.LANGFUSE_SECRET_KEY):
        return None

    if _client_ready:
        return _client

    _client_ready = True

    try:
        from langfuse import Langfuse

        _client = Langfuse(
            public_key=settings.LANGFUSE_PUBLIC_KEY,
            secret_key=settings.LANGFUSE_SECRET_KEY,
            host=settings.LANGFUSE_HOST,
        )
        logger.info("LangFuse tracing enabled")
    except Exception as err:  # pragma: no cover - depends on the environment
        logger.warning(f"LangFuse is configured but unusable: {err}")
        _client = None

    return _client


class Generation:
    """Carries what happened during one LLM call back to the tracer."""

    def __init__(self):
        self.output = None
        self.error = None
        self.usage: dict[str, int] = {}
        self.metadata: dict = {}

    def finish(self, output=None, error=None, usage=None, **metadata):
        self.output = output
        self.error = error
        self.usage = usage or {}
        self.metadata.update(metadata)


@asynccontextmanager
async def trace_generation(name: str, prompt: str, prompt_version: str):
    """Trace one generation. Yields a `Generation` for the caller to fill in."""
    generation = Generation()
    started = time.perf_counter()
    client = get_langfuse_client()

    try:
        yield generation
    finally:
        latency_ms = round((time.perf_counter() - started) * 1000, 2)
        metadata = {
            "prompt_version": prompt_version,
            "latency_ms": latency_ms,
            **generation.metadata,
        }

        if client is None:
            logger.debug(
                f"LLM call '{name}' took {latency_ms}ms, "
                f"error={generation.error or 'none'}"
            )
        else:
            try:
                with client.start_as_current_observation(
                    name=name,
                    as_type="generation",
                    input=prompt,
                    output=generation.output,
                    model=settings.OLLAMA_MODEL,
                    metadata=metadata,
                    version=prompt_version,
                    level="DEFAULT" if generation.error is None else "ERROR",
                    status_message=(
                        str(generation.error) if generation.error else None
                    ),
                    usage_details=generation.usage or None,
                ):
                    pass
            except Exception as err:  # pragma: no cover - network dependent
                logger.warning(f"LangFuse tracing failed: {err}")


def shutdown_tracing() -> None:
    """Flush pending events on application shutdown."""
    client = get_langfuse_client()

    if client is None:
        return

    try:
        client.flush()
        client.shutdown()
    except Exception as err:  # pragma: no cover - network dependent
        logger.warning(f"LangFuse shutdown failed: {err}")
