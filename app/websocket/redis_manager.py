import asyncio
import json
import logging
from uuid import UUID

from redis.exceptions import RedisError

from app.database.redis import redis_client
from app.websocket.connection_manager import manager as connection_manager

logger = logging.getLogger(__name__)


class RedisPubSubManager:
    CHANNEL = "live_chat:events"
    INITIAL_RETRY_DELAY = 1
    MAX_RETRY_DELAY = 30

    def __init__(self) -> None:
        self.pubsub = None
        self.listener_task: asyncio.Task | None = None
        self._stopping = False

    async def start(self) -> None:
        if self.listener_task and not self.listener_task.done():
            return

        self._stopping = False
        self.listener_task = asyncio.create_task(self._listen())

        logger.info("Redis Pub/Sub listener started")

    async def stop(self) -> None:
        self._stopping = True

        if self.listener_task:
            self.listener_task.cancel()

            try:
                await self.listener_task
            except asyncio.CancelledError:
                pass

            self.listener_task = None

        logger.info("Redis Pub/Sub listener stopped")

    async def publish_to_user(
        self,
        user_id: UUID,
        message: dict,
    ) -> None:
        event = {
            "target": "user",
            "user_id": str(user_id),
            "message": message,
        }

        await redis_client.publish(
            self.CHANNEL,
            json.dumps(event),
        )

    async def publish_broadcast(
        self,
        message: dict,
    ) -> None:
        event = {
            "target": "broadcast",
            "message": message,
        }

        await redis_client.publish(
            self.CHANNEL,
            json.dumps(event),
        )

    async def _listen(self) -> None:
        retry_delay = self.INITIAL_RETRY_DELAY

        while not self._stopping:
            connection_started_at = asyncio.get_running_loop().time()

            try:
                self.pubsub = redis_client.pubsub()

                await self.pubsub.subscribe(self.CHANNEL)

                logger.info(
                    "Subscribed to Redis channel: %s",
                    self.CHANNEL,
                )

                async for event in self.pubsub.listen():
                    if self._stopping:
                        break

                    if event["type"] != "message":
                        continue

                    await self._process_event(event["data"])

                if not self._stopping:
                    logger.warning(
                        "Redis Pub/Sub listener disconnected"
                    )

            except asyncio.CancelledError:
                raise

            except RedisError:
                logger.exception(
                    "Redis Pub/Sub connection failed"
                )

            finally:
                if self.pubsub:
                    try:
                        await self.pubsub.unsubscribe(self.CHANNEL)
                        await self.pubsub.aclose()
                    except RedisError:
                        logger.exception(
                            "Error closing Redis Pub/Sub connection"
                        )
                    finally:
                        self.pubsub = None

            if self._stopping:
                break

            connection_duration = (
                asyncio.get_running_loop().time()
                - connection_started_at
            )

            if connection_duration >= 60:
                retry_delay = self.INITIAL_RETRY_DELAY

            logger.info(
                "Reconnecting to Redis Pub/Sub in %s seconds",
                retry_delay,
            )

            await asyncio.sleep(retry_delay)

            retry_delay = min(
                retry_delay * 2,
                self.MAX_RETRY_DELAY,
            )

    async def _process_event(self, raw_data: str) -> None:
        try:
            payload = json.loads(raw_data)

            target = payload["target"]
            message = payload["message"]

            if target == "user":
                user_id = UUID(payload["user_id"])

                await connection_manager.send_to_user(
                    user_id=user_id,
                    message=message,
                )

            elif target == "broadcast":
                await connection_manager.broadcast(message)

            else:
                logger.warning(
                    "Unknown Redis Pub/Sub target: %s",
                    target,
                )

        except (ValueError, KeyError, TypeError):
            logger.exception(
                "Invalid Redis Pub/Sub event"
            )


redis_pubsub_manager = RedisPubSubManager()