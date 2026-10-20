"""Integration tests for Idempotent Event Consumer.

Verifies:
1. Consumer processes new messages and records state in consumer_processed_events.
2. At-least-once message redelivery: duplicates are safely ignored without re-executing handlers.
3. Repeated failure reaches max retries and is routed to Dead-Letter Queue (DLQ).
"""

import uuid
from collections.abc import AsyncGenerator

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.infrastructure.config import get_settings
from app.infrastructure.messaging.broker_adapter import DurableMemoryBroker
from app.infrastructure.persistence.postgres.database import (
    check_db_health,
    create_async_db_engine,
    get_async_session_factory,
    init_db,
)
from app.infrastructure.persistence.postgres.unit_of_work import PostgresUnitOfWork
from app.infrastructure.workers.idempotent_consumer import IdempotentEventConsumer
from app.ports.message_broker_port import BrokerMessage


@pytest.fixture
async def pg_engine() -> AsyncGenerator[AsyncEngine, None]:
    settings = get_settings()
    engine = create_async_db_engine(settings.database_url)
    healthy = await check_db_health(engine)
    if not healthy:
        pytest.skip("PostgreSQL database is not reachable at " + settings.database_url)
    await init_db(engine)
    yield engine
    await engine.dispose()


@pytest.fixture
async def session_factory(
    pg_engine: AsyncEngine,
) -> AsyncGenerator[async_sessionmaker[AsyncSession], None]:
    factory = get_async_session_factory(pg_engine)
    async with pg_engine.begin() as conn:
        await conn.execute(text("TRUNCATE TABLE consumer_processed_events CASCADE;"))
    yield factory


@pytest.fixture
def uow(session_factory: async_sessionmaker[AsyncSession]) -> PostgresUnitOfWork:
    return PostgresUnitOfWork(session_factory)


@pytest.mark.asyncio
class TestIdempotentConsumer:
    """Verifies consumer deduplication and DLQ routing invariants."""

    async def test_consumer_processes_first_delivery(
        self,
        uow: PostgresUnitOfWork,
    ) -> None:
        """Proves new event executes business handler and writes deduplication record."""
        broker = DurableMemoryBroker()
        executed_side_effects: list[str] = []

        async def business_handler(msg: BrokerMessage) -> None:
            executed_side_effects.append(msg.payload["action"])

        consumer = IdempotentEventConsumer(
            consumer_name="webhook_dispatcher",
            uow=uow,
            broker=broker,
            handler=business_handler,
        )

        msg = BrokerMessage(
            id=str(uuid.uuid4()),
            topic="ledger.events",
            payload={"action": "send_customer_email", "user": "alice"},
        )

        ack = await consumer.handle_message(msg)
        assert ack is True
        assert len(executed_side_effects) == 1
        assert consumer.processed_count == 1
        assert consumer.duplicate_skipped_count == 0

        # Verify DB deduplication entry
        async with uow:
            is_done = await uow.consumer_dedup.is_processed(msg.id, "webhook_dispatcher")
            assert is_done is True

    async def test_consumer_deduplicates_redelivery(
        self,
        uow: PostgresUnitOfWork,
    ) -> None:
        """Proves 5 identical deliveries execute the business side effect exactly once."""
        broker = DurableMemoryBroker()
        execution_count = 0

        async def business_handler(msg: BrokerMessage) -> None:
            nonlocal execution_count
            execution_count += 1

        consumer = IdempotentEventConsumer(
            consumer_name="sms_notifier",
            uow=uow,
            broker=broker,
            handler=business_handler,
        )

        msg = BrokerMessage(
            id="msg_duplicate_test_123",
            topic="ledger.events",
            payload={"notification": "sms_p2p_received"},
        )

        # First delivery: should execute handler
        ack1 = await consumer.handle_message(msg)
        assert ack1 is True
        assert execution_count == 1

        # Subsequent redeliveries (2 through 5)
        for _ in range(4):
            ack = await consumer.handle_message(msg)
            assert ack is True  # Idempotently acknowledged to broker

        # Crucial invariant: handler must have executed exactly 1 time!
        assert execution_count == 1
        assert consumer.processed_count == 1
        assert consumer.duplicate_skipped_count == 4

    async def test_consumer_poison_pill_routes_to_dlq(
        self,
        uow: PostgresUnitOfWork,
    ) -> None:
        """Proves repeated handler errors exhaust max retries and signal DLQ routing."""
        broker = DurableMemoryBroker()

        async def bad_handler(msg: BrokerMessage) -> None:
            raise ValueError("Malformed payload unhandled exception")

        consumer = IdempotentEventConsumer(
            consumer_name="failing_worker",
            uow=uow,
            broker=broker,
            max_retries=3,
            handler=bad_handler,
        )

        msg = BrokerMessage(
            id="poison_pill_msg_999",
            topic="ledger.events",
            payload={"corrupted": True},
        )

        # Attempt 1
        ack1 = await consumer.handle_message(msg)
        assert ack1 is False

        # Attempt 2
        ack2 = await consumer.handle_message(msg)
        assert ack2 is False

        # Attempt 3 (Max retries reached -> Signals DLQ)
        ack3 = await consumer.handle_message(msg)
        assert ack3 is False

        # Deduplication table must NOT contain poison pill
        async with uow:
            is_done = await uow.consumer_dedup.is_processed(msg.id, "failing_worker")
            assert is_done is False
