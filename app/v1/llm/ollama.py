import asyncio

import ollama
from fastapi import Request
from loguru import logger

from app.config import settings


async def running_ollama(app):
    logger.info("Connect to ollama...")
    client = ollama.AsyncClient(host=settings.OLLAMA_URL, timeout=120.0)
    for attempt in range(3):
        try:
            await client.pull(settings.OLLAMA_MODEL)
            app.state.ollama_client = client
            logger.info("Succesful connect to ollama")
            return client
        except Exception as err:
            logger.warning(f"Ollama connection attempt {attempt + 1}/3 failed: {err}")
            if attempt < 2:
                await asyncio.sleep(5)

    logger.error("Could not connect to Ollama")
    app.state.ollama_client = None
    return None


async def get_ollama_client(request: Request):
    return getattr(request.app.state, "ollama_client", None)
