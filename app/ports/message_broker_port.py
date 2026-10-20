"""Message Broker Port for LedgerCore.

Defines the contract for publishing committed outbox events to durable message brokers
(RabbitMQ / Redis Streams) and consuming them with delivery acknowledgments and dead-letter routing.
"""

from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


@dataclass(frozen=True)
class BrokerMessage:
    """Standardized envelope for messages dispatched through the broker."""

    id: str
    topic: str
    payload: dict[str, Any]
    headers: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    delivery_tag: str | None = None


MessageHandler = Callable[[BrokerMessage], Awaitable[bool]]


class IMessageBrokerPort(ABC):
    """Abstract port for durable asynchronous message dissemination."""

    @abstractmethod
    async def publish(
        self,
        topic: str,
        message: dict[str, Any],
        headers: dict[str, Any] | None = None,
        message_id: str | None = None,
    ) -> bool:
        """Publishes a message to a durable queue or exchange with publisher confirmation."""
        pass

    @abstractmethod
    async def subscribe(
        self,
        topic: str,
        handler: MessageHandler,
        consumer_group: str = "default_group",
        dlq_topic: str | None = None,
    ) -> None:
        """Subscribes an idempotent message handler to a topic with DLQ routing."""
        pass

    @abstractmethod
    async def close(self) -> None:
        """Gracefully closes connections and flushes buffers."""
        pass
