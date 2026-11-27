"""Health check, readiness, telemetry summary, and chaos simulation routes."""

import time
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.api.dependencies import get_circuit_breaker
from app.api.schemas import HealthResponse
from app.infrastructure.observability.metrics import metrics
from app.infrastructure.resilience.circuit_breaker import CircuitBreaker

router = APIRouter(tags=["Health"])


class TelemetrySummaryResponse(BaseModel):
    """Live telemetry snapshot for the Operations Command Center."""

    status: str
    circuit_breaker_state: str
    rps: float
    p95_latency_ms: float
    outbox_lag: int
    transfers_settled_total: int
    transfers_failed_total: int
    rate_limit_rejections_total: int
    timestamp: float


class CircuitBreakerChaosRequest(BaseModel):
    """Chaos control payload to trip or reset the API circuit breaker."""

    action: Literal["trip", "reset"]


@router.get("/health", response_model=HealthResponse, summary="Liveness and health check")
def health_check(
    circuit_breaker: CircuitBreaker = Depends(get_circuit_breaker),
) -> HealthResponse:
    """Returns engine health and circuit breaker state."""
    state = circuit_breaker.get_state().value
    metrics.set_circuit_breaker_state(state)
    return HealthResponse(
        status="healthy" if state != "OPEN" else "degraded",
        circuit_breaker_state=state,
        timestamp=time.time(),
    )


@router.get(
    "/metrics/summary",
    response_model=TelemetrySummaryResponse,
    summary="Live operational telemetry summary for Command Center UI",
)
def telemetry_summary(
    circuit_breaker: CircuitBreaker = Depends(get_circuit_breaker),
) -> TelemetrySummaryResponse:
    """Returns rolling RPS, P95 latency, outbox lag, and circuit breaker state."""
    state = circuit_breaker.get_state().value
    metrics.set_circuit_breaker_state(state)
    live = metrics.get_live_telemetry()
    return TelemetrySummaryResponse(
        status="healthy" if state != "OPEN" else "degraded",
        circuit_breaker_state=state,
        rps=float(live["rps"]),
        p95_latency_ms=float(live["p95_latency_ms"]),
        outbox_lag=int(live["outbox_lag"]),
        transfers_settled_total=int(live["transfers_settled_total"]),
        transfers_failed_total=int(live["transfers_failed_total"]),
        rate_limit_rejections_total=int(live["rate_limit_rejections_total"]),
        timestamp=time.time(),
    )


@router.post(
    "/chaos/circuit-breaker",
    response_model=HealthResponse,
    summary="Simulate circuit breaker trip or reset for chaos testing",
)
def simulate_circuit_breaker(
    payload: CircuitBreakerChaosRequest,
    circuit_breaker: CircuitBreaker = Depends(get_circuit_breaker),
) -> HealthResponse:
    """Trips the circuit breaker OPEN via simulated failures or resets it CLOSED."""
    if payload.action == "trip":
        for _ in range(max(circuit_breaker.min_requests, 6)):
            circuit_breaker.record_failure()
    else:
        for _ in range(circuit_breaker.half_open_success_threshold + 2):
            circuit_breaker.record_success()
        with circuit_breaker._lock:
            circuit_breaker._window.clear()
            from app.infrastructure.resilience.circuit_breaker import CircuitState

            circuit_breaker._state = CircuitState.CLOSED
    state = circuit_breaker.get_state().value
    metrics.set_circuit_breaker_state(state)
    return HealthResponse(
        status="healthy" if state != "OPEN" else "degraded",
        circuit_breaker_state=state,
        timestamp=time.time(),
    )
