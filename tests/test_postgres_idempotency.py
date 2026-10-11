"""Integration and torture tests for PostgreSQL-backed durable idempotency engine.

Verifies:
1. Exact-once replay: Duplicate requests with same key return cached receipt.
2. Cryptographic payload validation: Reusing key with mutated payload raises error.
3. In-flight race gate: Concurrent requests with identical key reject duplicates.
4. Failure resilience: Failed executions mark status FAILED and allow retry.
5. Multi-tenant isolation: Identical keys under distinct tenant IDs execute independently.
"""

from collections.abc import AsyncGenerator
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.application.exceptions import (
    IdempotencyInFlightError,
    IdempotencyPayloadMismatchError,
)
from app.application.fingerprint import (
    compute_transfer_fingerprint,
)
from app.application.use_cases.execute_transfer import TransferCommand
from app.application.use_cases.execute_transfer_async import (
    AsyncExecuteTransferUseCase,
)
from app.domain.exceptions import InsufficientFundsError
from app.domain.value_objects import Currency
from app.infrastructure.config import get_settings
from app.infrastructure.persistence.postgres.database import (
    check_db_health,
    create_async_db_engine,
    get_async_session_factory,
    init_db,
)
from app.infrastructure.persistence.postgres.models import AccountModel
from app.infrastructure.persistence.postgres.repositories import (
    PostgresIdempotencyRepository,
)
from app.infrastructure.persistence.postgres.unit_of_work import PostgresUnitOfWork


@pytest.fixture
async def pg_engine() -> AsyncGenerator[AsyncEngine, None]:
    """Provides an active PostgreSQL async engine and verifies connectivity."""
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
    """Provides session factory and cleans up tables between tests."""
    factory = get_async_session_factory(pg_engine)
    async with pg_engine.begin() as conn:
        await conn.execute(
            text(
                "TRUNCATE TABLE idempotency_records, ledger_entries, "
                "transactions, accounts CASCADE;"
            )
        )
    yield factory


@pytest.fixture
def uow(session_factory: async_sessionmaker[AsyncSession]) -> PostgresUnitOfWork:
    """Provides a fresh PostgresUnitOfWork."""
    return PostgresUnitOfWork(session_factory)


@pytest.mark.asyncio
class TestPostgresDurableIdempotency:
    """Torture test suite for PostgreSQL durable idempotency engine."""

    async def _seed_account(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        account_id: str,
        balance: Decimal,
        owner: str = "User",
        currency: str = "USD",
    ) -> None:
        async with session_factory() as session:
            model = AccountModel(
                id=account_id,
                owner_name=owner,
                balance=balance,
                currency=currency,
                status="ACTIVE",
            )
            session.add(model)
            await session.commit()

    async def test_exact_once_replay_with_zero_drift(
        self,
        uow: PostgresUnitOfWork,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """Duplicate request with same key returns cached receipt without secondary debit."""
        await self._seed_account(session_factory, "ACC-ALICE-IDEMP", Decimal("500.00"))
        await self._seed_account(session_factory, "ACC-BOB-IDEMP", Decimal("100.00"))

        use_case = AsyncExecuteTransferUseCase(uow=uow)
        cmd = TransferCommand(
            from_account_id="ACC-ALICE-IDEMP",
            to_account_id="ACC-BOB-IDEMP",
            amount=Decimal("150.00"),
            currency=Currency.USD,
            idempotency_key="REQ-TRANSFER-101",
        )

        # First execution: Settles
        res1 = await use_case.execute(cmd)
        assert res1.status == "SETTLED"
        assert res1.from_balance_after.amount == Decimal("350.00")
        assert res1.to_balance_after.amount == Decimal("250.00")

        # Second execution: Replay with identical key
        res2 = await use_case.execute(cmd)
        assert res2.status == "SETTLED"
        assert res2.transaction_id == res1.transaction_id
        assert res2.from_balance_after.amount == Decimal("350.00")

        # Verify database balances and ledger entries in PostgreSQL
        async with session_factory() as session:
            alice_bal = (
                await session.execute(
                    text("SELECT balance FROM accounts WHERE id = 'ACC-ALICE-IDEMP';")
                )
            ).scalar()
            bob_bal = (
                await session.execute(
                    text("SELECT balance FROM accounts WHERE id = 'ACC-BOB-IDEMP';")
                )
            ).scalar()
            entry_count = (
                await session.execute(text("SELECT COUNT(*) FROM ledger_entries;"))
            ).scalar()
            assert alice_bal == Decimal("350.0000")
            assert bob_bal == Decimal("250.0000")
            assert entry_count == 2

    async def test_payload_mutation_attack_raises_409_conflict(
        self,
        uow: PostgresUnitOfWork,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """Reusing key with a mutated payload raises IdempotencyPayloadMismatchError."""
        await self._seed_account(session_factory, "ACC-ALICE-ATTACK", Decimal("1000.00"))
        await self._seed_account(session_factory, "ACC-BOB-ATTACK", Decimal("100.00"))
        await self._seed_account(session_factory, "ACC-CHARLIE-ATTACK", Decimal("0.00"))

        use_case = AsyncExecuteTransferUseCase(uow=uow)

        # Legitimate request 1: Send $100 to Bob
        cmd1 = TransferCommand(
            from_account_id="ACC-ALICE-ATTACK",
            to_account_id="ACC-BOB-ATTACK",
            amount=Decimal("100.00"),
            currency=Currency.USD,
            idempotency_key="ATTACK-KEY-007",
        )
        res1 = await use_case.execute(cmd1)
        assert res1.status == "SETTLED"

        # Mutated request 2: Send $900 to Charlie using the SAME key
        cmd2 = TransferCommand(
            from_account_id="ACC-ALICE-ATTACK",
            to_account_id="ACC-CHARLIE-ATTACK",
            amount=Decimal("900.00"),
            currency=Currency.USD,
            idempotency_key="ATTACK-KEY-007",
        )

        with pytest.raises(IdempotencyPayloadMismatchError) as exc_info:
            await use_case.execute(cmd2)

        assert "different request payload" in str(exc_info.value)

        # Verify Charlie received nothing and Alice was only debited for Request 1
        async with session_factory() as session:
            alice_bal = (
                await session.execute(
                    text("SELECT balance FROM accounts WHERE id = 'ACC-ALICE-ATTACK';")
                )
            ).scalar()
            charlie_bal = (
                await session.execute(
                    text("SELECT balance FROM accounts WHERE id = 'ACC-CHARLIE-ATTACK';")
                )
            ).scalar()
            assert alice_bal == Decimal("900.0000")
            assert charlie_bal == Decimal("0.0000")

    async def test_in_flight_concurrent_lock_acquisition(
        self,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """While a request is IN_PROGRESS, concurrent requests receive IdempotencyInFlightError."""
        req_hash = compute_transfer_fingerprint(
            from_account_id="ACC-A",
            to_account_id="ACC-B",
            amount=Decimal("50.00"),
            currency="USD",
        )

        # Worker 1 acquires lock
        async with session_factory() as session1:
            repo1 = PostgresIdempotencyRepository(session1)
            acquired1, cached1 = await repo1.check_or_acquire("KEY-IN-FLIGHT", req_hash)
            await session1.commit()
            assert acquired1 is True
            assert cached1 is None

        # Worker 2 attempts same key while Worker 1 is still IN_PROGRESS
        async with session_factory() as session2:
            repo2 = PostgresIdempotencyRepository(session2)
            with pytest.raises(IdempotencyInFlightError) as exc_info:
                await repo2.check_or_acquire("KEY-IN-FLIGHT", req_hash)
            assert exc_info.value.key == "KEY-IN-FLIGHT"

    async def test_failed_execution_allows_subsequent_retry(
        self,
        uow: PostgresUnitOfWork,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """When a transaction fails, status transitions to FAILED and subsequent retry succeeds."""
        await self._seed_account(session_factory, "ACC-POOR", Decimal("20.00"))
        await self._seed_account(session_factory, "ACC-RICH", Decimal("100.00"))

        use_case = AsyncExecuteTransferUseCase(uow=uow)
        cmd = TransferCommand(
            from_account_id="ACC-POOR",
            to_account_id="ACC-RICH",
            amount=Decimal("100.00"),
            currency=Currency.USD,
            idempotency_key="RETRY-AFTER-FUND-01",
        )

        # Attempt 1: Fails due to insufficient funds
        with pytest.raises(InsufficientFundsError):
            await use_case.execute(cmd)

        # Verify idempotency record exists with status FAILED
        async with session_factory() as session:
            rec = (
                await session.execute(
                    text(
                        "SELECT status FROM idempotency_records "
                        "WHERE key = 'RETRY-AFTER-FUND-01';"
                    )
                )
            ).scalar()
            assert rec == "FAILED"

        # Fund ACC-POOR with $500
        async with session_factory() as session:
            await session.execute(
                text("UPDATE accounts SET balance = 500.00 WHERE id = 'ACC-POOR';")
            )
            await session.commit()

        # Attempt 2: Re-executing with the exact same key now succeeds!
        res = await use_case.execute(cmd)
        assert res.status == "SETTLED"
        assert res.from_balance_after.amount == Decimal("400.00")

    async def test_multi_tenant_idempotency_isolation(
        self,
        uow: PostgresUnitOfWork,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """The same key used across different tenants does not collide."""
        await self._seed_account(session_factory, "ACC-TENANT-A", Decimal("500.00"))
        await self._seed_account(session_factory, "ACC-TENANT-B", Decimal("500.00"))
        await self._seed_account(session_factory, "ACC-TARGET", Decimal("0.00"))

        use_case = AsyncExecuteTransferUseCase(uow=uow)

        # Tenant 1 uses key 'TX-GLOBAL-99'
        cmd1 = TransferCommand(
            from_account_id="ACC-TENANT-A",
            to_account_id="ACC-TARGET",
            amount=Decimal("50.00"),
            currency=Currency.USD,
            idempotency_key="TX-GLOBAL-99",
            tenant_id="tenant_alpha",
        )
        res1 = await use_case.execute(cmd1)
        assert res1.status == "SETTLED"

        # Tenant 2 uses same key 'TX-GLOBAL-99'
        cmd2 = TransferCommand(
            from_account_id="ACC-TENANT-B",
            to_account_id="ACC-TARGET",
            amount=Decimal("75.00"),
            currency=Currency.USD,
            idempotency_key="TX-GLOBAL-99",
            tenant_id="tenant_beta",
        )
        res2 = await use_case.execute(cmd2)
        assert res2.status == "SETTLED"

        # Verify distinct transactions in PostgreSQL
        assert res1.transaction_id != res2.transaction_id
        async with session_factory() as session:
            count = (
                await session.execute(
                    text("SELECT COUNT(*) FROM idempotency_records WHERE key = 'TX-GLOBAL-99';")
                )
            ).scalar()
            assert count == 2
