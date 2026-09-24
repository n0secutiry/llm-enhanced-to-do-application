from fastapi import APIRouter, Depends, HTTPException, status

from app.database.mongo_db import get_todo_repository
from app.v1.todo.repository import TodoRepository
from app.v1.todo.schemas.request_schemas import (
    TodoCreateRequest,
    TodoGetItemsRequest,
    TodoUpdateRequest,
)
from app.v1.todo.schemas.response_schemas import TodoListResponse, TodoResponse

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


@router.get("", response_model=TodoListResponse, status_code=status.HTTP_200_OK)
async def get_todo_items(
    data: TodoGetItemsRequest = Depends(),
    repo: TodoRepository = Depends(get_todo_repository),
):
    items, total = await repo.get_items(
        data.status, data.tag, data.priority_gte, data.limit, data.offset
    )
    return TodoListResponse(
        items=items,
        total=total,
        limit=data.limit,
        offset=data.offset,
    )


@router.patch(
    "/{todo_id}",
    response_model=TodoResponse,
    status_code=status.HTTP_200_OK,
    description="Update part of todo",
)
async def update_todo(
    todo_id: str,
    data: TodoUpdateRequest,
    repo: TodoRepository = Depends(get_todo_repository),
):
    result = await repo.update(todo_id, data)
    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Not found todo"
        )
    return result


@router.delete(
    "/{todo_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    description="Soft delete todo",
)
async def delete_todo(
    todo_id: str, repo: TodoRepository = Depends(get_todo_repository)
):
    deleted = await repo.soft_delete(todo_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Not found todo"
        )
