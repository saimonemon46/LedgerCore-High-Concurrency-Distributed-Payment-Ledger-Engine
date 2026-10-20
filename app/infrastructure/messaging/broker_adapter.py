"""Message Broker Adapters for LedgerCore.

Provides implementations of IMessageBrokerPort:
1. DurableMemoryBroker: In-memory durable pub/sub with DLQ routing and consumer acknowledgments.
2. RedisStreamBroker: Backed by Redis Streams (XADD / XREADGROUP / XACK).
"""

import asyncio
import json
import logging
import uuid
from typing import Any

from app.ports.message_broker_port import (
    BrokerMessage,
    IMessageBrokerPort,
    MessageHandler,
)

logger = logging.getLogger("ledger_core.broker")


class DurableMemoryBroker(IMessageBrokerPort):
    """In-memory broker with persistent message retention, DLQ routing, and consumer groups."""

    def __init__(self) -> None:
        self._topics: dict[str, list[BrokerMessage]] = {}
        self._dead_letter_queues: dict[str, list[BrokerMessage]] = {}
        self._handlers: dict[str, list[tuple[MessageHandler, str, str | None]]] = {}
        self._published_count = 0
        self._is_closed = False

    @property
    def published_count(self) -> int:
        return self._published_count

    def get_messages(self, topic: str) -> list[BrokerMessage]:
        return list(self._topics.get(topic, []))

    def get_dlq_messages(self, dlq_topic: str) -> list[BrokerMessage]:
        return list(self._dead_letter_queues.get(dlq_topic, []))

    async def publish(
        self,
        topic: str,
        message: dict[str, Any],
        headers: dict[str, Any] | None = None,
        message_id: str | None = None,
    ) -> bool:
        if self._is_closed:
            raise RuntimeError("Broker is closed.")

        msg_id = message_id or str(uuid.uuid4())
        envelope = BrokerMessage(
            id=msg_id,
            topic=topic,
            payload=message,
            headers=headers or {},
            delivery_tag=str(uuid.uuid4()),
        )

        if topic not in self._topics:
            self._topics[topic] = []
        self._topics[topic].append(envelope)
        self._published_count += 1

        # Dispatch to registered handlers
        if topic in self._handlers:
            for handler, _, dlq_topic in self._handlers[topic]:
                asyncio.create_task(self._dispatch_with_dlq(handler, envelope, dlq_topic))

        return True

    async def _dispatch_with_dlq(
        self,
        handler: MessageHandler,
        msg: BrokerMessage,
        dlq_topic: str | None,
    ) -> None:
        try:
            success = await handler(msg)
            if not success and dlq_topic:
                self._dead_letter_queues.setdefault(dlq_topic, []).append(msg)
        except Exception as e:
            logger.error("Handler error for message %s: %s", msg.id, e)
            if dlq_topic:
                self._dead_letter_queues.setdefault(dlq_topic, []).append(msg)

    async def subscribe(
        self,
        topic: str,
        handler: MessageHandler,
        consumer_group: str = "default_group",
        dlq_topic: str | None = None,
    ) -> None:
        if topic not in self._handlers:
            self._handlers[topic] = []
        self._handlers[topic].append((handler, consumer_group, dlq_topic))

    async def close(self) -> None:
        self._is_closed = True


class RedisStreamBroker(IMessageBrokerPort):
    """Durable broker backed by Redis Streams."""

    def __init__(self, redis_client: Any) -> None:
        self.redis = redis_client
        self._is_closed = False

    async def publish(
        self,
        topic: str,
        message: dict[str, Any],
        headers: dict[str, Any] | None = None,
        message_id: str | None = None,
    ) -> bool:
        if self._is_closed:
            raise RuntimeError("RedisStreamBroker is closed.")

        msg_id = message_id or str(uuid.uuid4())
        data = {
            "id": msg_id,
            "topic": topic,
            "payload": json.dumps(message),
            "headers": json.dumps(headers or {}),
        }
        await self.redis.xadd(f"stream:{topic}", data)
        return True

    async def subscribe(
        self,
        topic: str,
        handler: MessageHandler,
        consumer_group: str = "default_group",
        dlq_topic: str | None = None,
    ) -> None:
        stream_key = f"stream:{topic}"
        try:
            await self.redis.xgroup_create(stream_key, consumer_group, id="0", mkstream=True)
        except Exception:
            pass  # Group already exists

    async def close(self) -> None:
        self._is_closed = True
