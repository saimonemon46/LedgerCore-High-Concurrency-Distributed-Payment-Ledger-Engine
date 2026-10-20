"""Outbox Relay Worker for LedgerCore.

Claims committed outbox records from PostgreSQL using SELECT FOR UPDATE SKIP LOCKED
and publishes them to the message broker with publisher confirmation, ensuring
zero message loss across process restarts and crashes.
"""

import asyncio
import logging
from typing import Any

from app.infrastructure.persistence.postgres.unit_of_work import PostgresUnitOfWork
from app.ports.message_broker_port import IMessageBrokerPort

logger = logging.getLogger("ledger_core.relay")


class OutboxRelay:
    """Polls transactional outbox records and reliably forwards them to a message broker."""

    def __init__(
        self,
        uow: PostgresUnitOfWork,
        broker: IMessageBrokerPort,
        topic: str = "ledger.events",
        batch_size: int = 50,
        lock_seconds: int = 30,
        max_retries: int = 5,
        poll_interval_seconds: float = 0.5,
    ) -> None:
        self.uow = uow
        self.broker = broker
        self.topic = topic
        self.batch_size = batch_size
        self.lock_seconds = lock_seconds
        self.max_retries = max_retries
        self.poll_interval = poll_interval_seconds
        self._running = False
        self._task: asyncio.Task[None] | None = None

    async def relay_batch(self) -> int:
        """Claims and publishes a single batch of outbox events.

        Returns count of published events.
        """
        # 1. Claim batch with row locks
        async with self.uow as uow:
            events = await uow.outbox.claim_pending_events(
                batch_size=self.batch_size,
                lock_seconds=self.lock_seconds,
            )
            await uow.commit()

        if not events:
            return 0

        published_count = 0
        for event in events:
            try:
                # 2. Publish to durable message broker
                headers: dict[str, Any] = {
                    "event_type": event.event_type,
                    "aggregate_id": event.aggregate_id,
                    "retry_count": event.retry_count,
                }
                confirmed = await self.broker.publish(
                    topic=self.topic,
                    message=event.payload,
                    headers=headers,
                    message_id=event.id,
                )

                if confirmed:
                    # 3. Mark published on broker acknowledgment
                    async with self.uow as pub_uow:
                        await pub_uow.outbox.mark_published(event.id)
                        await pub_uow.commit()
                    published_count += 1
                else:
                    raise RuntimeError("Broker did not confirm message publication.")

            except Exception as e:
                logger.error("Failed to publish outbox event %s: %s", event.id, e)
                async with self.uow as fail_uow:
                    await fail_uow.outbox.mark_failed(
                        event_id=event.id,
                        error_message=str(e),
                        max_retries=self.max_retries,
                    )
                    await fail_uow.commit()

        return published_count

    async def run_loop(self) -> None:
        """Continuous execution loop with dynamic idle backoff."""
        self._running = True
        logger.info("Outbox relay worker started on topic '%s'.", self.topic)
        while self._running:
            try:
                count = await self.relay_batch()
                if count == 0:
                    await asyncio.sleep(self.poll_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Error in outbox relay loop: %s", e)
                await asyncio.sleep(self.poll_interval * 2)

    def start(self) -> None:
        """Starts the relay worker as a background asyncio task."""
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self.run_loop())

    async def stop(self) -> None:
        """Gracefully stops the relay worker."""
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._task = None
        logger.info("Outbox relay worker stopped.")
