"""Integration tests for Outbox Relay worker.

Verifies:
1. Outbox relay atomically claims pending events with SKIP LOCKED and publishes to broker.
2. Crash recovery: events committed in DB survive process restart and are forwarded upon recovery.
3. Poison-pill / broker failure retry backoff and transition to DEAD_LETTER status.
"""

import uuid
from collections.abc import AsyncGenerator

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.infrastructure.config import get_settings
from app.infrastructure.messaging.broker_adapter import DurableMemoryBroker
from app.infrastructure.persistence.postgres.database import (
    check_db_health,
    create_async_db_engine,
    get_async_session_factory,
    init_db,
)
from app.infrastructure.persistence.postgres.models import OutboxEventModel
from app.infrastructure.persistence.postgres.unit_of_work import PostgresUnitOfWork
from app.infrastructure.workers.outbox_relay import OutboxRelay


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
        await conn.execute(text("TRUNCATE TABLE outbox_events CASCADE;"))
    yield factory


@pytest.fixture
def uow(session_factory: async_sessionmaker[AsyncSession]) -> PostgresUnitOfWork:
    return PostgresUnitOfWork(session_factory)


@pytest.mark.asyncio
class TestOutboxRelay:
    """Verifies durable outbox relay operations and crash recovery."""

    async def test_relay_claims_and_publishes_pending_events(
        self,
        uow: PostgresUnitOfWork,
    ) -> None:
        """Proves relay claims pending outbox rows and marks them PUBLISHED on broker ACK."""
        broker = DurableMemoryBroker()

        # 1. Seed 3 pending outbox events
        async with uow:
            for i in range(3):
                await uow.outbox.save_event(
                    aggregate_id=f"tx_relay_{i}",
                    event_type="transaction.settled",
                    payload={"tx_index": i, "amount": "100.00"},
                )
            await uow.commit()

        # 2. Run relay batch
        relay = OutboxRelay(uow=uow, broker=broker, batch_size=10)
        published_count = await relay.relay_batch()

        assert published_count == 3
        assert broker.published_count == 3

        # 3. Verify all DB records marked PUBLISHED
        async with uow:
            assert uow.session is not None
            stmt = select(OutboxEventModel).order_by(OutboxEventModel.created_at.asc())
            res = await uow.session.execute(stmt)
            records = list(res.scalars().all())
            assert len(records) == 3
            for r in records:
                assert r.status == "PUBLISHED"
                assert r.locked_until is None

    async def test_relay_crash_recovery(
        self,
        uow: PostgresUnitOfWork,
    ) -> None:
        """Simulates application crash after DB commit: relay recovers and publishes on restart."""
        # 1. Simulate un-forwarded event written by a crashed application instance
        ev_id = str(uuid.uuid4())
        async with uow:
            await uow.outbox.save_event(
                aggregate_id="tx_crashed_app",
                event_type="transaction.settled",
                payload={"status": "crashed_instance_recovered"},
                event_id=ev_id,
            )
            await uow.commit()

        # 2. New relay instance starts up
        fresh_broker = DurableMemoryBroker()
        relay = OutboxRelay(uow=uow, broker=fresh_broker)

        count = await relay.relay_batch()
        assert count == 1
        assert fresh_broker.published_count == 1

        messages = fresh_broker.get_messages("ledger.events")
        assert len(messages) == 1
        assert messages[0].id == ev_id
        assert messages[0].payload["status"] == "crashed_instance_recovered"

    async def test_relay_max_retries_routes_to_dead_letter(
        self,
        uow: PostgresUnitOfWork,
    ) -> None:
        """Proves repeated broker failure transitions outbox row to DEAD_LETTER status."""

        class FailingBroker(DurableMemoryBroker):
            async def publish(self, *args, **kwargs) -> bool:
                raise ConnectionError("Simulated network drop to message broker")

        failing_broker = FailingBroker()
        ev_id = str(uuid.uuid4())

        # Seed 1 event
        async with uow:
            await uow.outbox.save_event(
                aggregate_id="tx_fail_dlq",
                event_type="transaction.settled",
                payload={"fail": True},
                event_id=ev_id,
            )
            await uow.commit()

        # Max retries = 2
        relay = OutboxRelay(uow=uow, broker=failing_broker, max_retries=2)

        # Attempt 1: should stay PENDING, retry_count = 1
        await relay.relay_batch()
        async with uow:
            assert uow.session is not None
            stmt = select(OutboxEventModel).where(OutboxEventModel.id == ev_id)
            rec = (await uow.session.execute(stmt)).scalar_one()
            assert rec.status == "PENDING"
            assert rec.retry_count == 1

        # Attempt 2: should transition to DEAD_LETTER
        await relay.relay_batch()
        async with uow:
            assert uow.session is not None
            stmt = select(OutboxEventModel).where(OutboxEventModel.id == ev_id)
            rec = (await uow.session.execute(stmt)).scalar_one()
            assert rec.status == "DEAD_LETTER"
            assert rec.retry_count == 2
            assert "Simulated network drop" in (rec.error_message or "")
