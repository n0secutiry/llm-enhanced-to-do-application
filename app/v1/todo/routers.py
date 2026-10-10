from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status

from app.database.mongo_db import get_todo_repository
from app.rate_limit import limit_llm_calls
from app.v1.todo.repository import TodoRepository
from app.v1.todo.schemas.request_schemas import (
    TodoCreateRequest,
    TodoGetItemsRequest,
    TodoUpdateRequest,
)
from app.v1.todo.schemas.response_schemas import (
    NextTodoResponse,
    NextTodosResponse,
    TodoListResponse,
    TodoResponse,
)
from app.v1.todo.service import TodoService, get_todo_service

router = APIRouter(prefix="/api/v1/todos", tags=["Todos"])

NOT_FOUND = HTTPException(
    status_code=status.HTTP_404_NOT_FOUND, detail="Not found todo"
)


@router.post(
    "",
    response_model=TodoResponse,
    status_code=status.HTTP_201_CREATED,
    description="Create a todo. Without a title one is generated in background",
)
async def create_new_todo(
    data: TodoCreateRequest,
    background_tasks: BackgroundTasks,
    service: TodoService = Depends(get_todo_service),
):
    todo = await service.create(data)

    if data.title is None:
        background_tasks.add_task(service.generate_llm_title, todo.id, data.content)

    background_tasks.add_task(service.prioritize_in_background, todo.id)

    return todo


@router.get(
    "",
    response_model=TodoListResponse,
    status_code=status.HTTP_200_OK,
    description="List todos with filters and pagination",
)
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


# Declared before "/{todo_id}" on purpose: otherwise "next" would be read as an id.
@router.get(
    "/next",
    response_model=NextTodosResponse,
    status_code=status.HTTP_200_OK,
    description="Top todos to work on right now, with the reason for each",
)
async def get_next_todos(service: TodoService = Depends(get_todo_service)):
    suggestions, generated_at = await service.get_next()

    return NextTodosResponse(
        items=[
            NextTodoResponse(
                todo=TodoResponse.model_validate(todo),
                priority_score=todo.priority_score,
                reason=reason,
            )
            for todo, reason in suggestions
        ],
        generated_at=generated_at,
    )


@router.get(
    "/{todo_id}",
    response_model=TodoResponse,
    status_code=status.HTTP_200_OK,
    description="Get a todo by id",
)
async def get_todo_by_id(
    todo_id: str, repo: TodoRepository = Depends(get_todo_repository)
):
    result = await repo.get_by_id(todo_id)

    if not result:
        raise NOT_FOUND

    return result


@router.patch(
    "/{todo_id}",
    response_model=TodoResponse,
    status_code=status.HTTP_200_OK,
    description="Partially update a todo",
)
async def update_todo(
    todo_id: str,
    data: TodoUpdateRequest,
    service: TodoService = Depends(get_todo_service),
):
    result = await service.update(todo_id, data)

    if not result:
        raise NOT_FOUND

    return result


@router.delete(
    "/{todo_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    description="Soft delete a todo",
)
async def delete_todo(
    todo_id: str, repo: TodoRepository = Depends(get_todo_repository)
):
    deleted = await repo.soft_delete(todo_id)

    if not deleted:
        raise NOT_FOUND


@router.post(
    "/{todo_id}/regenerate-title",
    response_model=TodoResponse,
    status_code=status.HTTP_200_OK,
    description="Generate the title again, replacing the current one",
    dependencies=[Depends(limit_llm_calls)],
)
async def regenerate_title(
    todo_id: str, service: TodoService = Depends(get_todo_service)
):
    result = await service.regenerate_title(todo_id)

    if not result:
        raise NOT_FOUND

    return result


@router.post(
    "/{todo_id}/prioritize",
    response_model=TodoResponse,
    status_code=status.HTTP_200_OK,
    description="Recompute the priority: LLM signals plus a deterministic formula",
    dependencies=[Depends(limit_llm_calls)],
)
async def prioritize_todo(
    todo_id: str, service: TodoService = Depends(get_todo_service)
):
    result = await service.prioritize(todo_id)

    if not result:
        raise NOT_FOUND

    return result
