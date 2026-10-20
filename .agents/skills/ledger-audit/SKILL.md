---
name: ledger-audit
description: >-
  Audits double-entry ledger invariants, verifies zero financial drift across accounts,
  and executes mathematical reconciliation tests in LedgerCore. Use when verifying
  balance integrity, debugging balance discrepancies, or validating transfer invariants.
---

# Ledger Invariant Audit Runbook

This skill provides step-by-step procedures for auditing financial conservation and balance integrity in LedgerCore.

## 1. When to Use
Activate this skill whenever:
- User asks to verify ledger invariants or check for financial drift.
- Inspecting discrepancies between debits and credits.
- Validating transactions after running load or concurrency benchmarks.

## 2. Invariant Rules
In double-entry bookkeeping:
1. Every transfer consists of balanced journal entries:
   $$\sum \text{Debits} = \sum \text{Credits}$$
2. The global sum of all posted journal entry amounts must equal zero:
   $$\text{Drift} = \sum_{\text{all entries}} \text{signed\_amount} \equiv 0$$
3. No account balance may drop below zero unless explicitly defined as an overdraft-enabled clearing account.

## 3. Execution Procedure

### Step 1: Execute Automated Invariant Suite
Run the provided helper script:
```bash
.agents/skills/ledger-audit/scripts/run_audit.sh
```

### Step 2: Run Unit Invariant Tests
Directly test domain-level conservation:
```bash
.venv/bin/pytest tests/unit/domain/test_money.py tests/unit/domain/test_journal_entry.py -v
```

### Step 3: Check Database Drift
If PostgreSQL is running, run the asynchronous reconciliation use case:
```bash
.venv/bin/python -c "
import asyncio
from app.infrastructure.persistence.postgres.database import get_async_session_factory
from app.application.use_cases.audit_reconciliation_async import AsyncAuditReconciliationUseCase
from app.infrastructure.persistence.postgres.unit_of_work import PostgresUnitOfWork

async def check():
    factory = get_async_session_factory()
    uow = PostgresUnitOfWork(factory)
    use_case = AsyncAuditReconciliationUseCase(uow)
    report = await use_case.execute()
    print('Audit Status:', report.status, 'Total Drift:', report.total_drift)

asyncio.run(check())
"
```

## 4. Troubleshooting Discrepancies
- If `total_drift != 0`:
  1. Inspect the last committed `TransferCommand` in `app/application/use_cases/execute_transfer.py`.
  2. Verify if fees were split into a separate debit entry without a matching credit entry on the platform fee account.
  3. Ensure no uncommitted partial entries leaked into the database.
