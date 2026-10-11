"""Integration and torture tests for PostgreSQL persistence, locking, and atomic Unit of Work.

Verifies:
- Relational schema tables and constraints (accounts, transactions, ledger_entries).
- Monotonic row-level locking (SELECT ... FOR UPDATE ORDER BY id ASC) eliminating deadlocks.
- Atomic commit & rollback: all-or-nothing mutations with 0 side-effects on error.
- Database-level non-negative balance constraint enforcement.
- Real-time mathematical audit reconciliation against PostgreSQL tables.
"""

import asyncio
from collections.abc import AsyncGenerator
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.application.exceptions import (
    ReconciliationDivergenceError,
)
from app.application.use_cases.audit_reconciliation_async import (
    AsyncAuditReconciliationUseCase,
)
from app.application.use_cases.execute_transfer import TransferCommand
from app.application.use_cases.execute_transfer_async import (
    AsyncExecuteTransferUseCase,
)
from app.domain.exceptions import InsufficientFundsError
from app.domain.strategies.fee_strategy import FlatFeeStrategy
from app.domain.value_objects import Currency, Money
from app.infrastructure.config import get_settings
from app.infrastructure.persistence.postgres.database import (
    check_db_health,
    create_async_db_engine,
    get_async_session_factory,
    init_db,
)
from app.infrastructure.persistence.postgres.models import AccountModel
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
    # Clean tables before each test
    async with pg_engine.begin() as conn:
        await conn.execute(text("TRUNCATE TABLE ledger_entries, transactions, accounts CASCADE;"))
    yield factory


@pytest.fixture
def uow(session_factory: async_sessionmaker[AsyncSession]) -> PostgresUnitOfWork:
    """Provides a fresh PostgresUnitOfWork."""
    return PostgresUnitOfWork(session_factory)


@pytest.mark.asyncio
class TestPostgresSchemaAndConstraints:
    """Tests relational schema constraints and table persistence."""

    async def test_database_health_and_tables(self, pg_engine: AsyncEngine) -> None:
        """Verifies database is healthy and core tables exist."""
        healthy = await check_db_health(pg_engine)
        assert healthy is True

        async with pg_engine.connect() as conn:
            result = await conn.execute(
                text(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema = 'public' ORDER BY table_name;"
                )
            )
            tables = [row[0] for row in result.fetchall()]
            assert "accounts" in tables
            assert "transactions" in tables
            assert "ledger_entries" in tables

    async def test_database_enforces_non_negative_balance_constraint(
        self,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """Verifies that PostgreSQL rejects negative balances at the database layer."""
        async with session_factory() as session:
            # Valid account creation
            acc = AccountModel(
                id="ACC-TEST-NEG",
                owner_name="Test Negative",
                balance=Decimal("100.0000"),
                currency="USD",
                status="ACTIVE",
            )
            session.add(acc)
            await session.commit()

            # Attempt to set negative balance
            acc.balance = Decimal("-50.0000")
            with pytest.raises(IntegrityError) as exc_info:
                await session.commit()
            assert "chk_account_balance_non_negative" in str(exc_info.value)


@pytest.mark.asyncio
class TestPostgresUnitOfWorkAndAtomicTransfers:
    """Tests atomic Unit of Work execution, lock ordering, and rollback guarantees."""

    async def _seed_account(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        account_id: str,
        balance: Decimal,
        owner: str = "User",
        currency: str = "USD",
        status: str = "ACTIVE",
    ) -> None:
        async with session_factory() as session:
            model = AccountModel(
                id=account_id,
                owner_name=owner,
                balance=balance,
                currency=currency,
                status=status,
            )
            session.add(model)
            await session.commit()

    async def test_canonical_monotonic_lock_ordering(
        self,
        uow: PostgresUnitOfWork,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """Verifies that lock_accounts_monotonically sorts account IDs ascendingly."""
        await self._seed_account(session_factory, "ACC-ZZZ", Decimal("100.00"))
        await self._seed_account(session_factory, "ACC-AAA", Decimal("200.00"))
        await self._seed_account(session_factory, "ACC-MMM", Decimal("300.00"))

        async with uow:
            # Request locks in reverse/arbitrary order
            locked = await uow.lock_accounts_monotonically(["ACC-ZZZ", "ACC-AAA", "ACC-MMM"])
            assert list(locked.keys()) == ["ACC-AAA", "ACC-MMM", "ACC-ZZZ"]
            assert locked["ACC-AAA"].balance.amount == Decimal("200.00")
            assert locked["ACC-ZZZ"].balance.amount == Decimal("100.00")

    async def test_atomic_transfer_success_with_fee(
        self,
        uow: PostgresUnitOfWork,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """Verifies that a valid transfer commits balances, ledger, and tx atomically."""
        await self._seed_account(session_factory, "ACC-ALICE", Decimal("500.00"), "Alice")
        await self._seed_account(session_factory, "ACC-BOB", Decimal("100.00"), "Bob")
        await self._seed_account(session_factory, "ACC-FEE", Decimal("0.00"), "Fee Reserve")

        use_case = AsyncExecuteTransferUseCase(
            uow=uow,
            default_fee_strategy=FlatFeeStrategy(Decimal("5.00")),
        )

        cmd = TransferCommand(
            from_account_id="ACC-ALICE",
            to_account_id="ACC-BOB",
            amount=Decimal("150.00"),
            currency=Currency.USD,
            fee_account_id="ACC-FEE",
        )

        result = await use_case.execute(cmd)

        assert result.status == "SETTLED"
        assert result.from_balance_after.amount == Decimal("345.00")  # 500 - 150 - 5
        assert result.to_balance_after.amount == Decimal("250.00")    # 100 + 150
        assert result.fee.amount == Decimal("5.00")
        assert len(result.ledger_entry_ids) == 3

        # Inspect database records
        async with session_factory() as session:
            alice_res = await session.execute(
                text("SELECT balance FROM accounts WHERE id = 'ACC-ALICE';")
            )
            bob_res = await session.execute(
                text("SELECT balance FROM accounts WHERE id = 'ACC-BOB';")
            )
            fee_res = await session.execute(
                text("SELECT balance FROM accounts WHERE id = 'ACC-FEE';")
            )
            assert alice_res.scalar() == Decimal("345.0000")
            assert bob_res.scalar() == Decimal("250.0000")
            assert fee_res.scalar() == Decimal("5.0000")

            # Check journal net sum in database
            net_res = await session.execute(
                text("SELECT SUM(amount) FROM ledger_entries;")
            )
            assert net_res.scalar() == Decimal("0.0000")

            # Check transaction record
            tx_res = await session.execute(
                text("SELECT status, amount, fee FROM transactions WHERE id = :tx_id;"),
                {"tx_id": result.transaction_id},
            )
            tx_row = tx_res.fetchone()
            assert tx_row is not None
            assert tx_row[0] == "SETTLED"
            assert tx_row[1] == Decimal("150.0000")
            assert tx_row[2] == Decimal("5.0000")

    async def test_atomic_rollback_on_insufficient_funds(
        self,
        uow: PostgresUnitOfWork,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """Verifies that insufficient balance causes a complete rollback with 0 side-effects."""
        await self._seed_account(session_factory, "ACC-POOR", Decimal("20.00"), "Poor")
        await self._seed_account(session_factory, "ACC-RICH", Decimal("500.00"), "Rich")

        use_case = AsyncExecuteTransferUseCase(uow=uow)

        cmd = TransferCommand(
            from_account_id="ACC-POOR",
            to_account_id="ACC-RICH",
            amount=Decimal("100.00"),
            currency=Currency.USD,
        )

        with pytest.raises(InsufficientFundsError):
            await use_case.execute(cmd)

        # Verify database remained completely untouched
        async with session_factory() as session:
            poor_res = await session.execute(
                text("SELECT balance FROM accounts WHERE id = 'ACC-POOR';")
            )
            rich_res = await session.execute(
                text("SELECT balance FROM accounts WHERE id = 'ACC-RICH';")
            )
            assert poor_res.scalar() == Decimal("20.0000")
            assert rich_res.scalar() == Decimal("500.0000")

            entries_count = await session.execute(
                text("SELECT COUNT(*) FROM ledger_entries;")
            )
            assert entries_count.scalar() == 0

    async def test_atomic_rollback_on_midflight_exception(
        self,
        uow: PostgresUnitOfWork,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """Verifies that an unhandled error inside a Unit of Work rolls back mutations."""
        await self._seed_account(session_factory, "ACC-ALICE-CRASH", Decimal("100.00"))
        await self._seed_account(session_factory, "ACC-BOB-CRASH", Decimal("100.00"))

        with pytest.raises(RuntimeError, match="Simulated mid-flight crash"):
            async with uow:
                accounts = await uow.lock_accounts_monotonically(
                    ["ACC-ALICE-CRASH", "ACC-BOB-CRASH"]
                )
                alice = accounts["ACC-ALICE-CRASH"]
                alice.debit(Money(Decimal("50.00"), Currency.USD))
                await uow.save_account_mutation(alice)
                # Crash before commit!
                raise RuntimeError("Simulated mid-flight crash")

        # Verify Alice's balance was rolled back to 100.00
        async with session_factory() as session:
            res = await session.execute(
                text("SELECT balance FROM accounts WHERE id = 'ACC-ALICE-CRASH';")
            )
            assert res.scalar() == Decimal("100.0000")

    async def test_concurrent_opposing_transfers_no_deadlock(
        self,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """Verifies Coffman circular-wait deadlock immunity under heavy bilateral transfers."""
        await self._seed_account(session_factory, "ACC-NODE-A", Decimal("10000.00"))
        await self._seed_account(session_factory, "ACC-NODE-B", Decimal("10000.00"))

        async def transfer_a_to_b() -> None:
            local_uow = PostgresUnitOfWork(session_factory)
            use_case = AsyncExecuteTransferUseCase(uow=local_uow)
            cmd = TransferCommand(
                from_account_id="ACC-NODE-A",
                to_account_id="ACC-NODE-B",
                amount=Decimal("10.00"),
                currency=Currency.USD,
            )
            await use_case.execute(cmd)

        async def transfer_b_to_a() -> None:
            local_uow = PostgresUnitOfWork(session_factory)
            use_case = AsyncExecuteTransferUseCase(uow=local_uow)
            cmd = TransferCommand(
                from_account_id="ACC-NODE-B",
                to_account_id="ACC-NODE-A",
                amount=Decimal("10.00"),
                currency=Currency.USD,
            )
            await use_case.execute(cmd)

        # Launch 20 concurrent opposing transfers simultaneously (10 A->B and 10 B->A)
        tasks = [transfer_a_to_b() if i % 2 == 0 else transfer_b_to_a() for i in range(20)]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Verify zero deadlocks or exceptions occurred
        for r in results:
            assert not isinstance(r, Exception), f"Concurrent transfer failed: {r}"

        # Verify final balances are conserved
        async with session_factory() as session:
            q_a = text("SELECT balance FROM accounts WHERE id = 'ACC-NODE-A';")
            bal_a = (await session.execute(q_a)).scalar()
            q_b = text("SELECT balance FROM accounts WHERE id = 'ACC-NODE-B';")
            bal_b = (await session.execute(q_b)).scalar()
            assert bal_a == Decimal("10000.0000")
            assert bal_b == Decimal("10000.0000")


@pytest.mark.asyncio
class TestPostgresAuditReconciliation:
    """Tests mathematical reconciliation against live PostgreSQL tables."""

    async def test_reconciliation_balanced(
        self,
        uow: PostgresUnitOfWork,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """Verifies audit succeeds when all journal entries match account balances."""
        # Seed and perform a transfer
        async with session_factory() as session:
            session.add(
                AccountModel(
                    id="ACC-1", owner_name="1", balance=Decimal("100.00"),
                    currency="USD", status="ACTIVE",
                )
            )
            session.add(
                AccountModel(
                    id="ACC-2", owner_name="2", balance=Decimal("100.00"),
                    currency="USD", status="ACTIVE",
                )
            )
            await session.commit()

        use_case = AsyncExecuteTransferUseCase(uow=uow)
        cmd = TransferCommand(
            from_account_id="ACC-1", to_account_id="ACC-2",
            amount=Decimal("25.00"), currency=Currency.USD,
        )
        await use_case.execute(cmd)

        audit_use_case = AsyncAuditReconciliationUseCase(uow=uow)
        report = await audit_use_case.reconcile(raise_on_error=True)

        assert report.is_system_net_zero is True
        assert report.is_balanced is True
        assert report.total_system_net == Decimal("0.00")
        assert len(report.discrepancies) == 0

    async def test_reconciliation_detects_manual_database_tampering(
        self,
        uow: PostgresUnitOfWork,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """Verifies direct balance manipulation in database is detected by the audit engine."""
        async with session_factory() as session:
            session.add(
                AccountModel(
                    id="ACC-AUD-1", owner_name="1", balance=Decimal("100.00"),
                    currency="USD", status="ACTIVE",
                )
            )
            session.add(
                AccountModel(
                    id="ACC-AUD-2", owner_name="2", balance=Decimal("100.00"),
                    currency="USD", status="ACTIVE",
                )
            )
            await session.commit()

        use_case = AsyncExecuteTransferUseCase(uow=uow)
        cmd = TransferCommand(
            from_account_id="ACC-AUD-1", to_account_id="ACC-AUD-2",
            amount=Decimal("40.00"), currency=Currency.USD,
        )
        await use_case.execute(cmd)

        # Deliberately tamper with ACC-AUD-1 balance directly in PostgreSQL
        async with session_factory() as session:
            update_sql = text("UPDATE accounts SET balance = 999.00 WHERE id = 'ACC-AUD-1';")
            await session.execute(update_sql)
            await session.commit()

        audit_use_case = AsyncAuditReconciliationUseCase(uow=uow)
        with pytest.raises(ReconciliationDivergenceError):
            await audit_use_case.reconcile(raise_on_error=True)

        report = await audit_use_case.reconcile(raise_on_error=False)
        assert report.is_balanced is False
        assert len(report.discrepancies) == 1
        assert report.discrepancies[0].account_id == "ACC-AUD-1"
        assert report.discrepancies[0].actual_balance == Decimal("999.0000")
        assert report.discrepancies[0].expected_balance == Decimal("60.0000")
