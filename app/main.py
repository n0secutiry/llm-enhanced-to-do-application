from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, status
from loguru import logger

from app.config import settings
from app.database.mongo_db import get_mongo_db, running_mongo_db
from app.middleware.loggin_middleware import LoggingMiddleware
from app.v1.llm.ollama import get_ollama_client, running_ollama
from app.v1.llm.routers import router as llm_router
from app.v1.llm.tracing import get_langfuse_client, shutdown_tracing
from app.v1.todo.routers import router as todo_router

logger.add(settings.LOG_FILE)


@asynccontextmanager
async def lifespan(app: FastAPI):
    ollama_client = await running_ollama(app)
    mongo_client = await running_mongo_db(app)
    get_langfuse_client()

    try:
        yield
    finally:
        await mongo_client.close()
        logger.info("Connection to mongodb close")

        if ollama_client:
            await ollama_client.close()
            logger.info("Connection to Ollama close")

        shutdown_tracing()


if settings.ENV == "dev":
    app = FastAPI(title="LLM Enhanced TODO application", lifespan=lifespan)
else:
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)


@app.get(
    "/health",
    status_code=status.HTTP_200_OK,
    tags=["Service"],
    description="Checks MongoDB and reports whether the LLM is reachable",
)
async def health_check(
    mongo_db=Depends(get_mongo_db),
    ollama_client=Depends(get_ollama_client),
):
    try:
        await mongo_db.command("ping")
    except Exception as err:
        logger.error(f"Error with mongodb {err}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Mongo database failed",
        )

    # The LLM is optional: the app stays healthy without it, the flag only
    # tells the caller whether titles will be generated right now.
    return {
        "status": "healthy",
        "database": "MongoDB is connected and responding",
        "llm": "available" if ollama_client else "unavailable, using fallbacks",
    }


app.add_middleware(LoggingMiddleware)

app.include_router(todo_router)
app.include_router(llm_router)
