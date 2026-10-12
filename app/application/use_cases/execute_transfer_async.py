"""Async PostgreSQL Execute Transfer Use Case orchestrating atomic financial transactions.

Enforces:
- Clean Architecture (Orchestrates Domain entities and Port boundaries)
- Database-level canonical lock acquisition (SELECT ... FOR UPDATE ORDER BY id ASC)
- Strict double-entry bookkeeping conservation (sum(entries) == 0.00)
- GoF State Machine lifecycle progression (INITIATED -> LOCKED -> COMMITTED -> SETTLED)
- Atomic Unit of Work commit with automatic rollback on any failure
"""

import time
import uuid
from decimal import Decimal

from app.application.exceptions import (
    AccountNotFoundError,
    InvalidIdempotencyKeyError,
    MissingIdempotencyKeyError,
    SelfTransferNotAllowedError,
)
from app.application.fingerprint import compute_transfer_command_hash
from app.application.use_cases.execute_transfer import TransferCommand, TransferResult
from app.domain.exceptions import (
    DomainError,
    LedgerInvariantViolationError,
)
from app.domain.models import LedgerEntry
from app.domain.state_machine import TransactionState, TransactionStateMachine
from app.domain.strategies.fee_strategy import IFeeStrategy, P2PPeerFeeStrategy
from app.domain.value_objects import Currency, Money
from app.infrastructure.persistence.postgres.repositories import (
    PostgresIdempotencyRepository,
)
from app.infrastructure.persistence.postgres.unit_of_work import PostgresUnitOfWork
from app.ports.cache_port import ICachePort
from app.ports.event_publisher_port import IEventPublisher, TransactionSettledEvent


class AsyncExecuteTransferUseCase:
    """Orchestrates financial transfers atomically within a PostgreSQL Unit of Work."""

    def __init__(
        self,
        uow: PostgresUnitOfWork,
        cache: ICachePort | None = None,
        event_publisher: IEventPublisher | None = None,
        default_fee_strategy: IFeeStrategy | None = None,
        require_idempotency: bool = False,
        in_flight_timeout_seconds: float = 120.0,
    ) -> None:
        self.uow = uow
        self.cache = cache
        self.event_publisher = event_publisher
        self.default_fee_strategy = default_fee_strategy or P2PPeerFeeStrategy()
        self.require_idempotency = require_idempotency
        self.in_flight_timeout_seconds = in_flight_timeout_seconds

    async def execute(self, command: TransferCommand) -> TransferResult:
        """Executes a transfer within a single atomic PostgreSQL transaction boundary.

        Args:
            command: Transfer parameters including sender, receiver, amount, and fee strategy.

        Returns:
            TransferResult: Complete transaction execution metadata.

        Raises:
            SelfTransferNotAllowedError: If sender and receiver are identical.
            AccountNotFoundError: If an account does not exist.
            InsufficientFundsError: If sender has inadequate funds.
            CurrencyMismatchError: If account and transfer currencies conflict.
            LedgerInvariantViolationError: If double-entry conservation fails.
            MissingIdempotencyKeyError: If idempotency key is required but missing.
            InvalidIdempotencyKeyError: If idempotency key is invalid or oversized.
        """
        # 1. Validation: Prevent self-transfer
        if command.from_account_id == command.to_account_id:
            raise SelfTransferNotAllowedError(
                f"Source and destination accounts are identical: {command.from_account_id}."
            )

        # 1.5. Validate Idempotency Key
        clean_key: str | None = None
        if self.require_idempotency or command.idempotency_key is not None:
            if not command.idempotency_key or not str(command.idempotency_key).strip():
                raise MissingIdempotencyKeyError()
            clean_key = str(command.idempotency_key).strip()
            if len(clean_key) > 128:
                raise InvalidIdempotencyKeyError(
                    clean_key, "Key exceeds maximum length of 128 characters."
                )

        # 2. Determine transfer currency and money amount
        if isinstance(command.amount, Money):
            transfer_amount = command.amount
        elif command.currency is not None:
            curr = (
                Currency(command.currency)
                if isinstance(command.currency, str)
                else command.currency
            )
            transfer_amount = Money(Decimal(str(command.amount)), curr)
        else:
            transfer_amount = Money(Decimal(str(command.amount)), Currency.USD)

        if not transfer_amount.is_positive():
            raise ValueError(f"Transfer amount must be strictly positive, got {transfer_amount}.")

        # 3. Initialize GoF State Machine
        state_machine = TransactionStateMachine()
        tx_id = str(uuid.uuid4())

        # 4. Determine Fee Strategy and Fee
        fee_strategy = command.fee_strategy or self.default_fee_strategy
        fee = fee_strategy.calculate_fee(transfer_amount)
        has_fee = fee.is_positive()
        fee_account_id = command.fee_account_id if has_fee else None

        # Build list of all participating accounts to lock
        account_ids_to_lock = [command.from_account_id, command.to_account_id]
        if fee_account_id:
            account_ids_to_lock.append(fee_account_id)

        # 4.5. Distributed Cryptographic Idempotency Check & In-Flight Lock Acquisition
        if clean_key:
            req_hash = compute_transfer_command_hash(
                from_account_id=command.from_account_id,
                to_account_id=command.to_account_id,
                amount=transfer_amount.amount,
                currency=str(transfer_amount.currency),
                fee_account_id=fee_account_id,
                metadata=command.metadata,
                tenant_id=command.tenant_id,
            )
            async with self.uow.session_factory() as idemp_session:
                idemp_repo = PostgresIdempotencyRepository(idemp_session)
                acquired, cached_payload = await idemp_repo.check_or_acquire(
                    key=clean_key,
                    request_hash=req_hash,
                    tenant_id=command.tenant_id,
                    in_flight_timeout_seconds=self.in_flight_timeout_seconds,
                )
                await idemp_session.commit()

            if not acquired and cached_payload is not None:
                return TransferResult.from_dict(cached_payload)

        # 5. Execute Atomic Unit of Work
        async with self.uow as uow:
            try:
                # Monotonic row-level locking (SELECT ... FOR UPDATE ORDER BY id ASC)
                accounts_map = await uow.lock_accounts_monotonically(account_ids_to_lock)

                if command.from_account_id not in accounts_map:
                    raise AccountNotFoundError(
                        f"Sender account {command.from_account_id} not found."
                    )
                if command.to_account_id not in accounts_map:
                    raise AccountNotFoundError(
                        f"Receiver account {command.to_account_id} not found."
                    )
                if fee_account_id and fee_account_id not in accounts_map:
                    raise AccountNotFoundError(
                        f"Fee collection account {fee_account_id} not found."
                    )

                sender = accounts_map[command.from_account_id]
                receiver = accounts_map[command.to_account_id]
                fee_account = accounts_map.get(fee_account_id) if fee_account_id else None

                # State transition: INITIATED -> LOCKED
                state_machine.transition_to(TransactionState.LOCKED)

                # Total debit required from sender
                total_debit = transfer_amount.add(fee) if has_fee else transfer_amount

                # Domain operations with invariant enforcement
                sender.debit(total_debit)
                receiver.credit(transfer_amount)
                if fee_account is not None and has_fee:
                    fee_account.credit(fee)

                # 6. Build double-entry ledger entries
                now = time.time()
                debit_entry_id = str(uuid.uuid4())
                credit_entry_id = str(uuid.uuid4())
                fee_entry_id = str(uuid.uuid4()) if has_fee else None

                entry_debit = LedgerEntry.create_debit(
                    entry_id=debit_entry_id,
                    transaction_id=tx_id,
                    account_id=sender.account_id,
                    amount=total_debit,
                    balance_after=sender.balance,
                    timestamp=now,
                )
                entry_credit = LedgerEntry.create_credit(
                    entry_id=credit_entry_id,
                    transaction_id=tx_id,
                    account_id=receiver.account_id,
                    amount=transfer_amount,
                    balance_after=receiver.balance,
                    timestamp=now,
                )

                entries: list[LedgerEntry] = [entry_debit, entry_credit]
                if has_fee and fee_account is not None and fee_entry_id is not None:
                    entry_fee = LedgerEntry.create_credit(
                        entry_id=fee_entry_id,
                        transaction_id=tx_id,
                        account_id=fee_account.account_id,
                        amount=fee,
                        balance_after=fee_account.balance,
                        timestamp=now,
                    )
                    entries.append(entry_fee)

                # 7. Mathematical zero-sum conservation verification
                net_sum = sum((e.amount for e in entries), start=Decimal("0.00"))
                if net_sum != Decimal("0.00"):
                    raise LedgerInvariantViolationError(
                        f"Double-entry balance check failed! Net sum is {net_sum}, expected 0.00."
                    )

                # 8. State transitions: LOCKED -> COMMITTED -> SETTLED
                state_machine.transition_to(TransactionState.COMMITTED)
                state_machine.transition_to(TransactionState.SETTLED)

                # 9. Atomic persistence within the same PostgreSQL transaction
                await uow.save_account_mutation(sender)
                await uow.save_account_mutation(receiver)
                if fee_account is not None and has_fee:
                    await uow.save_account_mutation(fee_account)

                await uow.record_transaction(
                    tx_id=tx_id,
                    idempotency_key=clean_key,
                    tenant_id=command.tenant_id,
                    from_account_id=sender.account_id,
                    to_account_id=receiver.account_id,
                    amount=transfer_amount.amount,
                    fee=fee.amount,
                    currency=str(transfer_amount.currency),
                    status="SETTLED",
                )
                await uow.append_entries(entries, currency=str(transfer_amount.currency))

                # If idempotency key provided, mark SETTLED in the exact same DB transaction!
                if clean_key:
                    result_dict = {
                        "transaction_id": tx_id,
                        "from_account_id": sender.account_id,
                        "to_account_id": receiver.account_id,
                        "amount": str(transfer_amount.amount),
                        "currency": str(transfer_amount.currency),
                        "fee": str(fee.amount),
                        "from_balance_after": str(sender.balance.amount),
                        "to_balance_after": str(receiver.balance.amount),
                        "status": "SETTLED",
                        "created_at": now,
                        "ledger_entry_ids": [e.entry_id for e in entries],
                        "metadata": command.metadata,
                    }
                    await uow.idempotency.mark_settled(
                        key=clean_key,
                        response_payload=result_dict,
                        transaction_id=tx_id,
                        tenant_id=command.tenant_id,
                    )

                # Commit atomically!
                await uow.commit()

                # 10. Cache invalidation
                if self.cache is not None:
                    self.cache.delete(sender.account_id)
                    self.cache.delete(receiver.account_id)
                    if fee_account is not None:
                        self.cache.delete(fee_account.account_id)

            except (DomainError, Exception):
                if state_machine.state in (
                    TransactionState.INITIATED,
                    TransactionState.LOCKED,
                ):
                    try:
                        state_machine.transition_to(TransactionState.FAILED)
                    except Exception:
                        pass
                if clean_key:
                    try:
                        async with self.uow.session_factory() as idemp_session:
                            idemp_repo = PostgresIdempotencyRepository(idemp_session)
                            await idemp_repo.mark_failed(
                                key=clean_key,
                                tenant_id=command.tenant_id,
                            )
                            await idemp_session.commit()
                    except Exception:
                        pass
                raise

        # 11. Asynchronous event publication (outside database critical lock)
        if self.event_publisher is not None:
            event = TransactionSettledEvent(
                transaction_id=tx_id,
                from_account_id=sender.account_id,
                to_account_id=receiver.account_id,
                amount=transfer_amount,
                fee=fee,
                timestamp=now,
            )
            self.event_publisher.publish(event)

        entry_ids = [e.entry_id for e in entries]
        return TransferResult(
            transaction_id=tx_id,
            from_account_id=sender.account_id,
            to_account_id=receiver.account_id,
            amount=transfer_amount,
            fee=fee,
            from_balance_after=sender.balance,
            to_balance_after=receiver.balance,
            status=state_machine.state.value,
            created_at=now,
            ledger_entry_ids=entry_ids,
            metadata=command.metadata,
        )
