"""Production Transfer Engine template for Canonical Lock Ordering.

Demonstrates:
1. Deadlock elimination via monotonic account sorting: min(src, dst) -> max(src, dst).
2. Atomic execution of debits and credits.
3. Creation of balanced, immutable ledger entries.
4. Mathematical invariant validation before commit.
"""

import uuid
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from decimal import Decimal

try:
    from .domain_models import Account, LedgerEntry, Transaction
    from .value_objects import Money
except ImportError:
    from domain_models import Account, LedgerEntry, Transaction  # type: ignore[no-redef]
    from value_objects import Money  # type: ignore[no-redef]


class TransferEngine:
    """Transfer engine demonstrating deadlock elimination and zero-drift invariants."""

    @staticmethod
    def get_canonical_lock_order(account_ids: list[str]) -> list[str]:
        """Returns sorted, deduplicated account IDs to eliminate circular-wait deadlocks."""
        return sorted(set(account_ids))

    async def execute_transfer(
        self,
        from_account: Account,
        to_account: Account,
        amount: Money,
        fee_account: Account | None = None,
        fee_amount: Money | None = None,
    ) -> Transaction:
        """Executes a financial transfer with optional fee.

        Guarantees:
        - Locks are ordered canonically: min(from_id, to_id).
        - Sum(Debits) + Sum(Credits) == 0.00.
        - Negative balances prevented unless explicit overdraft allowed.
        """
        # 1. Self-transfer check
        if from_account.account_id == to_account.account_id:
            raise ValueError("Self-transfers between identical accounts are not permitted.")

        # 2. Canonical lock order calculation
        account_ids = [from_account.account_id, to_account.account_id]
        if fee_account and fee_amount and fee_amount.is_positive():
            account_ids.append(fee_account.account_id)

        canonical_locks = self.get_canonical_lock_order(account_ids)

        # 3. Acquire locks in canonical sorted order
        # (In real Postgres implementation: SELECT ... FOR UPDATE WHERE id IN (...) ORDER BY id ASC)
        async with self._acquire_locks(canonical_locks):
            tx_id = str(uuid.uuid4())
            total_debit = amount
            if fee_amount and fee_amount.is_positive():
                actual_fee = fee_amount
            else:
                actual_fee = Money(Decimal("0.00"), amount.currency)

            if fee_account and actual_fee.is_positive():
                total_debit = amount.add(actual_fee)

            # Solvency check & mutations
            from_account.debit(total_debit)
            to_account.credit(amount)
            if fee_account and actual_fee.is_positive():
                fee_account.credit(actual_fee)

            # Generate balanced immutable ledger entries
            entries = [
                LedgerEntry.create_debit(
                    entry_id=str(uuid.uuid4()),
                    transaction_id=tx_id,
                    account_id=from_account.account_id,
                    amount=total_debit,
                    balance_after=from_account.balance,
                ),
                LedgerEntry.create_credit(
                    entry_id=str(uuid.uuid4()),
                    transaction_id=tx_id,
                    account_id=to_account.account_id,
                    amount=amount,
                    balance_after=to_account.balance,
                ),
            ]

            if fee_account and actual_fee.is_positive():
                entries.append(
                    LedgerEntry.create_credit(
                        entry_id=str(uuid.uuid4()),
                        transaction_id=tx_id,
                        account_id=fee_account.account_id,
                        amount=actual_fee,
                        balance_after=fee_account.balance,
                    )
                )

            transaction = Transaction(
                transaction_id=tx_id,
                from_account_id=from_account.account_id,
                to_account_id=to_account.account_id,
                amount=amount,
                fee=actual_fee,
                status="SETTLED",
                entries=entries,
            )

            # Strict conservation assertion before commit
            transaction.verify_double_entry_balance()
            return transaction

    @asynccontextmanager
    async def _acquire_locks(self, ordered_ids: list[str]) -> AsyncGenerator[None, None]:
        """Placeholder for canonical database or distributed lock acquisition."""
        # Note: Always acquire in the order provided by ordered_ids
        yield
