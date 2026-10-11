"""PostgreSQL repository implementations mapping domain models to relational schemas."""

import time
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models import Account, AccountStatus, EntryType, LedgerEntry
from app.domain.value_objects import Currency, Money
from app.infrastructure.persistence.postgres.models import AccountModel, LedgerEntryModel


class PostgresAccountRepository:
    """Async repository for account persistence backed by PostgreSQL."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    @staticmethod
    def _to_domain(model: AccountModel) -> Account:
        """Converts an ORM AccountModel to a pure Domain Account entity."""
        balance_dec = Decimal(str(model.balance)).quantize(Decimal("0.01"))
        return Account(
            account_id=model.id,
            owner_name=model.owner_name,
            balance=Money(balance_dec, Currency(model.currency)),
            status=AccountStatus(model.status),
        )

    async def get_by_id(self, account_id: str) -> Account | None:
        """Retrieves an Account by ID."""
        stmt = select(AccountModel).where(AccountModel.id == account_id)
        result = await self.session.execute(stmt)
        model = result.scalar_one_or_none()
        return self._to_domain(model) if model is not None else None

    async def get_by_id_for_update(self, account_id: str) -> Account | None:
        """Retrieves an Account with an exclusive row-level lock (FOR UPDATE)."""
        stmt = (
            select(AccountModel)
            .where(AccountModel.id == account_id)
            .with_for_update()
        )
        result = await self.session.execute(stmt)
        model = result.scalar_one_or_none()
        return self._to_domain(model) if model is not None else None

    async def save(self, account: Account) -> None:
        """Persists or updates an Account entity."""
        stmt = select(AccountModel).where(AccountModel.id == account.account_id)
        result = await self.session.execute(stmt)
        model = result.scalar_one_or_none()

        if model is None:
            model = AccountModel(
                id=account.account_id,
                owner_name=account.owner_name,
                balance=account.balance.amount,
                currency=str(account.balance.currency),
                status=str(account.status),
            )
            self.session.add(model)
        else:
            model.owner_name = account.owner_name
            model.balance = account.balance.amount
            model.currency = str(account.balance.currency)
            model.status = str(account.status)

    async def create(self, account: Account) -> Account:
        """Creates and saves a new account, returning the domain entity."""
        model = AccountModel(
            id=account.account_id,
            owner_name=account.owner_name,
            balance=account.balance.amount,
            currency=str(account.balance.currency),
            status=str(account.status),
        )
        self.session.add(model)
        return account

    async def get_all(self) -> list[Account]:
        """Returns all accounts for audits and reconciliation."""
        stmt = select(AccountModel).order_by(AccountModel.id.asc())
        result = await self.session.execute(stmt)
        models = result.scalars().all()
        return [self._to_domain(m) for m in models]


class PostgresLedgerRepository:
    """Async repository for append-only double-entry ledger journals."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    @staticmethod
    def _to_domain(model: LedgerEntryModel) -> LedgerEntry:
        """Converts an ORM LedgerEntryModel to a pure Domain LedgerEntry entity."""
        ts = model.created_at.timestamp() if model.created_at is not None else time.time()
        amount_dec = Decimal(str(model.amount)).quantize(Decimal("0.01"))
        balance_after_dec = Decimal(str(model.balance_after)).quantize(Decimal("0.01"))
        return LedgerEntry(
            entry_id=model.entry_id,
            transaction_id=model.transaction_id,
            account_id=model.account_id,
            amount=amount_dec,
            balance_after=balance_after_dec,
            entry_type=EntryType(model.entry_type),
            timestamp=ts,
        )

    async def append_entry(
        self,
        entry: LedgerEntry,
        currency: str | Currency = "USD",
    ) -> None:
        """Appends an immutable LedgerEntry record."""
        model = LedgerEntryModel(
            entry_id=entry.entry_id,
            transaction_id=entry.transaction_id,
            account_id=entry.account_id,
            amount=entry.amount,
            currency=str(currency),
            balance_after=entry.balance_after,
            entry_type=str(entry.entry_type),
        )
        self.session.add(model)

    async def append_entries(
        self,
        entries: list[LedgerEntry],
        currency: str | Currency = "USD",
    ) -> None:
        """Appends multiple ledger entries in batch."""
        for entry in entries:
            await self.append_entry(entry, currency=currency)

    async def get_entries_for_account(self, account_id: str) -> list[LedgerEntry]:
        """Returns chronological ledger entries associated with the account."""
        stmt = (
            select(LedgerEntryModel)
            .where(LedgerEntryModel.account_id == account_id)
            .order_by(LedgerEntryModel.sequence_id.asc())
        )
        result = await self.session.execute(stmt)
        models = result.scalars().all()
        return [self._to_domain(m) for m in models]

    async def get_all_entries(self) -> list[LedgerEntry]:
        """Returns all ledger entries in the system ordered by deterministic sequence."""
        stmt = select(LedgerEntryModel).order_by(LedgerEntryModel.sequence_id.asc())
        result = await self.session.execute(stmt)
        models = result.scalars().all()
        return [self._to_domain(m) for m in models]

    async def get_total_system_net(self) -> Decimal:
        """Calculates total net sum across all ledger entries in the database."""
        stmt = select(func.coalesce(func.sum(LedgerEntryModel.amount), Decimal("0.0000")))
        result = await self.session.execute(stmt)
        val = result.scalar()
        return Decimal(str(val)) if val is not None else Decimal("0.0000")
