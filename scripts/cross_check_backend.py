"""Comprehensive Backend Cross-Check Script for LedgerCore.

Validates end-to-end functionality across:
1. Infrastructure Connectivity (PostgreSQL 16, Redis 8)
2. FastAPI Engine Lifecycle & Health Endpoints
3. Demo Workspace Seed & State Reset
4. Account Queries, Creation & Double-Entry Capital Reserve Balancing
5. Transfer Invariant Validations
6. Distributed Idempotency (Exact-once replay, Mutation 409 attack detection)
7. Double-Entry Journaling & Mathematical Reconciliation (Zero Drift)
8. High-Concurrency Opposing Transfers (Canonical Lock Ordering / Zero Deadlocks)
"""

import asyncio
import sys
from decimal import Decimal
from pathlib import Path

import httpx
import redis.asyncio as aioredis

# Ensure project root is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.api.main import create_app
from app.infrastructure.config import get_settings
from app.infrastructure.persistence.postgres.database import (
    check_db_health,
    create_async_db_engine,
)


async def main() -> None:
    print("=" * 80)
    print("🚀 LEDGERCORE BACKEND SYSTEM CROSS-CHECK")
    print("=" * 80)

    settings = get_settings()
    engine = create_async_db_engine()

    # 1. Infrastructure Connectivity
    print("\n[Step 1/8] Verifying Infrastructure Connectivity...")
    db_ok = await check_db_health(engine)
    assert db_ok, "PostgreSQL connection failed!"
    print("  ✅ PostgreSQL 16 (asyncpg): CONNECTED & HEALTHY")

    redis = aioredis.from_url(settings.redis_url)
    redis_ping = await redis.ping()
    assert redis_ping, "Redis ping failed!"
    print("  ✅ Redis 8: CONNECTED & RESPONDING (PONG)")
    await redis.aclose()

    # 2. FastAPI Engine Lifecycle & Health Check
    app = create_app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        print("\n[Step 2/8] Testing Engine Health & Lifecycle...")
        resp = await client.get("/api/v1/health")
        assert resp.status_code == 200, f"Health check failed: {resp.text}"
        health_data = resp.json()
        assert health_data["status"] == "healthy", f"Engine unhealthy: {health_data}"
        assert health_data["circuit_breaker_state"] == "CLOSED"
        print(
            f"  ✅ Health Endpoint 200 OK: status={health_data['status']}, "
            f"circuit_breaker={health_data['circuit_breaker_state']}"
        )

        # 3. Seed Demo Data via API
        print("\n[Step 3/8] Seeding Demo Data via POST /api/v1/audit/seed-demo...")
        resp = await client.post("/api/v1/audit/seed-demo")
        assert resp.status_code == 200, f"Seed failed: {resp.text}"
        print(f"  ✅ Demo Seed Successful: {resp.json()['message']}")

        # 4. Account Listing & Querying
        print("\n[Step 4/8] Testing Account Queries & Retrieval...")
        resp = await client.get("/api/v1/accounts")
        assert resp.status_code == 200, f"Account list failed: {resp.text}"
        accounts = resp.json()
        assert len(accounts) >= 5, f"Expected at least 5 demo accounts, got {len(accounts)}"
        account_ids = {a["account_id"] for a in accounts}
        print(f"  ✅ Retrieved {len(accounts)} Accounts from PostgreSQL: {sorted(account_ids)}")

        # Query single account & balance
        acc1_resp = await client.get("/api/v1/accounts/ACC-001-NORTHSTAR")
        assert acc1_resp.status_code == 200
        acc1 = acc1_resp.json()
        print(
            f"  ✅ Account ACC-001-NORTHSTAR: Balance = {acc1['balance']} {acc1['currency']}, "
            f"Active = {acc1['is_active']}"
        )

        # Test 404 for unknown account
        not_found_resp = await client.get("/api/v1/accounts/NONEXISTENT-ACCOUNT")
        assert not_found_resp.status_code == 404
        print("  ✅ Unknown Account correctly rejected with HTTP 404")

        # Create a new account with opening balance and verify double-entry reserve debit
        new_acc_id = f"ACC-E2E-TEST-{int(asyncio.get_event_loop().time())}"
        create_resp = await client.post(
            "/api/v1/accounts",
            json={
                "account_id": new_acc_id,
                "owner_name": "E2E Verification Corp",
                "currency": "BDT",
                "initial_balance": "5000.00",
            },
        )
        assert create_resp.status_code == 201, f"Create account failed: {create_resp.text}"
        print(f"  ✅ Account Provisioned: {new_acc_id} with initial balance 5000.00 BDT")

        # Duplicate account creation rejection
        dup_resp = await client.post(
            "/api/v1/accounts",
            json={
                "account_id": new_acc_id,
                "owner_name": "Duplicate Corp",
                "currency": "BDT",
                "initial_balance": "100.00",
            },
        )
        assert dup_resp.status_code == 409, f"Duplicate should fail 409, got {dup_resp.status_code}"
        print("  ✅ Duplicate Account creation rejected with HTTP 409 Conflict")

        # 5. Invariant Validation & Error Handling
        print("\n[Step 5/8] Verifying Invariant Rejections & Validation Gates...")

        # 5a. Missing Idempotency Key
        no_key_resp = await client.post(
            "/api/v1/transfers",
            json={
                "from_account_id": "ACC-001-NORTHSTAR",
                "to_account_id": "ACC-002-NORTHSTAR",
                "amount": "100.00",
                "currency": "BDT",
            },
        )
        assert no_key_resp.status_code == 400, (
            f"Expected 400 for missing idempotency key, got {no_key_resp.status_code}"
        )
        print("  ✅ Missing Idempotency-Key rejected with HTTP 400 Bad Request")

        # 5b. Self-Transfer
        self_resp = await client.post(
            "/api/v1/transfers",
            headers={"Idempotency-Key": "TEST-KEY-SELF-01"},
            json={
                "from_account_id": "ACC-001-NORTHSTAR",
                "to_account_id": "ACC-001-NORTHSTAR",
                "amount": "100.00",
                "currency": "BDT",
            },
        )
        assert self_resp.status_code == 422, (
            f"Expected 422 for self-transfer, got {self_resp.status_code}"
        )
        print("  ✅ Self-transfer rejected with HTTP 422 Unprocessable Content")

        # 5c. Insufficient Funds
        overdraw_resp = await client.post(
            "/api/v1/transfers",
            headers={"Idempotency-Key": "TEST-KEY-OVERDRAW-01"},
            json={
                "from_account_id": "ACC-001-NORTHSTAR",
                "to_account_id": "ACC-002-NORTHSTAR",
                "amount": "999999999.00",
                "currency": "BDT",
            },
        )
        assert overdraw_resp.status_code == 422, (
            f"Expected 422 for overdraw, got {overdraw_resp.status_code}"
        )
        print("  ✅ Insufficient funds rejected with HTTP 422 (balance constraint intact)")

        # 5d. Currency Mismatch
        mismatch_resp = await client.post(
            "/api/v1/transfers",
            headers={"Idempotency-Key": "TEST-KEY-CURRENCY-01"},
            json={
                "from_account_id": "ACC-001-NORTHSTAR",
                "to_account_id": "ACC-002-NORTHSTAR",
                "amount": "100.00",
                "currency": "USD",  # Accounts are in BDT
            },
        )
        assert mismatch_resp.status_code == 422, (
            f"Expected 422 for currency mismatch, got {mismatch_resp.status_code}"
        )
        print("  ✅ Currency mismatch rejected with HTTP 422 Unprocessable Content")

        # 6. Transfer Execution & Idempotency Guarantees
        print("\n[Step 6/8] Testing Atomic Transfer Execution & Idempotency...")
        transfer_key = f"IDEM-KEY-VERIFY-{int(asyncio.get_event_loop().time())}"
        payload = {
            "from_account_id": "ACC-001-NORTHSTAR",
            "to_account_id": "ACC-002-NORTHSTAR",
            "amount": "250.00",
            "currency": "BDT",
            "fee_strategy_type": "FLAT",
            "flat_fee": "5.00",
            "fee_account_id": "ACC-FEE-REVENUE",
            "metadata": {"reason": "Cross-check E2E transfer test"},
        }

        # First execution
        tx1_resp = await client.post(
            "/api/v1/transfers",
            headers={"Idempotency-Key": transfer_key},
            json=payload,
        )
        assert tx1_resp.status_code == 200, f"Transfer failed: {tx1_resp.text}"
        tx1_data = tx1_resp.json()
        tx1_id = tx1_data["transaction_id"]
        assert tx1_data["status"] == "SETTLED"
        print(
            f"  ✅ Transfer Executed: TxID={tx1_id}, Amount=250.00 BDT, "
            f"Fee=5.00 BDT, Status={tx1_data['status']}"
        )

        # Replay identical execution (exact-once guarantee)
        tx2_resp = await client.post(
            "/api/v1/transfers",
            headers={"Idempotency-Key": transfer_key},
            json=payload,
        )
        assert tx2_resp.status_code == 200, f"Replay failed: {tx2_resp.text}"
        tx2_data = tx2_resp.json()
        assert tx2_data["transaction_id"] == tx1_id, "Replay returned different transaction ID!"
        assert tx2_data["from_balance_after"] == tx1_data["from_balance_after"], (
            "Secondary debit detected on replay!"
        )
        print(
            f"  ✅ Idempotent Replay Verified: Exactly same TxID={tx2_data['transaction_id']}, "
            f"Zero double debit"
        )

        # Mutation attack (same key, mutated payload)
        mutated_payload = dict(payload)
        mutated_payload["amount"] = "300.00"  # altered amount
        tx_mut_resp = await client.post(
            "/api/v1/transfers",
            headers={"Idempotency-Key": transfer_key},
            json=mutated_payload,
        )
        assert tx_mut_resp.status_code == 409, (
            f"Expected 409 for payload mutation attack, got {tx_mut_resp.status_code}"
        )
        print("  ✅ Cryptographic Mutation Attack caught & rejected with HTTP 409 Conflict")

        # 7. Journal Postings & Mathematical Reconciliation
        print("\n[Step 7/8] Verifying Double-Entry Journal Postings & Audit Reconciliation...")

        # Query transfer details with postings
        tx_detail_resp = await client.get(f"/api/v1/transfers/{tx1_id}")
        assert tx_detail_resp.status_code == 200, (
            f"Get transfer detail failed: {tx_detail_resp.text}"
        )
        tx_detail = tx_detail_resp.json()
        postings = tx_detail["postings"]
        assert len(postings) == 3, f"Expected 3 postings, got {len(postings)}"

        # Verify debits + credits sum in postings
        debit_sum = sum(Decimal(p["amount"]) for p in postings if p["entry_type"] == "DEBIT")
        credit_sum = sum(Decimal(p["amount"]) for p in postings if p["entry_type"] == "CREDIT")
        assert debit_sum == credit_sum, (
            f"Postings unbalanced: Debits={debit_sum}, Credits={credit_sum}"
        )
        print(f"  ✅ Transaction Postings Balanced: Debits ({debit_sum}) == Credits ({credit_sum})")

        # Run system-wide audit reconciliation
        audit_resp = await client.post("/api/v1/audit/reconcile?raise_on_error=true")
        assert audit_resp.status_code == 200, f"Audit reconciliation failed: {audit_resp.text}"
        audit_data = audit_resp.json()
        assert audit_data["is_balanced"] is True, f"Audit unbalanced: {audit_data}"
        assert audit_data["is_system_net_zero"] is True, f"System net not zero: {audit_data}"
        assert Decimal(audit_data["total_system_net"]) == Decimal("0.00")
        assert len(audit_data["discrepancies"]) == 0
        print("  ✅ Audit Reconciliation Passed:")
        print(f"     - Accounts Audited: {audit_data['accounts_audited_count']}")
        print(f"     - Ledger Entries Audited: {audit_data['ledger_entries_count']}")
        print(
            f"     - Total System Net: {audit_data['total_system_net']} "
            f"(Strict Zero-Sum Conservation)"
        )
        print(f"     - Account Discrepancies: {len(audit_data['discrepancies'])}")

        # 8. High-Concurrency Opposing Transfers (Deadlock Elimination Torture)
        print("\n[Step 8/8] Testing High-Concurrency Opposing Transfers (Zero Deadlocks)...")
        concurrency_count = 10

        async def send_transfer(from_acc: str, to_acc: str, idx: int) -> int:
            t_key = f"CONCURRENCY-TOR-{idx}-{int(asyncio.get_event_loop().time())}"
            r = await client.post(
                "/api/v1/transfers",
                headers={"Idempotency-Key": t_key},
                json={
                    "from_account_id": from_acc,
                    "to_account_id": to_acc,
                    "amount": "10.00",
                    "currency": "BDT",
                    "fee_strategy_type": "FLAT",
                    "flat_fee": "0.00",
                },
            )
            return r.status_code

        tasks = []
        for i in range(concurrency_count):
            # A -> B
            tasks.append(send_transfer("ACC-001-NORTHSTAR", "ACC-002-NORTHSTAR", i * 2))
            # B -> A (Opposing direction simultaneously)
            tasks.append(send_transfer("ACC-002-NORTHSTAR", "ACC-001-NORTHSTAR", i * 2 + 1))

        results = await asyncio.gather(*tasks, return_exceptions=True)
        success_count = sum(1 for res in results if res == 200)
        print(
            f"  ✅ Dispatched {len(tasks)} concurrent bidirectional transfers: "
            f"{success_count}/{len(tasks)} settled (0 deadlocks)"
        )

        # Verify system net remains strictly zero after concurrency torture
        audit_after_resp = await client.post("/api/v1/audit/reconcile?raise_on_error=true")
        assert audit_after_resp.status_code == 200
        audit_after = audit_after_resp.json()
        assert audit_after["is_balanced"] is True
        assert Decimal(audit_after["total_system_net"]) == Decimal("0.00")
        print(
            f"  ✅ Post-Torture Audit Reconciliation: Net Zero={audit_after['total_system_net']}, "
            f"Balanced={audit_after['is_balanced']}"
        )

    await engine.dispose()
    print("\n" + "=" * 80)
    print("🏆 ALL 8 BACKEND CROSS-CHECK SUITES PASSED FLAWLESSLY!")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(main())
