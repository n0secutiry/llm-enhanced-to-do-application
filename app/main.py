from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, status
from loguru import logger

from app.config import settings
from app.database.mongo_db import get_mongo_db, running_mongo_db
from app.middleware.loggin_middleware import LoggingMiddleware
from app.v1.todo.routers import router as todo_router

logger.add("/logs/app.log")


@asynccontextmanager
async def lifespan(app: FastAPI):
    mongo_client = await running_mongo_db(app)
    try:
        yield
    finally:
        await mongo_client.close()
        logger.info("Connection to mongodb close")


if settings.ENV == "dev":
    app = FastAPI(title="LLM Enhanced TODO application", lifespan=lifespan)
else:
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)


@app.get("/health", status_code=status.HTTP_200_OK)
async def mongo_health_check(mongo_db=Depends(get_mongo_db)):
    try:
        await mongo_db.command("ping")
        return {"status": "healthy", "database": "MongoDB is connected and responding"}
    except Exception as err:
        logger.error(f"Error with mongodb {err}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Mongo database failed",
        )


app.add_middleware(LoggingMiddleware)

app.include_router(todo_router)
