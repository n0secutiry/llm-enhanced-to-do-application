import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.v1.todo.models import PyObjectId, StatusType, TitleSourceType
from app.v1.todo.schemas.llm_schemas import PrioritySignals


class TodoResponse(BaseModel):
    id: PyObjectId = Field(validation_alias="_id")
    title: str
    title_source: TitleSourceType
    content: str
    status: StatusType
    tags: list[str]
    priority_score: float
    # Kept next to the score on purpose: the client can see what the model
    # said and what the formula decided.
    priority_signals: PrioritySignals | None = None
    due_date: datetime.datetime | None = None
    created_at: datetime.datetime
    updated_at: datetime.datetime

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class TodoListResponse(BaseModel):
    items: list[TodoResponse]
    total: int
    limit: int
    offset: int


class NextTodoResponse(BaseModel):
    """One suggestion from `GET /todos/next`, with the reason attached."""

    todo: TodoResponse
    priority_score: float
    reason: str


class NextTodosResponse(BaseModel):
    items: list[NextTodoResponse]
    generated_at: datetime.datetime
