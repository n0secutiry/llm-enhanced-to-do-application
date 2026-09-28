from fastapi import APIRouter, Depends, HTTPException, status
from loguru import logger

from app.v1.llm.exception import LLMTimeoutError
from app.v1.llm.ollama import get_ollama_client
from app.v1.llm.schemas.request_schemas import LLMGenerateTitleRequest
from app.v1.llm.schemas.response_schemas import LLMGeneratedTitleDataResponse
from app.v1.llm.service import LLMService

router = APIRouter(prefix="/api/v1/llm", tags=["LLM"])


@router.post(
    "",
    response_model=LLMGeneratedTitleDataResponse,
    status_code=status.HTTP_201_CREATED,
    description="Generate title for todo",
)
async def make_title_todo(
    data: LLMGenerateTitleRequest,
    ollama_client=Depends(get_ollama_client),
):
    try:
        client_repository = LLMService(ollama_client)
        result = await client_repository.create_title(data.prompt)
        return result
    except LLMTimeoutError as err:
        raise HTTPException(
            detail=str(err), status_code=status.HTTP_504_GATEWAY_TIMEOUT
        )
    except Exception as err:
        logger.error(err)
        raise HTTPException(
            detail="LLM failed", status_code=status.HTTP_503_SERVICE_UNAVAILABLE
        )
