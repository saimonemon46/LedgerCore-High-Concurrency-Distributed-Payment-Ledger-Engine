"""Locust distributed load testing benchmark for LedgerCore.

Simulates realistic production traffic distribution:
- 70% Transfer Transactions (POST /api/v1/transfers) with 10% mobile idempotency retries.
- 25% Balance Queries (GET /api/v1/accounts/{id}/balance) testing L1 Cache-Aside.
- 5% Mathematical Audit Reconciliations (POST /api/v1/audit/reconcile).

Target SLAs:
- Throughput: > 1,000 QPS
- Latency (P95): <= 22ms
- Error Rate: 0.0%
"""

import random
import uuid
from decimal import Decimal

from locust import HttpUser, between, task


class LedgerCoreUser(HttpUser):
    """Simulated mobile banking client hammering LedgerCore."""

    wait_time = between(0.001, 0.005)  # High throughput simulation
    account_ids: list[str] = [f"LOCUST-ACC-{i}" for i in range(1, 51)]

    def on_start(self) -> None:
        """Provisions accounts on worker start."""
        # Provision initial accounts with $10,000 each
        for acc_id in self.account_ids[:10]:
            with self.client.post(
                "/api/v1/accounts",
                json={
                    "account_id": acc_id,
                    "owner_name": f"User {acc_id}",
                    "initial_balance": "10000.00",
                    "currency": "USD",
                },
                catch_response=True,
                name="/api/v1/accounts (seed)",
            ) as response:
                if response.status_code in (201, 409):
                    response.success()
                else:
                    response.failure(f"Seeding failed: {response.status_code}")

    @task(70)
    def transfer_money(self) -> None:
        """Executes a financial transfer with 10% retry storm probability."""
        sender, receiver = random.sample(self.account_ids[:10], 2)
        amount = f"{random.randint(1, 10)}.00"

        # 10% chance to simulate a mobile packet retransmit with same key
        if random.random() < 0.10:
            idempotency_key = f"retry-storm-{random.randint(1, 20)}"
        else:
            idempotency_key = f"mobile-tx-{uuid.uuid4()}"

        headers = {"Idempotency-Key": idempotency_key}
        payload = {
            "from_account_id": sender,
            "to_account_id": receiver,
            "amount": amount,
            "currency": "USD",
            "fee_strategy_type": "P2P",
        }

        with self.client.post(
            "/api/v1/transfers",
            json=payload,
            headers=headers,
            catch_response=True,
            name="/api/v1/transfers",
        ) as response:
            if response.status_code in (200, 409, 422):
                # 200: Transfer posted or idempotent replay returned
                # 409: Idempotency conflict / in-flight lock during retry storm
                # 422: Valid rejection if an account runs out of funds during race
                response.success()
            else:
                response.failure(f"Unexpected status: {response.status_code} - {response.text}")

    @task(25)
    def query_balance(self) -> None:
        """Queries account balance, exercising L1 Cache-Aside path."""
        acc_id = random.choice(self.account_ids[:10])
        with self.client.get(
            f"/api/v1/accounts/{acc_id}/balance",
            catch_response=True,
            name="/api/v1/accounts/[id]/balance",
        ) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Balance query failed: {response.status_code}")

    @task(5)
    def audit_reconciliation(self) -> None:
        """Triggers real-time mathematical ledger reconciliation."""
        with self.client.post(
            "/api/v1/audit/reconcile",
            catch_response=True,
            name="/api/v1/audit/reconcile",
        ) as response:
            if response.status_code == 200:
                data = response.json()
                net_zero = Decimal(data.get("total_system_net", "1")) == Decimal("0.00")
                if net_zero:
                    response.success()
                else:
                    response.failure(f"Zero-sum invariant broken: {data}")
            else:
                response.failure(f"Audit endpoint error: {response.status_code}")
