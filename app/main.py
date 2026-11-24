
import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from redis.exceptions import RedisError
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.router import router as api_v1_router
from app.config import settings
from app.core.logging import setup_logging
from app.database.connection import engine
from app.database.dependencies import get_db
from app.database.redis import redis_client
from app.managers.presence_manager import PresenceManager
from app.websocket.redis_manager import redis_pubsub_manager

setup_logging()

logger = logging.getLogger(__name__)

PRESENCE_CLEANUP_INTERVAL = 10


async def cleanup_stale_presence() -> None:
    while True:
        try:
            await PresenceManager.cleanup_expired_users()

            processed_users = (
                await PresenceManager.process_pending_offline_users()
            )

            if processed_users:
                logger.info(
                    "Processed %s pending offline presence events",
                    len(processed_users),
                )

        except RedisError:
            logger.exception("Stale presence cleanup failed")

        except SQLAlchemyError:
            logger.exception(
                "Database error during stale presence cleanup"
            )

        await asyncio.sleep(PRESENCE_CLEANUP_INTERVAL)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Application starting")

    cleanup_task = None

    try:
        await redis_client.ping()
        logger.info("Redis connection established")

        await redis_pubsub_manager.start()
        logger.info("Redis Pub/Sub started")

        cleanup_task = asyncio.create_task(
            cleanup_stale_presence(),
            name="stale-presence-cleanup",
        )

        logger.info("Stale presence cleanup task started")

        yield

    finally:
        if cleanup_task:
            cleanup_task.cancel()

            try:
                await cleanup_task
            except asyncio.CancelledError:
                pass

        await redis_pubsub_manager.stop()
        await redis_client.aclose()
        await engine.dispose()

        logger.info("Redis and database connections closed")


app = FastAPI(
    title=settings.APP_NAME,
    debug=settings.DEBUG,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

app.include_router(api_v1_router)


@app.get("/")
async def root():
    return {
        "message": "Live Chat System API is running",
        "version": "1.0.0",
    }


@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "application": settings.APP_NAME,
        "environment": settings.ENVIRONMENT,
    }


@app.get("/health/database")
async def database_health_check(
    db: Annotated[AsyncSession, Depends(get_db)],
):
    try:
        await db.execute(text("SELECT 1"))

        return {
            "database": "connected",
            "session": "working",
        }

    except SQLAlchemyError:
        logger.exception("Database health check failed")

        raise HTTPException(
            status_code=503,
            detail="Database connection unavailable",
        ) from None
