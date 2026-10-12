"""Verification test suite for LedgerCore FastAPI REST endpoints."""

import asyncio
from collections.abc import Generator
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.api.dependencies import Container
from app.api.main import app
from app.infrastructure.persistence.postgres.database import (
    check_db_health,
    create_async_db_engine,
    init_db,
)
from app.infrastructure.resilience.circuit_breaker import CircuitState


@pytest.fixture(autouse=True)
def reset_services() -> Generator[None, None, None]:
    """Resets container state and truncates PostgreSQL tables between tests."""
    Container.reset()

    async def _clean() -> None:
        engine = create_async_db_engine()
        try:
            if await check_db_health(engine):
                await init_db(engine)
                async with engine.begin() as conn:
                    await conn.execute(
                        text(
                            "TRUNCATE TABLE idempotency_records, ledger_entries, "
                            "transactions, accounts CASCADE;"
                        )
                    )
        finally:
            await engine.dispose()

    asyncio.run(_clean())
    yield
    Container.reset()


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    """TestClient fixture with context manager lifespan trigger."""
    with TestClient(app) as test_client:
        yield test_client


class TestHealthEndpoint:
    """Verifies service liveness and health diagnostics."""

    def test_health_check_healthy(self, client: TestClient) -> None:
        response = client.get("/api/v1/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["circuit_breaker_state"] == "CLOSED"
        assert "timestamp" in data


class TestAccountsEndpoints:
    """Verifies account creation and balance queries."""

    def test_create_and_query_account(self, client: TestClient) -> None:
        # Create account
        payload = {
            "account_id": "ACC-ALICE-1",
            "owner_name": "Alice Smith",
            "initial_balance": "500.00",
            "currency": "USD",
        }
        create_res = client.post("/api/v1/accounts", json=payload)
        assert create_res.status_code == 201
        data = create_res.json()
        assert data["account_id"] == "ACC-ALICE-1"
        assert data["balance"] == "500.00"
        assert data["currency"] == "USD"
        assert data["is_active"] is True

        # Query balance (Cache Miss)
        get_res1 = client.get("/api/v1/accounts/ACC-ALICE-1/balance")
        assert get_res1.status_code == 200
        assert get_res1.json()["balance"] == "500.00"
        assert get_res1.json()["cached"] is False

        # Query balance again (Cache Hit)
        get_res2 = client.get("/api/v1/accounts/ACC-ALICE-1/balance")
        assert get_res2.status_code == 200
        assert get_res2.json()["cached"] is True

    def test_create_duplicate_account_returns_409(self, client: TestClient) -> None:
        payload = {
            "account_id": "ACC-DUP-1",
            "owner_name": "Duplicate User",
            "initial_balance": "10.00",
            "currency": "USD",
        }
        res1 = client.post("/api/v1/accounts", json=payload)
        assert res1.status_code == 201

        res2 = client.post("/api/v1/accounts", json=payload)
        assert res2.status_code == 409
        assert "already exists" in res2.json()["detail"]

    def test_query_unknown_account_returns_404(self, client: TestClient) -> None:
        res = client.get("/api/v1/accounts/NONEXISTENT-999/balance")
        assert res.status_code == 404
        assert res.json()["error_type"] == "AccountNotFound"


class TestTransfersEndpoint:
    """Verifies atomic transfers, idempotency guarantees, and error handling."""

    def test_transfer_missing_idempotency_key_returns_400(self, client: TestClient) -> None:
        client.post(
            "/api/v1/accounts",
            json={"account_id": "ACC-A", "owner_name": "Alice", "initial_balance": "500.00"},
        )
        client.post(
            "/api/v1/accounts",
            json={"account_id": "ACC-B", "owner_name": "Bob", "initial_balance": "50.00"},
        )

        res = client.post(
            "/api/v1/transfers",
            json={
                "from_account_id": "ACC-A",
                "to_account_id": "ACC-B",
                "amount": "100.00",
            },
        )
        assert res.status_code == 400
        assert res.json()["error_type"] == "MissingIdempotencyKey"

    def test_transfer_blank_idempotency_key_returns_400(self, client: TestClient) -> None:
        res = client.post(
            "/api/v1/transfers",
            json={
                "from_account_id": "ACC-A",
                "to_account_id": "ACC-B",
                "amount": "100.00",
            },
            headers={"Idempotency-Key": "   "},
        )
        assert res.status_code == 400
        assert res.json()["error_type"] == "MissingIdempotencyKey"

    def test_transfer_oversized_idempotency_key_returns_400(self, client: TestClient) -> None:
        res = client.post(
            "/api/v1/transfers",
            json={
                "from_account_id": "ACC-A",
                "to_account_id": "ACC-B",
                "amount": "100.00",
            },
            headers={"Idempotency-Key": "x" * 129},
        )
        assert res.status_code == 400
        assert res.json()["error_type"] == "InvalidIdempotencyKey"

    def test_transfer_success(self, client: TestClient) -> None:
        # Provision Alice ($500) and Bob ($50)
        client.post(
            "/api/v1/accounts",
            json={"account_id": "ACC-A", "owner_name": "Alice", "initial_balance": "500.00"},
        )
        client.post(
            "/api/v1/accounts",
            json={"account_id": "ACC-B", "owner_name": "Bob", "initial_balance": "50.00"},
        )

        headers = {"Idempotency-Key": "transfer-success-key-001"}
        transfer_payload = {
            "from_account_id": "ACC-A",
            "to_account_id": "ACC-B",
            "amount": "100.00",
            "currency": "USD",
            "fee_strategy_type": "P2P",
        }
        res = client.post("/api/v1/transfers", json=transfer_payload, headers=headers)
        assert res.status_code == 200
        data = res.json()
        assert data["from_account_id"] == "ACC-A"
        assert data["to_account_id"] == "ACC-B"
        assert data["amount"] == "100.00"
        assert data["from_balance_after"] == "400.00"
        assert data["to_balance_after"] == "150.00"
        assert data["status"] == "SETTLED"
        assert len(data["ledger_entry_ids"]) == 2

    def test_transfer_idempotency_prevents_double_charge(self, client: TestClient) -> None:
        client.post(
            "/api/v1/accounts",
            json={"account_id": "ACC-A", "owner_name": "Alice", "initial_balance": "500.00"},
        )
        client.post(
            "/api/v1/accounts",
            json={"account_id": "ACC-B", "owner_name": "Bob", "initial_balance": "50.00"},
        )

        headers = {"Idempotency-Key": "mobile-req-abc-999"}
        transfer_payload = {
            "from_account_id": "ACC-A",
            "to_account_id": "ACC-B",
            "amount": "100.00",
            "currency": "USD",
        }

        # First request: Settles and debits Alice
        res1 = client.post("/api/v1/transfers", json=transfer_payload, headers=headers)
        assert res1.status_code == 200
        data1 = res1.json()
        tx_id1 = data1["transaction_id"]
        assert data1["from_balance_after"] == "400.00"

        # Duplicate retry with same key: Returns cached receipt, ZERO secondary debit
        res2 = client.post("/api/v1/transfers", json=transfer_payload, headers=headers)
        assert res2.status_code == 200
        data2 = res2.json()
        assert data2["transaction_id"] == tx_id1
        assert data2["from_balance_after"] == "400.00"

        # Verify Alice's balance in storage is still exactly $400.00
        bal = client.get("/api/v1/accounts/ACC-A/balance").json()
        assert bal["balance"] == "400.00"

    def test_insufficient_funds_returns_422(self, client: TestClient) -> None:
        client.post(
            "/api/v1/accounts",
            json={"account_id": "ACC-A", "owner_name": "Alice", "initial_balance": "50.00"},
        )
        client.post(
            "/api/v1/accounts",
            json={"account_id": "ACC-B", "owner_name": "Bob", "initial_balance": "50.00"},
        )

        res = client.post(
            "/api/v1/transfers",
            json={
                "from_account_id": "ACC-A",
                "to_account_id": "ACC-B",
                "amount": "100.00",
            },
            headers={"Idempotency-Key": "insufficient-test-key"},
        )
        assert res.status_code == 422
        assert res.json()["error_type"] == "InsufficientFunds"

    def test_self_transfer_returns_422(self, client: TestClient) -> None:
        res = client.post(
            "/api/v1/transfers",
            json={
                "from_account_id": "ACC-A",
                "to_account_id": "ACC-A",
                "amount": "10.00",
            },
            headers={"Idempotency-Key": "self-transfer-test-key"},
        )
        assert res.status_code == 422
        assert res.json()["error_type"] == "SelfTransferNotAllowed"

    def test_circuit_breaker_open_returns_503_service_unavailable(
        self, client: TestClient
    ) -> None:
        container = Container.get_instance()
        # Force breaker to OPEN
        container.circuit_breaker._state = CircuitState.OPEN
        container.circuit_breaker._tripped_at = 9999999999.0

        res = client.post(
            "/api/v1/transfers",
            json={
                "from_account_id": "ACC-A",
                "to_account_id": "ACC-B",
                "amount": "10.00",
            },
        )
        assert res.status_code == 503
        assert "Retry-After" in res.headers
        assert res.json()["error_type"] == "CircuitBreakerOpen"

    def test_transfer_persists_to_postgres_authoritatively(self, client: TestClient) -> None:
        client.post(
            "/api/v1/accounts",
            json={"account_id": "ACC-PG-A", "owner_name": "Alice", "initial_balance": "300.00"},
        )
        client.post(
            "/api/v1/accounts",
            json={"account_id": "ACC-PG-B", "owner_name": "Bob", "initial_balance": "50.00"},
        )

        headers = {"Idempotency-Key": "pg-auth-transfer-001"}
        transfer_payload = {
            "from_account_id": "ACC-PG-A",
            "to_account_id": "ACC-PG-B",
            "amount": "100.00",
            "currency": "USD",
        }
        res = client.post("/api/v1/transfers", json=transfer_payload, headers=headers)
        assert res.status_code == 200
        tx_id = res.json()["transaction_id"]

        # Verify directly in PostgreSQL database that mutations are authoritative
        async def _verify_db() -> None:
            engine = create_async_db_engine()
            try:
                async with engine.connect() as conn:
                    # 1. Accounts table updated
                    res_a = await conn.execute(
                        text("SELECT balance FROM accounts WHERE id = 'ACC-PG-A'")
                    )
                    assert res_a.scalar() == Decimal("200.0000")

                    res_b = await conn.execute(
                        text("SELECT balance FROM accounts WHERE id = 'ACC-PG-B'")
                    )
                    assert res_b.scalar() == Decimal("150.0000")

                    # 2. Transaction recorded in transactions table
                    res_tx = await conn.execute(
                        text("SELECT status, amount FROM transactions WHERE id = :tx_id"),
                        {"tx_id": tx_id},
                    )
                    row = res_tx.mappings().first()
                    assert row is not None
                    assert row["status"] == "SETTLED"
                    assert row["amount"] == Decimal("100.0000")

                    # 3. Journal entries recorded in ledger_entries table
                    res_entries = await conn.execute(
                        text("SELECT count(*) FROM ledger_entries WHERE transaction_id = :tx_id"),
                        {"tx_id": tx_id},
                    )
                    assert res_entries.scalar() == 2

                    # 4. Idempotency record recorded in idempotency_records table
                    res_idemp = await conn.execute(
                        text(
                            "SELECT status, transaction_id FROM idempotency_records "
                            "WHERE key = 'pg-auth-transfer-001'"
                        )
                    )
                    idemp_row = res_idemp.mappings().first()
                    assert idemp_row is not None
                    assert idemp_row["status"] == "SETTLED"
                    assert str(idemp_row["transaction_id"]) == tx_id
            finally:
                await engine.dispose()

        asyncio.run(_verify_db())

    def test_transfer_idempotency_payload_mismatch_returns_409(
        self, client: TestClient
    ) -> None:
        client.post(
            "/api/v1/accounts",
            json={"account_id": "ACC-PG-A", "owner_name": "Alice", "initial_balance": "300.00"},
        )
        client.post(
            "/api/v1/accounts",
            json={"account_id": "ACC-PG-B", "owner_name": "Bob", "initial_balance": "50.00"},
        )

        headers = {"Idempotency-Key": "mismatch-key-999"}
        payload1 = {
            "from_account_id": "ACC-PG-A",
            "to_account_id": "ACC-PG-B",
            "amount": "100.00",
            "currency": "USD",
        }
        res1 = client.post("/api/v1/transfers", json=payload1, headers=headers)
        assert res1.status_code == 200

        # Attempt to replay with altered amount
        payload2 = {
            "from_account_id": "ACC-PG-A",
            "to_account_id": "ACC-PG-B",
            "amount": "200.00",
            "currency": "USD",
        }
        res2 = client.post("/api/v1/transfers", json=payload2, headers=headers)
        assert res2.status_code == 409
        assert res2.json()["error_type"] == "IdempotencyPayloadMismatch"


class TestAuditEndpoint:
    """Verifies mathematical ledger reconciliation via API."""

    def test_audit_reconciliation_healthy(self, client: TestClient) -> None:
        # Provision accounts and perform a transfer
        client.post(
            "/api/v1/accounts",
            json={"account_id": "ACC-1", "owner_name": "Alice", "initial_balance": "500.00"},
        )
        client.post(
            "/api/v1/accounts",
            json={"account_id": "ACC-2", "owner_name": "Bob", "initial_balance": "100.00"},
        )
        client.post(
            "/api/v1/transfers",
            json={"from_account_id": "ACC-1", "to_account_id": "ACC-2", "amount": "50.00"},
            headers={"Idempotency-Key": "audit-transfer-key-01"},
        )

        res = client.post("/api/v1/audit/reconcile")
        assert res.status_code == 200
        data = res.json()
        assert data["is_balanced"] is True
        assert data["is_system_net_zero"] is True
        assert Decimal(data["total_system_net"]) == Decimal("0.00")
        assert len(data["discrepancies"]) == 0
