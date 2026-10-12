"""PostgreSQL Unit of Work implementing ACID boundaries and canonical deadlock-free locking."""

import logging
from decimal import Decimal
from typing import Self

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.domain.models import Account, AccountStatus, LedgerEntry
from app.domain.value_objects import Currency, Money
from app.infrastructure.persistence.postgres.models import AccountModel, TransactionModel
from app.infrastructure.persistence.postgres.repositories import (
    PostgresAccountRepository,
    PostgresIdempotencyRepository,
    PostgresLedgerRepository,
)

logger = logging.getLogger("ledger_core.uow")


class PostgresUnitOfWork:
    """Manages transactional boundaries and canonical row-level locking for PostgreSQL."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        self.session_factory = session_factory
        self.session: AsyncSession | None = None
        self._accounts: PostgresAccountRepository | None = None
        self._ledger: PostgresLedgerRepository | None = None
        self._idempotency: PostgresIdempotencyRepository | None = None
        self._committed: bool = False

    async def __aenter__(self) -> Self:
        """Enters the Unit of Work and begins a transactional database session."""
        self.session = self.session_factory()
        await self.session.begin()
        self._accounts = PostgresAccountRepository(self.session)
        self._ledger = PostgresLedgerRepository(self.session)
        self._idempotency = PostgresIdempotencyRepository(self.session)
        self._committed = False
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object | None,
    ) -> None:
        """Exits the Unit of Work, automatically rolling back on errors or uncommitted state."""
        if self.session is None:
            return

        try:
            if exc_type is not None:
                logger.warning("Rolling back transaction due to exception: %s", exc_val)
                await self.rollback()
            elif not self._committed:
                await self.commit()
        finally:
            await self.session.close()
            self.session = None
            self._accounts = None
            self._ledger = None
            self._idempotency = None

    @property
    def accounts(self) -> PostgresAccountRepository:
        """Provides access to the accounts repository within the active session."""
        if self._accounts is None:
            raise RuntimeError("PostgresUnitOfWork session is not active. Use 'async with uow:'.")
        return self._accounts

    @property
    def ledger(self) -> PostgresLedgerRepository:
        """Provides access to the ledger journal repository within the active session."""
        if self._ledger is None:
            raise RuntimeError("PostgresUnitOfWork session is not active. Use 'async with uow:'.")
        return self._ledger

    @property
    def idempotency(self) -> PostgresIdempotencyRepository:
        """Provides access to the idempotency repository within the active session."""
        if self._idempotency is None:
            raise RuntimeError("PostgresUnitOfWork session is not active. Use 'async with uow:'.")
        return self._idempotency

    async def commit(self) -> None:
        """Commits the active database transaction."""
        if self.session is not None and not self._committed:
            await self.session.commit()
            self._committed = True

    async def rollback(self) -> None:
        """Rolls back the active database transaction."""
        if self.session is not None:
            await self.session.rollback()

    async def lock_accounts_monotonically(
        self,
        account_ids: list[str],
    ) -> dict[str, Account]:
        """Locks all participating accounts in deterministic ascending lexicographical order.

        Enforces strictly monotonic min(ids) -> ... -> max(ids) row-level lock acquisition
        via PostgreSQL's 'SELECT ... FOR UPDATE' inside the single active transaction.

        By querying and locking each account by primary key in sorted lexicographical order:
        1. Lock for min(ids) is physically requested and acquired first in PostgreSQL.
        2. Lock for next(ids) is requested and acquired second.
        3. Lock for max(ids) is requested and acquired third.

        Because every concurrent application process or machine requests row locks in the
        exact same ascending order, circular wait (Coffman condition #4) is mathematically
        eliminated, guaranteeing zero deadlocks across all distributed nodes sharing the DB.
        """
        if self.session is None:
            raise RuntimeError("Unit of Work is not active.")

        # Deduplicate and sort accounts deterministically
        sorted_ids = sorted(set(account_ids))
        if not sorted_ids:
            return {}

        domain_accounts: dict[str, Account] = {}
        for acc_id in sorted_ids:
            stmt = (
                select(AccountModel)
                .where(AccountModel.id == acc_id)
                .with_for_update()
            )
            result = await self.session.execute(stmt)
            m = result.scalar_one_or_none()
            if m is not None:
                bal_dec = Decimal(str(m.balance)).quantize(Decimal("0.01"))
                domain_accounts[m.id] = Account(
                    account_id=m.id,
                    owner_name=m.owner_name,
                    balance=Money(bal_dec, Currency(m.currency)),
                    status=AccountStatus(m.status),
                )
        return domain_accounts

    async def record_transaction(
        self,
        tx_id: str,
        from_account_id: str,
        to_account_id: str,
        amount: Decimal,
        currency: str,
        status: str,
        fee: Decimal = Decimal("0.0000"),
        idempotency_key: str | None = None,
        tenant_id: str = "default",
        error_reason: str | None = None,
    ) -> TransactionModel:
        """Persists a transaction lifecycle audit record within the atomic transaction."""
        if self.session is None:
            raise RuntimeError("Unit of Work is not active.")

        tx_model = TransactionModel(
            id=tx_id,
            idempotency_key=idempotency_key,
            tenant_id=tenant_id,
            source_account_id=from_account_id,
            destination_account_id=to_account_id,
            amount=amount,
            fee=fee,
            currency=currency,
            status=status,
            error_reason=error_reason,
        )
        self.session.add(tx_model)
        await self.session.flush()
        return tx_model

    async def save_account_mutation(self, account: Account) -> None:
        """Updates the balance and status of an existing locked account."""
        if self.session is None:
            raise RuntimeError("Unit of Work is not active.")

        stmt = select(AccountModel).where(AccountModel.id == account.account_id)
        result = await self.session.execute(stmt)
        model = result.scalar_one_or_none()
        if model is None:
            raise KeyError(f"Account {account.account_id} not found for balance update.")

        model.balance = account.balance.amount
        model.status = str(account.status)
        model.owner_name = account.owner_name

    async def append_entries(
        self,
        entries: list[LedgerEntry],
        currency: str | Currency = "USD",
    ) -> None:
        """Appends journal ledger entries within the active atomic transaction."""
        await self.ledger.append_entries(entries, currency=currency)
