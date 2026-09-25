from fastapi import APIRouter, Depends, HTTPException, status

from app.database.mongo_db import get_todo_repository
from app.v1.todo.repository import TodoRepository
from app.v1.todo.schemas.request_schemas import TodoCreateRequest
from app.v1.todo.schemas.response_schemas import TodoResponse

router = APIRouter(prefix="/api/v1/todos", tags=["Todos"])


@router.post(
    "",
    response_model=TodoResponse,
    status_code=status.HTTP_201_CREATED,
    description="Add new notion",
)
async def create_new_todo(
    data: TodoCreateRequest, repo: TodoRepository = Depends(get_todo_repository)
):
    result = await repo.create(data)
    return result


@router.get(
    "/{todo_id}",
    response_model=TodoResponse,
    status_code=status.HTTP_200_OK,
    description="Get todo by id",
)
async def get_todo_by_id(
    todo_id: str, repo: TodoRepository = Depends(get_todo_repository)
):
    result = await repo.get_by_id(todo_id)
    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Not found todo"
        )
    return result
