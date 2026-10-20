"""Idempotent Event Consumer for LedgerCore.

Enforces consumer-side deduplication using the `consumer_processed_events` table,
ensuring at-least-once broker delivery is translated into exactly-once business side effects.
Routes poison-pill or repeatedly failing messages to a Dead-Letter Queue (DLQ).
"""

import logging
from collections.abc import Awaitable, Callable

from app.infrastructure.persistence.postgres.unit_of_work import PostgresUnitOfWork
from app.ports.message_broker_port import BrokerMessage, IMessageBrokerPort

logger = logging.getLogger("ledger_core.consumer")


class IdempotentEventConsumer:
    """Consumes messages idempotently with database deduplication and DLQ routing."""

    def __init__(
        self,
        consumer_name: str,
        uow: PostgresUnitOfWork,
        broker: IMessageBrokerPort,
        topic: str = "ledger.events",
        dlq_topic: str = "ledger.events.dlq",
        max_retries: int = 3,
        handler: Callable[[BrokerMessage], Awaitable[None]] | None = None,
    ) -> None:
        self.consumer_name = consumer_name
        self.uow = uow
        self.broker = broker
        self.topic = topic
        self.dlq_topic = dlq_topic
        self.max_retries = max_retries
        self.handler = handler
        self._retry_counts: dict[str, int] = {}
        self._processed_count = 0
        self._duplicate_skipped_count = 0

    @property
    def processed_count(self) -> int:
        return self._processed_count

    @property
    def duplicate_skipped_count(self) -> int:
        return self._duplicate_skipped_count

    async def handle_message(self, message: BrokerMessage) -> bool:
        """Processes a broker message idempotently.

        Returns True on success or duplicate (ACK).
        Returns False on unrecoverable failure (NACK / DLQ routing).
        """
        # 1. Deduplication check
        async with self.uow as uow:
            already_processed = await uow.consumer_dedup.is_processed(
                event_id=message.id,
                consumer_name=self.consumer_name,
            )

        if already_processed:
            logger.info(
                "Message %s already processed by consumer '%s'. Skipping duplicate (ACK).",
                message.id,
                self.consumer_name,
            )
            self._duplicate_skipped_count += 1
            return True

        # 2. Execute business handler
        try:
            if self.handler is not None:
                await self.handler(message)

            # 3. Persist deduplication entry upon successful handler completion
            async with self.uow as uow:
                await uow.consumer_dedup.record_processed(
                    event_id=message.id,
                    consumer_name=self.consumer_name,
                )
                await uow.commit()

            self._processed_count += 1
            self._retry_counts.pop(message.id, None)
            return True

        except Exception as e:
            attempts = self._retry_counts.get(message.id, 0) + 1
            self._retry_counts[message.id] = attempts
            logger.error(
                "Consumer '%s' failed processing message %s (attempt %d/%d): %s",
                self.consumer_name,
                message.id,
                attempts,
                self.max_retries,
                e,
            )

            if attempts >= self.max_retries:
                logger.critical(
                    "Message %s exceeded max retries (%d). Routing to DLQ '%s'.",
                    message.id,
                    self.max_retries,
                    self.dlq_topic,
                )
                return False  # Signals broker to route to DLQ

            # Allow retry on next delivery
            return False

    async def register(self) -> None:
        """Registers this consumer to subscribe to the configured broker topic."""
        await self.broker.subscribe(
            topic=self.topic,
            handler=self.handle_message,
            consumer_group=self.consumer_name,
            dlq_topic=self.dlq_topic,
        )
        logger.info(
            "Consumer '%s' subscribed to topic '%s' with DLQ '%s'.",
            self.consumer_name,
            self.topic,
            self.dlq_topic,
        )
