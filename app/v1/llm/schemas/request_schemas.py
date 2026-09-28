from pydantic import BaseModel, Field


class LLMGenerateTitleRequest(BaseModel):
    prompt: str = Field(min_length=5)
