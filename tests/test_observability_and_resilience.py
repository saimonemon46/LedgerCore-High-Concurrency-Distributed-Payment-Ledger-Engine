"""Unit and API tests for Prometheus metrics, telemetry summary, chaos breaker, and rate limiter."""

import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import Container
from app.api.main import create_app
from app.infrastructure.observability.metrics import metrics
from app.infrastructure.resilience.rate_limiter import RedisRateLimiter


@pytest.fixture
def client() -> TestClient:
    Container.reset()
    app = create_app()
    with TestClient(app) as test_client:
        yield test_client


def test_prometheus_metrics_endpoint_exposes_real_metrics(client: TestClient) -> None:
    metrics.inc_transfers_settled()
    resp = client.get("/metrics")
    assert resp.status_code == 200
    assert "text/plain" in resp.headers["content-type"]
    body = resp.text
    assert "ledger_transfers_settled_total" in body
    assert "ledger_http_requests_total" in body
    assert "ledger_http_request_duration_seconds" in body
    assert "ledger_circuit_breaker_state" in body


def test_telemetry_summary_and_circuit_breaker_chaos(client: TestClient) -> None:
    summary = client.get("/api/v1/metrics/summary")
    assert summary.status_code == 200
    data = summary.json()
    assert data["circuit_breaker_state"] == "CLOSED"
    assert "rps" in data
    assert "p95_latency_ms" in data

    trip = client.post("/api/v1/chaos/circuit-breaker", json={"action": "trip"})
    assert trip.status_code == 200
    assert trip.json()["circuit_breaker_state"] == "OPEN"

    reset = client.post("/api/v1/chaos/circuit-breaker", json={"action": "reset"})
    assert reset.status_code == 200
    assert reset.json()["circuit_breaker_state"] == "CLOSED"


@pytest.mark.asyncio
async def test_rate_limiter_enforces_429_threshold() -> None:
    limiter = RedisRateLimiter(redis_url="redis://127.0.0.1:59999/0", requests_per_minute=3)
    try:
        r1 = await limiter.check("10.0.0.1", scope="transfers")
        r2 = await limiter.check("10.0.0.1", scope="transfers")
        r3 = await limiter.check("10.0.0.1", scope="transfers")
        r4 = await limiter.check("10.0.0.1", scope="transfers")
        assert r1.allowed is True
        assert r2.allowed is True
        assert r3.allowed is True
        assert r4.allowed is False
        assert r4.remaining == 0
    finally:
        await limiter.close()
