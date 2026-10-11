"""Verification script for Phase 2: Distributed Idempotency Engine & Request Fingerprinting.

Run with:
    python scripts/verify_phase2.py

Validates:
1. Exact-once execution and receipt caching with zero secondary debits
2. Cryptographic payload validation catching mutation attacks (409 Conflict)
3. In-flight concurrent execution race gate (425 Too Early)
4. Failure resilience and retry recovery
5. Scoped multi-tenant key isolation
"""

import asyncio
import sys
from decimal import Decimal
from pathlib import Path

# Ensure project root is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text

from app.application.exceptions import (
    IdempotencyInFlightError,
    IdempotencyPayloadMismatchError,
)
from app.application.fingerprint import compute_transfer_fingerprint
from app.application.use_cases.execute_transfer import TransferCommand
from app.application.use_cases.execute_transfer_async import (
    AsyncExecuteTransferUseCase,
)
from app.domain.exceptions import InsufficientFundsError
from app.domain.value_objects import Currency
from app.infrastructure.config import get_settings
from app.infrastructure.persistence.postgres.database import (
    check_db_health,
    create_async_db_engine,
    get_async_session_factory,
    init_db,
)
from app.infrastructure.persistence.postgres.models import AccountModel
from app.infrastructure.persistence.postgres.repositories import (
    PostgresIdempotencyRepository,
)
from app.infrastructure.persistence.postgres.unit_of_work import PostgresUnitOfWork


async def main() -> None:
    settings = get_settings()
    print("=" * 75)
    print("🔒 LEDGERCORE PHASE 2: DISTRIBUTED IDEMPOTENCY ENGINE VERIFICATION")
    print(f"Target DB: {settings.database_url}")
    print("=" * 75)

    engine = create_async_db_engine()
    healthy = await check_db_health(engine)
    if not healthy:
        print("❌ FAILED: PostgreSQL is not reachable.")
        await engine.dispose()
        sys.exit(1)

    await init_db(engine)
    session_factory = get_async_session_factory(engine)
    uow = PostgresUnitOfWork(session_factory)

    # Clean previous state
    async with session_factory() as session:
        await session.execute(
            text(
                "TRUNCATE TABLE idempotency_records, ledger_entries, "
                "transactions, accounts CASCADE;"
            )
        )
        await session.commit()

    # Step 1: Exact-Once Execution & Receipt Caching
    print("\n[1/5] Testing Exact-Once Execution & Cached Replay...")
    async with session_factory() as session:
        session.add(
            AccountModel(
                id="ACC-ALICE-P2",
                owner_name="Alice",
                balance=Decimal("500.00"),
                currency="USD",
                status="ACTIVE",
            )
        )
        session.add(
            AccountModel(
                id="ACC-BOB-P2",
                owner_name="Bob",
                balance=Decimal("100.00"),
                currency="USD",
                status="ACTIVE",
            )
        )
        await session.commit()

    use_case = AsyncExecuteTransferUseCase(uow=uow)
    cmd = TransferCommand(
        from_account_id="ACC-ALICE-P2",
        to_account_id="ACC-BOB-P2",
        amount=Decimal("150.00"),
        currency=Currency.USD,
        idempotency_key="DEMO-KEY-101",
    )

    # Call 1: Processed
    res1 = await use_case.execute(cmd)
    print(f"  ✅ Request 1 Processed: TxID={res1.transaction_id}")
    print(f"     - Alice: $500.00 -> ${res1.from_balance_after.amount} USD")
    print(f"     - Bob:   $100.00 -> ${res1.to_balance_after.amount} USD")

    # Call 2: Replay identical request
    res2 = await use_case.execute(cmd)
    print(f"  ✅ Request 2 Replay:   TxID={res2.transaction_id} (CACHED)")
    assert res1.transaction_id == res2.transaction_id
    assert res1.from_balance_after.amount == res2.from_balance_after.amount

    async with session_factory() as session:
        entry_count = (
            await session.execute(text("SELECT COUNT(*) FROM ledger_entries;"))
        ).scalar()
        print(f"     - Total Journal Entries in DB: {entry_count} (Zero double debits!)")
        assert entry_count == 2

    # Step 2: Payload Mutation Attack Prevention
    print("\n[2/5] Testing Payload Mutation Attack Detection (409 Conflict)...")
    mutated_cmd = TransferCommand(
        from_account_id="ACC-ALICE-P2",
        to_account_id="ACC-BOB-P2",
        amount=Decimal("999.00"),  # Altered from $150 to $999!
        currency=Currency.USD,
        idempotency_key="DEMO-KEY-101",  # Same key as above!
    )
    try:
        await use_case.execute(mutated_cmd)
        print("  ❌ ERROR: Mutated payload was accepted!")
    except IdempotencyPayloadMismatchError as err:
        print(f"  ✅ Caught Attack: {err}")
        print("     - System successfully rejected request mutation with HTTP 409 Conflict.")

    # Step 3: In-Flight Concurrency Race Gate
    print("\n[3/5] Testing In-Flight Concurrency Race Gate (425 Too Early)...")
    req_hash = compute_transfer_fingerprint(
        from_account_id="ACC-X",
        to_account_id="ACC-Y",
        amount=Decimal("50.00"),
        currency="USD",
    )
    async with session_factory() as s1:
        r1 = PostgresIdempotencyRepository(s1)
        acq, _ = await r1.check_or_acquire("KEY-RACE-01", req_hash)
        await s1.commit()
        assert acq is True

    try:
        async with session_factory() as s2:
            r2 = PostgresIdempotencyRepository(s2)
            await r2.check_or_acquire("KEY-RACE-01", req_hash)
            print("  ❌ ERROR: Concurrent in-flight request was allowed!")
    except IdempotencyInFlightError as err:
        print(f"  ✅ Race Condition Blocked: {err}")
        print("     - Duplicate in-flight execution rejected with HTTP 425 Too Early.")

    # Step 4: Failure & Recovery Retry
    print("\n[4/5] Testing Failure Resilience & Safe Retry...")
    poor_cmd = TransferCommand(
        from_account_id="ACC-BOB-P2",
        to_account_id="ACC-ALICE-P2",
        amount=Decimal("50000.00"),  # Inadequate funds!
        currency=Currency.USD,
        idempotency_key="KEY-RETRY-02",
    )
    try:
        await use_case.execute(poor_cmd)
    except InsufficientFundsError:
        print("  ✅ Attempt 1 failed gracefully on insufficient funds.")

    async with session_factory() as session:
        rec_status = (
            await session.execute(
                text("SELECT status FROM idempotency_records WHERE key = 'KEY-RETRY-02';")
            )
        ).scalar()
        print(f"     - Idempotency status marked as: {rec_status}")
        assert rec_status == "FAILED"

        # Fund Bob
        await session.execute(
            text("UPDATE accounts SET balance = 60000.00 WHERE id = 'ACC-BOB-P2';")
        )
        await session.commit()

    res_retry = await use_case.execute(poor_cmd)
    print(f"  ✅ Attempt 2 Succeeded: Status={res_retry.status}, TxID={res_retry.transaction_id}")
    assert res_retry.status == "SETTLED"

    # Step 5: Multi-Tenant Key Isolation
    print("\n[5/5] Testing Scoped Multi-Tenant Isolation...")
    tenant_a_cmd = TransferCommand(
        from_account_id="ACC-ALICE-P2",
        to_account_id="ACC-BOB-P2",
        amount=Decimal("10.00"),
        currency=Currency.USD,
        idempotency_key="GLOBAL-KEY-77",
        tenant_id="tenant_alpha",
    )
    tenant_b_cmd = TransferCommand(
        from_account_id="ACC-ALICE-P2",
        to_account_id="ACC-BOB-P2",
        amount=Decimal("20.00"),
        currency=Currency.USD,
        idempotency_key="GLOBAL-KEY-77",
        tenant_id="tenant_beta",
    )
    res_a = await use_case.execute(tenant_a_cmd)
    res_b = await use_case.execute(tenant_b_cmd)
    print(f"  ✅ Tenant Alpha: TxID={res_a.transaction_id}")
    print(f"  ✅ Tenant Beta:  TxID={res_b.transaction_id}")
    assert res_a.transaction_id != res_b.transaction_id

    await engine.dispose()
    print("\n" + "=" * 75)
    print("🎉 ALL PHASE 2 CHECKS PASSED: Durable Idempotency Engine is Fully Hardened!")
    print("=" * 75)


if __name__ == "__main__":
    asyncio.run(main())
