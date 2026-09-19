import datetime
from enum import StrEnum
from typing import Annotated

from bson import ObjectId
from pydantic import BaseModel, BeforeValidator, Field

PyObjectId = Annotated[str, BeforeValidator(lambda v: str(v) if isinstance(v, ObjectId) else v)]


class StatusType(StrEnum):
    open = "open"
    in_progress = "in_progress"
    done = "done"
    archived = "archived"


class TitleSourceType(StrEnum):
    user = "user"
    llm = "llm"
    fallback = "fallback"


class TodoModel(BaseModel):
    id: PyObjectId = Field(alias="_id")
    title: str = Field(min_length=2, max_length=100)                      
    title_source: TitleSourceType
    content: str
    status: StatusType
    tags: list[str] = Field(default_factory=list)
    due_date: datetime.datetime | None = None
    priority_score: float = 0.0
    priority_signals: None = None
    created_at: datetime.datetime = Field(
        default_factory=lambda: datetime.datetime.now(datetime.timezone.utc)
    )
    updated_at: datetime.datetime = Field(
        default_factory=lambda: datetime.datetime.now(datetime.timezone.utc)
    )
    deleted_at: datetime.datetime | None = None