import logging
import time
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.exceptions import (
    IdempotencyInFlightError,
    IdempotencyPayloadMismatchError,
)
from app.domain.models import Account, AccountStatus, EntryType, LedgerEntry
from app.domain.value_objects import Currency, Money
from app.infrastructure.persistence.postgres.models import (
    AccountModel,
    IdempotencyRecordModel,
    LedgerEntryModel,
)

logger = logging.getLogger("ledger_core.idempotency")


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


class PostgresIdempotencyRepository:
    """Async repository managing durable idempotency records and cryptographic verification."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_record(
        self,
        key: str,
        tenant_id: str = "default",
    ) -> IdempotencyRecordModel | None:
        """Retrieves an existing idempotency record by tenant and key."""
        stmt = (
            select(IdempotencyRecordModel)
            .where(
                IdempotencyRecordModel.tenant_id == tenant_id,
                IdempotencyRecordModel.key == key,
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def check_or_acquire(
        self,
        key: str,
        request_hash: str,
        tenant_id: str = "default",
        in_flight_timeout_seconds: float = 120.0,
    ) -> tuple[bool, dict[str, Any] | None]:
        """Checks payload fingerprint and acquires an in-flight execution lock.

        Returns:
            tuple[bool, dict[str, Any] | None]:
                (True, None) if lock acquired or safely recovered -> proceed with execution.
                (False, cached_payload) if previously SETTLED -> return cached result.

        Raises:
            IdempotencyPayloadMismatchError: If the key was used with a different payload.
            IdempotencyInFlightError: If identical request is processing within lease window.
        """
        stmt = (
            select(IdempotencyRecordModel)
            .where(
                IdempotencyRecordModel.tenant_id == tenant_id,
                IdempotencyRecordModel.key == key,
            )
            .with_for_update()
        )
        result = await self.session.execute(stmt)
        record = result.scalar_one_or_none()

        if record is not None:
            # 1. Detect request payload mutation
            if record.request_hash != request_hash:
                raise IdempotencyPayloadMismatchError(key)

            # 2. Fast-path: Return cached completed execution
            if record.status == "SETTLED":
                return False, record.response_payload

            # 3. Interrupted request recovery or in-flight active conflict
            if record.status == "IN_PROGRESS":
                now_utc = datetime.now(UTC)
                record_time = record.updated_at or record.created_at
                if record_time is not None and record_time.tzinfo is None:
                    record_time = record_time.replace(tzinfo=UTC)

                elapsed_seconds = (now_utc - record_time).total_seconds() if record_time else 0.0

                if elapsed_seconds > in_flight_timeout_seconds:
                    logger.warning(
                        "Safely recovering interrupted request for key '%s' "
                        "(in-flight lease expired after %.1fs > timeout %.1fs).",
                        key,
                        elapsed_seconds,
                        in_flight_timeout_seconds,
                    )
                    record.status = "IN_PROGRESS"
                    record.updated_at = func.now()
                    await self.session.flush()
                    return True, None

                # Active execution within valid lease window
                retry_after = max(1, int(in_flight_timeout_seconds - elapsed_seconds))
                raise IdempotencyInFlightError(key, retry_after_seconds=min(retry_after, 5))

            # 4. Previously failed request: allow retry
            record.status = "IN_PROGRESS"
            record.updated_at = func.now()
            await self.session.flush()
            return True, None

        # Insert new IN_PROGRESS record
        new_record = IdempotencyRecordModel(
            key=key,
            tenant_id=tenant_id,
            request_hash=request_hash,
            status="IN_PROGRESS",
        )
        self.session.add(new_record)
        try:
            await self.session.flush()
            return True, None
        except IntegrityError as err:
            # Concurrency race condition: another transaction committed first
            await self.session.rollback()
            stmt = (
                select(IdempotencyRecordModel)
                .where(
                    IdempotencyRecordModel.tenant_id == tenant_id,
                    IdempotencyRecordModel.key == key,
                )
                .with_for_update()
            )
            res = await self.session.execute(stmt)
            rec = res.scalar_one_or_none()
            if rec is not None:
                if rec.request_hash != request_hash:
                    raise IdempotencyPayloadMismatchError(key) from err
                if rec.status == "SETTLED":
                    return False, rec.response_payload
                if rec.status == "IN_PROGRESS":
                    raise IdempotencyInFlightError(key) from err
            raise IdempotencyInFlightError(key) from err

    async def mark_settled(
        self,
        key: str,
        response_payload: dict[str, Any],
        transaction_id: str | None = None,
        tenant_id: str = "default",
    ) -> None:
        """Marks the idempotency record as SETTLED with its serialized response payload."""
        stmt = (
            select(IdempotencyRecordModel)
            .where(
                IdempotencyRecordModel.tenant_id == tenant_id,
                IdempotencyRecordModel.key == key,
            )
        )
        result = await self.session.execute(stmt)
        record = result.scalar_one_or_none()
        if record is not None:
            record.status = "SETTLED"
            record.response_payload = response_payload
            record.transaction_id = transaction_id
            record.updated_at = func.now()
        else:
            record = IdempotencyRecordModel(
                key=key,
                tenant_id=tenant_id,
                request_hash="",
                status="SETTLED",
                response_payload=response_payload,
                transaction_id=transaction_id,
            )
            self.session.add(record)
        await self.session.flush()

    async def mark_failed(
        self,
        key: str,
        tenant_id: str = "default",
    ) -> None:
        """Marks the idempotency record as FAILED so client retries are permitted."""
        stmt = (
            select(IdempotencyRecordModel)
            .where(
                IdempotencyRecordModel.tenant_id == tenant_id,
                IdempotencyRecordModel.key == key,
            )
        )
        result = await self.session.execute(stmt)
        record = result.scalar_one_or_none()
        if record is not None:
            record.status = "FAILED"
            record.updated_at = func.now()
            await self.session.flush()

