"""Integration tests for Transactional Outbox atomicity.

Verifies:
1. Outbox events are written inside the exact same database transaction as the transfer.
2. Complete rollback: if transfer fails, outbox record is rolled back (0 ghost events).
"""

from collections.abc import AsyncGenerator
from decimal import Decimal

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.application.use_cases.execute_transfer import TransferCommand
from app.application.use_cases.execute_transfer_async import (
    AsyncExecuteTransferUseCase,
)
from app.domain.exceptions import InsufficientFundsError
from app.domain.models import Account, AccountStatus
from app.domain.value_objects import Currency, Money
from app.infrastructure.config import get_settings
from app.infrastructure.persistence.postgres.database import (
    check_db_health,
    create_async_db_engine,
    get_async_session_factory,
    init_db,
)
from app.infrastructure.persistence.postgres.models import OutboxEventModel
from app.infrastructure.persistence.postgres.unit_of_work import PostgresUnitOfWork


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
        await conn.execute(
            text(
                "TRUNCATE TABLE outbox_events, consumer_processed_events, "
                "ledger_entries, transactions, accounts CASCADE;"
            )
        )
    yield factory


@pytest.fixture
def uow(session_factory: async_sessionmaker[AsyncSession]) -> PostgresUnitOfWork:
    return PostgresUnitOfWork(session_factory)


@pytest.mark.asyncio
class TestOutboxAtomicity:
    """Verifies all-or-nothing transactional outbox guarantees."""

    async def test_outbox_event_persisted_atomically_on_transfer_success(
        self,
        uow: PostgresUnitOfWork,
    ) -> None:
        """Proves outbox row is committed in the same transaction as transfer balance updates."""
        # 1. Seed accounts
        async with uow:
            acc_a = Account(
                account_id="ACC-OUTBOX-SRC",
                owner_name="Alice",
                balance=Money(Decimal("500.00"), Currency.USD),
                status=AccountStatus.ACTIVE,
            )
            acc_b = Account(
                account_id="ACC-OUTBOX-DEST",
                owner_name="Bob",
                balance=Money(Decimal("0.00"), Currency.USD),
                status=AccountStatus.ACTIVE,
            )
            await uow.accounts.save(acc_a)
            await uow.accounts.save(acc_b)
            await uow.commit()

        # 2. Execute transfer
        use_case = AsyncExecuteTransferUseCase(uow=uow, require_idempotency=True)
        cmd = TransferCommand(
            from_account_id="ACC-OUTBOX-SRC",
            to_account_id="ACC-OUTBOX-DEST",
            amount=Decimal("150.00"),
            currency="USD",
            idempotency_key="idemp_outbox_test_01",
        )
        result = await use_case.execute(cmd)
        assert result.status == "SETTLED"

        # 3. Verify outbox table has the event
        async with uow:
            assert uow.session is not None
            stmt = select(OutboxEventModel).where(
                OutboxEventModel.aggregate_id == result.transaction_id
            )
            res = await uow.session.execute(stmt)
            event_rec = res.scalar_one_or_none()

            assert event_rec is not None
            assert event_rec.status == "PENDING"
            assert event_rec.event_type == "transaction.settled"
            assert event_rec.payload["amount"] == "150.00"
            assert event_rec.payload["from_account_id"] == "ACC-OUTBOX-SRC"
            assert event_rec.payload["to_account_id"] == "ACC-OUTBOX-DEST"

    async def test_outbox_event_rolled_back_on_insufficient_funds(
        self,
        uow: PostgresUnitOfWork,
    ) -> None:
        """Proves outbox row is rolled back with zero side-effects if transfer fails."""
        # 1. Seed account with low balance
        async with uow:
            acc_a = Account(
                account_id="ACC-OUTBOX-BROKE",
                owner_name="Broke Sender",
                balance=Money(Decimal("20.00"), Currency.USD),
                status=AccountStatus.ACTIVE,
            )
            acc_b = Account(
                account_id="ACC-OUTBOX-RECV",
                owner_name="Receiver",
                balance=Money(Decimal("0.00"), Currency.USD),
                status=AccountStatus.ACTIVE,
            )
            await uow.accounts.save(acc_a)
            await uow.accounts.save(acc_b)
            await uow.commit()

        # 2. Attempt transfer of 500.00
        use_case = AsyncExecuteTransferUseCase(uow=uow)
        cmd = TransferCommand(
            from_account_id="ACC-OUTBOX-BROKE",
            to_account_id="ACC-OUTBOX-RECV",
            amount=Decimal("500.00"),
            currency="USD",
        )

        with pytest.raises(InsufficientFundsError):
            await use_case.execute(cmd)

        # 3. Verify ZERO outbox events were committed
        async with uow:
            assert uow.session is not None
            stmt = select(OutboxEventModel)
            res = await uow.session.execute(stmt)
            all_events = list(res.scalars().all())
            assert len(all_events) == 0
