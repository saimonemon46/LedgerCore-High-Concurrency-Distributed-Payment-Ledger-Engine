"""Outbox Port for LedgerCore.

Defines the contract for persisting domain events within the atomic database
transaction and safely polling them via distributed claim mechanisms.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class OutboxEvent:
    """Domain representation of a persistent outbox record."""

    id: str
    aggregate_id: str
    event_type: str
    payload: dict[str, Any]
    status: str
    retry_count: int
    created_at: datetime
    updated_at: datetime
    locked_until: datetime | None = None
    error_message: str | None = None


class IOutboxRepository(ABC):
    """Abstract port for outbox table persistence and queue relay claiming."""

    @abstractmethod
    async def save_event(
        self,
        aggregate_id: str,
        event_type: str,
        payload: dict[str, Any],
        event_id: str | None = None,
    ) -> str:
        """Persists an outbox event within the active unit-of-work transaction session."""
        pass

    @abstractmethod
    async def claim_pending_events(
        self,
        batch_size: int = 50,
        lock_seconds: int = 30,
    ) -> list[OutboxEvent]:
        """Atomically claims a batch of pending events using SELECT FOR UPDATE SKIP LOCKED."""
        pass

    @abstractmethod
    async def mark_published(self, event_id: str) -> None:
        """Marks an outbox event as successfully published."""
        pass

    @abstractmethod
    async def mark_failed(
        self,
        event_id: str,
        error_message: str,
        max_retries: int = 5,
    ) -> None:
        """Records a publication failure and increments retry count or dead-letters the record."""
        pass
