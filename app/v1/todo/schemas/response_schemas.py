import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.v1.todo.models import PyObjectId, StatusType, TitleSourceType


class TodoResponse(BaseModel):
    id: PyObjectId = Field(validation_alias="_id")
    title: str
    title_source: TitleSourceType
    content: str
    status: StatusType
    tags: list[str]
    priority_score: float
    due_date: datetime.datetime | None = None
    created_at: datetime.datetime
    updated_at: datetime.datetime

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)
