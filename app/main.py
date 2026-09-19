from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, status

from app.config import settings
from app.database.mongo_db import get_mongo_db, running_mongo_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    mongo_client = await running_mongo_db(app)
    try:
        yield
    finally:
        await mongo_client.close()
        print("Connection to mongo close")
        


if settings.ENV == "dev":
    app = FastAPI(title="LLM Enhanced TODO application", lifespan=lifespan)
else:
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)


@app.get("/health", status_code=status.HTTP_200_OK)
async def mongo_health_check(mongo_db=Depends(get_mongo_db)):
    try:
        await mongo_db.command("ping")
        return {"status": "healthy", "database": "MongoDB is connected and responding"}
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Mongo database failed",
        )
