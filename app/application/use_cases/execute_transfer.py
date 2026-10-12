"""Synchronous in-memory Execute Transfer Use Case for unit testing.

NOTE: This use case operates with in-memory repositories and local threading.RLock.
It is retained specifically for isolated unit tests, fast mocked simulations, and
local micro-benchmarks, NOT as proof of distributed or multi-process correctness.
For real multi-process and multi-node execution with ACID durability, use
AsyncExecuteTransferUseCase backed by PostgreSQL Unit of Work and row-level locks.
"""

import time
import uuid
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from app.application.exceptions import (
    AccountNotFoundError,
    SelfTransferNotAllowedError,
)
from app.domain.exceptions import (
    DomainError,
    LedgerInvariantViolationError,
)
from app.domain.models import Account, LedgerEntry
from app.domain.state_machine import TransactionState, TransactionStateMachine
from app.domain.strategies.fee_strategy import IFeeStrategy, P2PPeerFeeStrategy
from app.domain.value_objects import Currency, Money
from app.infrastructure.concurrency.lock_manager import CanonicalLockManager
from app.ports.cache_port import ICachePort
from app.ports.event_publisher_port import IEventPublisher, TransactionSettledEvent
from app.ports.repository_ports import IAccountRepository, ILedgerRepository


@dataclass(frozen=True)
class TransferCommand:
    """Input parameters for executing a financial transfer."""

    from_account_id: str
    to_account_id: str
    amount: Money | Decimal
    currency: Currency | str | None = None
    fee_strategy: IFeeStrategy | None = None
    fee_account_id: str | None = None
    idempotency_key: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    tenant_id: str = "default"


@dataclass(frozen=True)
class TransferResult:
    """Output DTO containing the result of an executed transfer."""

    transaction_id: str
    from_account_id: str
    to_account_id: str
    amount: Money
    fee: Money
    from_balance_after: Money
    to_balance_after: Money
    status: str
    created_at: float
    ledger_entry_ids: list[str]
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serializes the result to a dictionary for caching and API responses."""
        return {
            "transaction_id": self.transaction_id,
            "from_account_id": self.from_account_id,
            "to_account_id": self.to_account_id,
            "amount": str(self.amount.amount),
            "currency": str(self.amount.currency),
            "fee": str(self.fee.amount),
            "from_balance_after": str(self.from_balance_after.amount),
            "to_balance_after": str(self.to_balance_after.amount),
            "status": self.status,
            "created_at": self.created_at,
            "ledger_entry_ids": list(self.ledger_entry_ids),
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TransferResult":
        """Reconstructs a TransferResult from a serialized dictionary."""
        currency = Currency(data["currency"])
        amount = Money(Decimal(data["amount"]), currency)
        fee = Money(Decimal(data["fee"]), currency)
        from_bal = Money(Decimal(data["from_balance_after"]), currency)
        to_bal = Money(Decimal(data["to_balance_after"]), currency)
        return cls(
            transaction_id=str(data["transaction_id"]),
            from_account_id=str(data["from_account_id"]),
            to_account_id=str(data["to_account_id"]),
            amount=amount,
            fee=fee,
            from_balance_after=from_bal,
            to_balance_after=to_bal,
            status=str(data["status"]),
            created_at=float(data["created_at"]),
            ledger_entry_ids=list(data.get("ledger_entry_ids", [])),
            metadata=dict(data.get("metadata", {})),
        )


class ExecuteTransferUseCase:
    """Use case coordinating atomic, deadlock-free double-entry transfers."""

    DEFAULT_FEE_ACCOUNT_ID = "ACC-SYS-FEE"

    def __init__(
        self,
        account_repo: IAccountRepository,
        ledger_repo: ILedgerRepository,
        lock_manager: CanonicalLockManager | None = None,
        event_publisher: IEventPublisher | None = None,
        cache: ICachePort | None = None,
    ) -> None:
        self.account_repo = account_repo
        self.ledger_repo = ledger_repo
        self.lock_manager = lock_manager or CanonicalLockManager()
        self.event_publisher = event_publisher
        self.cache = cache

    def execute(self, command: TransferCommand) -> TransferResult:
        """Executes a financial transfer with strict invariants and zero deadlocks.

        Args:
            command: Transfer parameters including sender, receiver, and amount.

        Returns:
            TransferResult: Snapshot of completed transaction and updated balances.

        Raises:
            SelfTransferNotAllowedError: If sender and receiver are identical.
            AccountNotFoundError: If sender or receiver accounts do not exist.
            DomainError: On solvency, frozen status, or currency mismatch violation.
            LedgerInvariantViolationError: If double-entry conservation sum != 0.00.
        """
        if command.from_account_id == command.to_account_id:
            raise SelfTransferNotAllowedError(command.from_account_id)

        # 1. Resolve and normalize transfer amount
        transfer_amount: Money
        if isinstance(command.amount, Money):
            transfer_amount = command.amount
        else:
            currency = (
                Currency(command.currency)
                if command.currency is not None
                else Currency.USD
            )
            transfer_amount = Money(command.amount, currency)

        if not transfer_amount.is_positive():
            raise ValueError("Transfer amount must be strictly positive (> 0.00).")

        # 2. Fetch participating accounts
        sender = self.account_repo.get_by_id(command.from_account_id)
        if sender is None:
            raise AccountNotFoundError(command.from_account_id)

        receiver = self.account_repo.get_by_id(command.to_account_id)
        if receiver is None:
            raise AccountNotFoundError(command.to_account_id)

        # 3. Calculate commercial transaction fee
        fee_strategy = command.fee_strategy or P2PPeerFeeStrategy()
        fee = fee_strategy.calculate_fee(transfer_amount)
        has_fee = fee.is_positive()

        fee_account: Account | None = None
        if has_fee:
            fee_acc_id = command.fee_account_id or self.DEFAULT_FEE_ACCOUNT_ID
            fee_account = self.account_repo.get_by_id(fee_acc_id)
            if fee_account is None:
                # Provision system fee treasury if not yet created
                fee_account = Account(
                    account_id=fee_acc_id,
                    owner_name="Platform Fee Treasury",
                    balance=Money.zero(transfer_amount.currency),
                )
                self.account_repo.save(fee_account)

        # 4. Prepare accounts to lock
        accounts_to_lock: list[Account] = [sender, receiver]
        if fee_account is not None and fee_account.account_id not in (
            sender.account_id,
            receiver.account_id,
        ):
            accounts_to_lock.append(fee_account)

        tx_id = str(uuid.uuid4())
        state_machine = TransactionStateMachine(initial_state=TransactionState.INITIATED)

        # 5. Execute within deterministic deadlock-free lock context
        with self.lock_manager.acquire_many(accounts_to_lock):
            try:
                # Reload latest balance and status under lock to prevent stale reads
                fresh_sender = self.account_repo.get_by_id(sender.account_id)
                if fresh_sender is not None:
                    sender.balance = fresh_sender.balance
                    sender.status = fresh_sender.status

                fresh_receiver = self.account_repo.get_by_id(receiver.account_id)
                if fresh_receiver is not None:
                    receiver.balance = fresh_receiver.balance
                    receiver.status = fresh_receiver.status

                if fee_account is not None:
                    fresh_fee = self.account_repo.get_by_id(fee_account.account_id)
                    if fresh_fee is not None:
                        fee_account.balance = fresh_fee.balance
                        fee_account.status = fresh_fee.status

                # State transition: INITIATED -> LOCKED
                state_machine.transition_to(TransactionState.LOCKED)

                # Total debit required from sender (Principal + Fee)
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

                # 9. Atomic persistence
                self.account_repo.save(sender)
                self.account_repo.save(receiver)
                if fee_account is not None and has_fee:
                    self.account_repo.save(fee_account)

                self.ledger_repo.append_entries(entries)

                # 10. Cache invalidation
                if self.cache is not None:
                    self.cache.delete(sender.account_id)
                    self.cache.delete(receiver.account_id)
                    if fee_account is not None:
                        self.cache.delete(fee_account.account_id)

            except DomainError:
                # Mark state machine as FAILED if still in active state
                if state_machine.state in (
                    TransactionState.INITIATED,
                    TransactionState.LOCKED,
                ):
                    try:
                        state_machine.transition_to(TransactionState.FAILED)
                    except Exception:
                        pass
                raise
            except Exception:
                if state_machine.state in (
                    TransactionState.INITIATED,
                    TransactionState.LOCKED,
                ):
                    try:
                        state_machine.transition_to(TransactionState.FAILED)
                    except Exception:
                        pass
                raise

        # 11. Asynchronous event publication (off lock critical path)
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
