"""Production Domain Entities template for double-entry financial ledgers.

Contains:
1. Account: balance encapsulation and solvency invariant.
2. LedgerEntry: immutable, append-only journal record.
3. Transaction: composite transaction grouping balanced entries.
"""

import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum

try:
    from .value_objects import Money
except ImportError:
    from value_objects import Money  # type: ignore[no-redef]


class AccountStatus(StrEnum):
    ACTIVE = "ACTIVE"
    FROZEN = "FROZEN"
    CLOSED = "CLOSED"


class EntryType(StrEnum):
    DEBIT = "DEBIT"
    CREDIT = "CREDIT"


class InsufficientFundsError(Exception):
    """Raised when an account does not have enough balance for a debit."""
    pass


class LedgerInvariantViolationError(Exception):
    """Raised when double-entry conservation (sum debits == sum credits) is violated."""
    pass


@dataclass
class Account:
    """Financial account entity encapsulating balance integrity."""

    account_id: str
    owner_name: str
    balance: Money
    status: AccountStatus = AccountStatus.ACTIVE

    def debit(self, amount: Money) -> None:
        """Debits funds from the account, enforcing solvency."""
        if self.status != AccountStatus.ACTIVE:
            raise ValueError(f"Account {self.account_id} is {self.status} and cannot be debited.")
        if not amount.is_positive():
            raise ValueError("Debit amount must be strictly positive.")
        if self.balance < amount:
            raise InsufficientFundsError(
                f"Account {self.account_id} balance {self.balance} < {amount}"
            )
        self.balance = self.balance.subtract(amount)

    def credit(self, amount: Money) -> None:
        """Credits funds to the account."""
        if self.status != AccountStatus.ACTIVE:
            raise ValueError(f"Account {self.account_id} is {self.status} and cannot be credited.")
        if not amount.is_positive():
            raise ValueError("Credit amount must be strictly positive.")
        self.balance = self.balance.add(amount)


@dataclass(frozen=True)
class LedgerEntry:
    """Immutable, append-only journal record.

    Convention:
    - DEBIT amounts are stored as negative Decimal (-abs(amount)).
    - CREDIT amounts are stored as positive Decimal (+abs(amount)).
    - Global conservation: sum(entry.amount for entry in transaction.entries) == Decimal("0.00").
    """

    entry_id: str
    transaction_id: str
    account_id: str
    amount: Decimal
    balance_after: Decimal
    entry_type: EntryType
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        if self.entry_type == EntryType.DEBIT and self.amount > Decimal("0.00"):
            raise ValueError(f"Debit entry amount must be <= 0.00, got {self.amount}")
        if self.entry_type == EntryType.CREDIT and self.amount < Decimal("0.00"):
            raise ValueError(f"Credit entry amount must be >= 0.00, got {self.amount}")

    @classmethod
    def create_debit(
        cls,
        entry_id: str,
        transaction_id: str,
        account_id: str,
        amount: Money | Decimal,
        balance_after: Money | Decimal,
    ) -> "LedgerEntry":
        raw_amt = amount.amount if isinstance(amount, Money) else amount
        bal_after = balance_after.amount if isinstance(balance_after, Money) else balance_after
        return cls(
            entry_id=entry_id,
            transaction_id=transaction_id,
            account_id=account_id,
            amount=-abs(raw_amt),
            balance_after=bal_after,
            entry_type=EntryType.DEBIT,
        )

    @classmethod
    def create_credit(
        cls,
        entry_id: str,
        transaction_id: str,
        account_id: str,
        amount: Money | Decimal,
        balance_after: Money | Decimal,
    ) -> "LedgerEntry":
        raw_amt = amount.amount if isinstance(amount, Money) else amount
        bal_after = balance_after.amount if isinstance(balance_after, Money) else balance_after
        return cls(
            entry_id=entry_id,
            transaction_id=transaction_id,
            account_id=account_id,
            amount=abs(raw_amt),
            balance_after=bal_after,
            entry_type=EntryType.CREDIT,
        )


@dataclass
class Transaction:
    """Financial transaction grouping balanced double-entry ledger entries."""

    transaction_id: str
    from_account_id: str
    to_account_id: str
    amount: Money
    fee: Money = field(default_factory=lambda: Money(Decimal("0.00")))
    status: str = "INITIATED"
    fee_account_id: str | None = None
    currency: str = "USD"
    idempotency_key: str = ""
    entries: list[LedgerEntry] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)

    def verify_double_entry_balance(self) -> bool:
        """Verifies that sum(signed_amounts) == Decimal('0.00')."""
        if not self.entries:
            return False
        total_drift = sum((e.amount for e in self.entries), Decimal("0.00"))
        if total_drift != Decimal("0.00"):
            raise LedgerInvariantViolationError(
                f"Transaction {self.transaction_id} is unbalanced. Net drift: {total_drift}"
            )
        return True
