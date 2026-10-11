"""Async PostgreSQL Audit Reconciliation Use Case for LedgerCore.

Performs mathematical verification of the core double-entry bookkeeping invariant:
1. Total system net of all ledger entries must be strictly 0.00 (Zero-Sum Law).
2. Every account balance must strictly reconcile with its historical ledger journal.
"""

import time
from collections import defaultdict
from decimal import Decimal

from app.application.exceptions import ReconciliationDivergenceError
from app.application.use_cases.audit_reconciliation import (
    AccountDiscrepancy,
    ReconciliationReport,
)
from app.domain.models import LedgerEntry
from app.infrastructure.persistence.postgres.unit_of_work import PostgresUnitOfWork


class AsyncAuditReconciliationUseCase:
    """Audits system-wide financial invariants directly against PostgreSQL tables."""

    def __init__(self, uow: PostgresUnitOfWork) -> None:
        self.uow = uow

    async def reconcile(self, raise_on_error: bool = False) -> ReconciliationReport:
        """Executes a full mathematical reconciliation of the PostgreSQL ledger.

        Args:
            raise_on_error: If True, raises ReconciliationDivergenceError on divergence.

        Returns:
            ReconciliationReport: Audit findings and discrepancy breakdown.
        """
        now = time.time()

        async with self.uow as uow:
            accounts = await uow.accounts.get_all()
            all_entries = await uow.ledger.get_all_entries()

        # 1. Calculate system-wide ledger totals
        total_credits = Decimal("0.00")
        total_debits = Decimal("0.00")
        total_system_net = Decimal("0.00")

        entries_by_account: dict[str, list[LedgerEntry]] = defaultdict(list)
        for entry in all_entries:
            total_system_net += entry.amount
            if entry.amount > Decimal("0.00"):
                total_credits += entry.amount
            else:
                total_debits += entry.amount
            entries_by_account[entry.account_id].append(entry)

        # 2. Reconcile individual account balances
        total_balances = Decimal("0.00")
        discrepancies: list[AccountDiscrepancy] = []

        for acc in accounts:
            current_bal = acc.balance.amount
            total_balances += current_bal

            acc_entries = entries_by_account.get(acc.account_id, [])
            if acc_entries:
                latest_entry = acc_entries[-1]
                expected_bal = latest_entry.balance_after
                if current_bal != expected_bal:
                    diff = current_bal - expected_bal
                    discrepancies.append(
                        AccountDiscrepancy(
                            account_id=acc.account_id,
                            actual_balance=current_bal,
                            expected_balance=expected_bal,
                            discrepancy=diff,
                        )
                    )

        is_net_zero = (total_system_net == Decimal("0.00"))
        is_balanced = is_net_zero and (len(discrepancies) == 0)

        report = ReconciliationReport(
            total_account_balances=total_balances,
            total_ledger_credits=total_credits,
            total_ledger_debits=total_debits,
            total_system_net=total_system_net,
            is_system_net_zero=is_net_zero,
            is_balanced=is_balanced,
            accounts_audited_count=len(accounts),
            ledger_entries_count=len(all_entries),
            discrepancies=discrepancies,
            timestamp=now,
        )

        if raise_on_error and not is_balanced:
            raise ReconciliationDivergenceError(
                divergence=total_system_net,
                details=report.to_dict(),
            )

        return report
