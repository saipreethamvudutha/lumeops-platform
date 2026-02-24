"""
Redis Pub/Sub manager for real-time event broadcasting.

Architecture:
    When an inference is ingested, the ingest endpoint publishes an event
    to a tenant-scoped Redis channel:  lumeops:events:{tenant_id}

    WebSocket connections subscribe to their authenticated tenant's channel
    and forward messages to the browser in real-time.

Why Redis Pub/Sub (not polling)?
    - Sub-millisecond latency vs 30-60s polling intervals
    - No wasted database queries when nothing has changed
    - Scales horizontally: multiple API server instances can share events
      through the same Redis broker
    - Tenant isolation: each tenant has its own channel, so events
      never leak across organizational boundaries

Why not a dedicated message broker (RabbitMQ, Kafka)?
    - We already have Redis for rate limiting — no new infrastructure
    - Redis pub/sub is ephemeral (fire-and-forget), which matches our
      use case: dashboard updates are nice-to-have, not critical
    - If a client disconnects and reconnects, they fetch fresh data
      from the REST API — no need for message persistence
"""

from __future__ import annotations

import asyncio
from typing import Any, AsyncGenerator, Callable

import redis.asyncio as aioredis

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger("pubsub")

# Channel prefix for tenant-scoped events
CHANNEL_PREFIX = "lumeops:events:"


class EventPublisher:
    """
    Publishes events to tenant-scoped Redis channels.

    Used by the ingest endpoint (and future endpoints) to broadcast
    real-time events to connected WebSocket clients.

    Design: singleton pattern with lazy connection. The publisher
    maintains a single Redis connection that is reused across all
    publish calls. If Redis is unavailable, publishing fails silently
    (graceful degradation — the inference is still stored, just no
    real-time push).
    """

    def __init__(self) -> None:
        self._redis: aioredis.Redis | None = None

    async def connect(self) -> None:
        """Initialize the Redis connection for publishing."""
        if self._redis is not None:
            return
        try:
            settings = get_settings()
            self._redis = aioredis.from_url(
                settings.REDIS_URL,
                decode_responses=True,
                max_connections=10,
            )
            # Verify connection
            await self._redis.ping()
            logger.info("pubsub_publisher_connected")
        except Exception as exc:
            logger.warning("pubsub_publisher_connect_failed", error=str(exc))
            self._redis = None

    async def close(self) -> None:
        """Close the Redis connection."""
        if self._redis:
            await self._redis.aclose()
            self._redis = None
            logger.info("pubsub_publisher_closed")

    async def publish(
        self, tenant_id: str, event_type: str, payload: dict[str, Any]
    ) -> bool:
        """
        Publish an event to a tenant's channel.

        Args:
            tenant_id: UUID of the tenant (channel isolation)
            event_type: Event name (e.g., "inference_received", "alert_created")
            payload: JSON-serializable event data

        Returns:
            True if published successfully, False otherwise.
        """
        if self._redis is None:
            await self.connect()
        if self._redis is None:
            return False

        try:
            import orjson

            channel = f"{CHANNEL_PREFIX}{tenant_id}"
            message = orjson.dumps({
                "type": event_type,
                "data": payload,
            }).decode()

            subscribers = await self._redis.publish(channel, message)
            logger.debug(
                "event_published",
                channel=channel,
                event_type=event_type,
                subscribers=subscribers,
            )
            return True

        except Exception as exc:
            logger.warning(
                "pubsub_publish_failed",
                event_type=event_type,
                error=str(exc),
            )
            return False


class EventSubscriber:
    """
    Subscribes to a tenant's event channel and yields messages.

    Used by WebSocket connections to receive real-time events.
    Each WebSocket connection creates its own subscriber instance,
    scoped to the authenticated tenant's channel.

    Design: each subscriber gets its own Redis connection (required
    by Redis pub/sub — a connection in subscribe mode cannot execute
    other commands). When the WebSocket disconnects, the subscriber
    is cleaned up.
    """

    def __init__(self, tenant_id: str) -> None:
        self.tenant_id = tenant_id
        self.channel = f"{CHANNEL_PREFIX}{tenant_id}"
        self._redis: aioredis.Redis | None = None
        self._pubsub: aioredis.client.PubSub | None = None

    async def connect(self) -> bool:
        """Subscribe to the tenant's event channel."""
        try:
            settings = get_settings()
            self._redis = aioredis.from_url(
                settings.REDIS_URL,
                decode_responses=True,
            )
            self._pubsub = self._redis.pubsub()
            await self._pubsub.subscribe(self.channel)
            logger.info(
                "pubsub_subscriber_connected",
                channel=self.channel,
            )
            return True
        except Exception as exc:
            logger.warning(
                "pubsub_subscriber_connect_failed",
                channel=self.channel,
                error=str(exc),
            )
            return False

    async def listen(self) -> AsyncGenerator[dict[str, Any], None]:
        """
        Yield parsed event messages as they arrive.

        This is an async generator — the WebSocket handler iterates
        over it, sending each event to the browser.

        The generator runs until the subscriber is closed (which
        happens when the WebSocket disconnects).
        """
        if self._pubsub is None:
            return

        try:
            async for message in self._pubsub.listen():
                if message["type"] != "message":
                    continue

                try:
                    import orjson
                    event = orjson.loads(message["data"])
                    yield event
                except Exception:
                    # Skip malformed messages
                    continue
        except asyncio.CancelledError:
            # Normal shutdown — WebSocket disconnected
            pass
        except Exception as exc:
            logger.warning(
                "pubsub_listener_error",
                channel=self.channel,
                error=str(exc),
            )

    async def close(self) -> None:
        """Unsubscribe and close the Redis connection."""
        try:
            if self._pubsub:
                await self._pubsub.unsubscribe(self.channel)
                await self._pubsub.aclose()
            if self._redis:
                await self._redis.aclose()
            logger.debug(
                "pubsub_subscriber_closed",
                channel=self.channel,
            )
        except Exception:
            pass  # Best-effort cleanup


# ── Singleton publisher ────────────────────────────────────────────────
# Created once at import time, connected during app startup (lifespan).
event_publisher = EventPublisher()
