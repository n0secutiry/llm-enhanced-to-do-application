from datetime import datetime

from pydantic import BaseModel

from app.v1.todo.models import StatusType


class TodoCreateRequest(BaseModel):
    title: str
    content: str
    status: StatusType = StatusType.open
    tags: list[str] = []
    due_date: datetime | None = None


class TodoUpdateRequest(BaseModel):
    title: str = None
    content: str = None
    status: StatusType = None
    tags: list[str] = None
    due_date: datetime | None = None
