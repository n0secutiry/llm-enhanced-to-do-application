from pydantic import BaseModel, Field

from app.v1.todo.models import TitleSourceType


class LLMGeneratedTitleResponse(BaseModel):
    title: str = Field(min_length=3, max_length=60)


class LLMGeneratedTitleDataResponse(BaseModel):
    title: str = Field(min_length=3, max_length=60)
    title_source: TitleSourceType
