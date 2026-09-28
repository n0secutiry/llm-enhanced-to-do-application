import asyncio
from pathlib import Path

from loguru import logger

from app.config import settings
from app.v1.llm.exception import LLMGenerationError
from app.v1.llm.schemas.response_schemas import LLMGeneratedTitleResponse


class LLMService:
    def __init__(self, ollama):
        self.ollama = ollama
        self.prompt_path = Path("app/prompts/prompt.txt")
        self.system_prompt_template = self.prompt_path.read_text(encoding="utf-8")

    async def __create_title_llm(self, prompt):
        prompt = prompt[:2000]
        data_format = LLMGeneratedTitleResponse.model_json_schema()
        final_prompt = self.system_prompt_template.replace("{{ content }}", prompt)
        for attempt in range(3):
            try:
                ollama_response = await asyncio.wait_for(
                    self.ollama.generate(
                        model=settings.OLLAMA_MODEL,
                        prompt=final_prompt,
                        format=data_format,
                        stream=False,
                    ),
                    timeout=120,
                )
                if hasattr(ollama_response, "response"):
                    json_string = ollama_response.response
                else:
                    json_string = ollama_response.get("response", "")

                json_string = LLMGeneratedTitleResponse.model_validate_json(json_string)
                result = {"title": json_string.title, "title_source": "llm"}
                return result
            except asyncio.TimeoutError:
                logger.warning(f"Ollama response timeout, attempt {attempt + 1}/3")
            except Exception as err:
                logger.warning(
                    f"Ollama generation failed, attempt {attempt + 1}/3: {err}"
                )

            if attempt < 2:
                await asyncio.sleep(4)

        raise LLMGenerationError("Failed to generate title")

    async def __create_title_without_llm(self, prompt):
        return {"title": prompt[:40], "title_source": "fallback"}

    async def create_title(self, prompt):
        if not self.ollama:
            return await self.__create_title_without_llm(prompt)

        try:
            return await self.__create_title_llm(prompt)
        except Exception as err:
            logger.warning(f"LLM failed, using fallback: {err}")
            return await self.__create_title_without_llm(prompt)
