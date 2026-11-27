"""Seed real demo accounts and initial double-entry ledger postings in PostgreSQL."""

import asyncio
import logging
import uuid
from decimal import Decimal

from sqlalchemy import text

from app.application.use_cases.audit_reconciliation_async import AsyncAuditReconciliationUseCase
from app.infrastructure.persistence.postgres.database import (
    create_async_db_engine,
    get_async_session_factory,
)
from app.infrastructure.persistence.postgres.models import (
    AccountModel,
    LedgerEntryModel,
    TransactionModel,
)
from app.infrastructure.persistence.postgres.unit_of_work import PostgresUnitOfWork

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("seed_demo_data")

async def seed() -> None:
    engine = create_async_db_engine()
    session_factory = get_async_session_factory(engine)
    uow = PostgresUnitOfWork(session_factory)

    logger.info("Connecting to PostgreSQL and resetting demo data...")

    async with engine.begin() as conn:
        # Clean existing test/demo data safely
        await conn.execute(
            text(
                "TRUNCATE TABLE idempotency_records, ledger_entries, "
                "transactions, accounts CASCADE;"
            )
        )

    async with uow:
        assert uow.session is not None
        # 1. Accounts
        accounts = [
            AccountModel(
                id="ACC-001-NORTHSTAR",
                owner_name="Northstar Primary Operations",
                balance=Decimal("10000.0000"),
                currency="BDT",
                status="ACTIVE",
            ),
            AccountModel(
                id="ACC-002-NORTHSTAR",
                owner_name="Apex Settlement Account",
                balance=Decimal("1000.0000"),
                currency="BDT",
                status="ACTIVE",
            ),
            AccountModel(
                id="ACC-003-MERCHANT",
                owner_name="Metro Commerce Vault",
                balance=Decimal("3000.0000"),
                currency="BDT",
                status="ACTIVE",
            ),
            AccountModel(
                id="ACC-004-ESCROW",
                owner_name="Escrow Clearing Reserve",
                balance=Decimal("2000.0000"),
                currency="BDT",
                status="ACTIVE",
            ),
            AccountModel(
                id="ACC-CLEARING-01",
                owner_name="Inter-Account Transit Vault",
                balance=Decimal("0.0000"),
                currency="BDT",
                status="ACTIVE",
            ),
            AccountModel(
                id="ACC-FEE-REVENUE",
                owner_name="Platform Processing Fee Revenue",
                balance=Decimal("45.0000"),
                currency="BDT",
                status="ACTIVE",
            ),
            AccountModel(
                id="ACC-SYSTEM-RESERVE-BDT",
                owner_name="System Capital Reserve (BDT)",
                balance=Decimal("-16045.0000"),
                currency="BDT",
                status="ACTIVE",
            ),
        ]

        for acc in accounts:
            uow.session.add(acc)
        await uow.session.flush()

        # 2. Transactions & Postings
        seed_txns = [
            (
                "TXN-202611-0091",
                "ACC-SYSTEM-RESERVE-BDT",
                "ACC-001-NORTHSTAR",
                Decimal("10000.0000"),
                Decimal("-10000.0000"),
                Decimal("10000.0000"),
            ),
            (
                "TXN-202611-0092",
                "ACC-SYSTEM-RESERVE-BDT",
                "ACC-002-NORTHSTAR",
                Decimal("1000.0000"),
                Decimal("-11000.0000"),
                Decimal("1000.0000"),
            ),
            (
                "TXN-202611-0093",
                "ACC-SYSTEM-RESERVE-BDT",
                "ACC-FEE-REVENUE",
                Decimal("45.0000"),
                Decimal("-11045.0000"),
                Decimal("45.0000"),
            ),
            (
                "TXN-202611-0094",
                "ACC-SYSTEM-RESERVE-BDT",
                "ACC-003-MERCHANT",
                Decimal("3000.0000"),
                Decimal("-14045.0000"),
                Decimal("3000.0000"),
            ),
            (
                "TXN-202611-0095",
                "ACC-SYSTEM-RESERVE-BDT",
                "ACC-004-ESCROW",
                Decimal("2000.0000"),
                Decimal("-16045.0000"),
                Decimal("2000.0000"),
            ),
        ]

        for tx_id, src_id, dest_id, amt, src_bal_after, dest_bal_after in seed_txns:
            tx = TransactionModel(
                id=tx_id,
                idempotency_key=f"idem_seed_{tx_id.lower()}",
                tenant_id="ten_northstar_01",
                source_account_id=src_id,
                destination_account_id=dest_id,
                amount=amt,
                fee=Decimal("0.0000"),
                currency="BDT",
                status="SETTLED",
            )
            uow.session.add(tx)

            # Leg 1: Credit destination
            credit_entry = LedgerEntryModel(
                entry_id=str(uuid.uuid4()),
                transaction_id=tx_id,
                account_id=dest_id,
                amount=amt,
                currency="BDT",
                balance_after=dest_bal_after,
                entry_type="CREDIT",
            )
            # Leg 2: Debit source (signed negative amount in double-entry)
            debit_entry = LedgerEntryModel(
                entry_id=str(uuid.uuid4()),
                transaction_id=tx_id,
                account_id=src_id,
                amount=-amt,
                currency="BDT",
                balance_after=src_bal_after,
                entry_type="DEBIT",
            )
            uow.session.add(credit_entry)
            uow.session.add(debit_entry)

        await uow.commit()
        logger.info("Successfully seeded demo accounts and double-entry postings in PostgreSQL.")

    # Run mathematical audit to verify zero drift
    audit_use_case = AsyncAuditReconciliationUseCase(uow)
    report = await audit_use_case.reconcile()
    logger.info("Mathematical Audit Report:")
    logger.info("Total account balances: %s", report.total_account_balances)
    logger.info("System Net Zero: %s", report.is_system_net_zero)
    logger.info("Balanced: %s", report.is_balanced)
    logger.info("Accounts checked: %d", report.accounts_audited_count)
    logger.info("Ledger entries checked: %d", report.ledger_entries_count)

    await engine.dispose()
    logger.info("Seed data migration completed successfully.")

if __name__ == "__main__":
    asyncio.run(seed())
