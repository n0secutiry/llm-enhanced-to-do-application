from datetime import datetime

from pydantic import BaseModel, Field

from app.v1.todo.models import StatusType


class TodoCreateRequest(BaseModel):
    title: str = Field(min_length=2, max_length=100)
    content: str = Field(min_length=1)
    status: StatusType = StatusType.open
    tags: list[str] = []
    due_date: datetime | None = None


class TodoUpdateRequest(BaseModel):
    title: str = Field(default=None, min_length=2, max_length=100)
    content: str = Field(default=None, min_length=1)
    status: StatusType = None
    tags: list[str] = None
    due_date: datetime | None = None


class TodoGetItemsRequest(BaseModel):
    status: StatusType | None = None
    tag: str | None = None
    priority_gte: int | None = None
    limit: int | None = Field(ge=1, le=20, default=10)
    offset: int | None = Field(ge=0, default=0)
