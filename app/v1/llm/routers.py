"""Internal endpoint used for prompt tuning.

It is not part of the public todo API: it exists so a title prompt can be
tried out without creating notes.
"""

from fastapi import APIRouter, Depends, status
from loguru import logger

from app.rate_limit import limit_llm_calls
from app.v1.llm.ollama import get_llm_service
from app.v1.llm.schemas.request_schemas import LLMGenerateTitleRequest
from app.v1.llm.schemas.response_schemas import LLMGeneratedTitleDataResponse
from app.v1.llm.service import LLMService

router = APIRouter(prefix="/api/v1/llm", tags=["LLM"])


@router.post(
    "",
    response_model=LLMGeneratedTitleDataResponse,
    status_code=status.HTTP_201_CREATED,
    description="Generate a title from arbitrary text (prompt tuning helper)",
    dependencies=[Depends(limit_llm_calls)],
)
async def make_title_todo(
    data: LLMGenerateTitleRequest,
    llm_service: LLMService = Depends(get_llm_service),
):
    result = await llm_service.create_title(data.prompt)

    logger.debug(f"Title generated from raw text: {result}")

    return result
