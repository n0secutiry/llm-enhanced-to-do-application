"""What a client is allowed to send.

Fields the server owns — `title_source`, `priority_score`, `priority_signals`,
timestamps — are deliberately absent here: they are set by services and the
scoring formula, never by the caller.
"""

from datetime import datetime

from pydantic import BaseModel, Field

from app.v1.todo.models import StatusType


class TodoCreateRequest(BaseModel):
    # No title means "generate one": the server fills in a fallback immediately
    # and a background task asks the LLM for a better one.
    title: str | None = Field(default=None, min_length=2, max_length=100)
    content: str = Field(min_length=1)
    status: StatusType = StatusType.open
    tags: list[str] = Field(default_factory=list)
    due_date: datetime | None = None


class TodoUpdateRequest(BaseModel):
    """Every field is optional: PATCH only touches what was actually sent.

    Note the difference between the two kinds of fields. For `title`,
    `content`, `status` and `tags` an explicit `null` makes no sense and is
    dropped by the service. For `due_date`, `null` is meaningful — it is how a
    deadline gets removed.
    """

    title: str | None = Field(default=None, min_length=2, max_length=100)
    content: str | None = Field(default=None, min_length=1)
    status: StatusType | None = None
    tags: list[str] | None = None
    due_date: datetime | None = None


class TodoGetItemsRequest(BaseModel):
    status: StatusType | None = None
    tag: str | None = None
    priority_gte: float | None = None
    # `limit` is capped so a single client cannot ask for the whole collection;
    # `offset` is not capped, otherwise later pages become unreachable.
    limit: int = Field(default=10, ge=1, le=100)
    offset: int = Field(default=0, ge=0)
