"""Observability & Prometheus Metrics for LedgerCore.

Provides real `prometheus_client` Counters, Gauges, and Histograms exposed
at `/metrics`, while preserving thread-safe in-memory snapshot counters.
"""

import threading
import time
from collections import deque
from dataclasses import dataclass, field

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)

# Prometheus Metrics Registry
PROM_TRANSFERS_SETTLED = Counter(
    "ledger_transfers_settled_total",
    "Total number of double-entry transfers settled",
)
PROM_TRANSFERS_FAILED = Counter(
    "ledger_transfers_failed_total",
    "Total number of failed or rejected transfers",
)
PROM_OUTBOX_SAVED = Counter(
    "ledger_outbox_events_saved_total",
    "Total number of transactional outbox events saved",
)
PROM_OUTBOX_PUBLISHED = Counter(
    "ledger_outbox_events_published_total",
    "Total number of outbox events published to message broker",
)
PROM_CONSUMER_PROCESSED = Counter(
    "ledger_consumer_processed_total",
    "Total number of broker events processed by consumers",
)
PROM_CONSUMER_DUPLICATES = Counter(
    "ledger_consumer_duplicates_skipped_total",
    "Total number of duplicate consumer deliveries skipped",
)
PROM_CONSUMER_DLQ = Counter(
    "ledger_consumer_dlq_routed_total",
    "Total number of events routed to dead-letter queue",
)
PROM_RATE_LIMIT_REJECTIONS = Counter(
    "ledger_rate_limit_rejections_total",
    "Total number of requests rejected with HTTP 429 by rate limiter",
)
PROM_HTTP_REQUESTS = Counter(
    "ledger_http_requests_total",
    "Total HTTP requests handled by LedgerCore API",
    ["method", "path", "status"],
)
PROM_HTTP_DURATION = Histogram(
    "ledger_http_request_duration_seconds",
    "HTTP request latency in seconds",
    ["method", "path"],
    buckets=(0.002, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0),
)
PROM_CIRCUIT_BREAKER_STATE = Gauge(
    "ledger_circuit_breaker_state",
    "Circuit breaker state (0=CLOSED, 1=HALF_OPEN, 2=OPEN)",
)
PROM_OUTBOX_LAG = Gauge(
    "ledger_outbox_lag",
    "Current number of unpublished events in transactional outbox",
)

_CIRCUIT_STATE_MAP = {
    "CLOSED": 0.0,
    "HALF_OPEN": 1.0,
    "OPEN": 2.0,
}


@dataclass
class MetricCounters:
    """Thread-safe metric counters backed by Prometheus client collectors."""

    transfers_settled_total: int = 0
    transfers_failed_total: int = 0
    outbox_events_saved_total: int = 0
    outbox_events_published_total: int = 0
    consumer_processed_total: int = 0
    consumer_duplicates_skipped_total: int = 0
    consumer_dlq_routed_total: int = 0
    rate_limit_rejections_total: int = 0
    _lock: threading.Lock = field(default_factory=threading.Lock)
    _recent_latencies_ms: deque[float] = field(
        default_factory=lambda: deque(maxlen=500)
    )
    _recent_request_timestamps: deque[float] = field(
        default_factory=lambda: deque(maxlen=2000)
    )

    def inc_transfers_settled(self) -> None:
        with self._lock:
            self.transfers_settled_total += 1
        PROM_TRANSFERS_SETTLED.inc()

    def inc_transfers_failed(self) -> None:
        with self._lock:
            self.transfers_failed_total += 1
        PROM_TRANSFERS_FAILED.inc()

    def inc_outbox_saved(self) -> None:
        with self._lock:
            self.outbox_events_saved_total += 1
        PROM_OUTBOX_SAVED.inc()

    def inc_outbox_published(self, count: int = 1) -> None:
        with self._lock:
            self.outbox_events_published_total += count
        PROM_OUTBOX_PUBLISHED.inc(count)

    def inc_consumer_processed(self) -> None:
        with self._lock:
            self.consumer_processed_total += 1
        PROM_CONSUMER_PROCESSED.inc()

    def inc_consumer_duplicates(self) -> None:
        with self._lock:
            self.consumer_duplicates_skipped_total += 1
        PROM_CONSUMER_DUPLICATES.inc()

    def inc_consumer_dlq(self) -> None:
        with self._lock:
            self.consumer_dlq_routed_total += 1
        PROM_CONSUMER_DLQ.inc()

    def inc_rate_limit_rejection(self) -> None:
        with self._lock:
            self.rate_limit_rejections_total += 1
        PROM_RATE_LIMIT_REJECTIONS.inc()

    def set_circuit_breaker_state(self, state: str) -> None:
        PROM_CIRCUIT_BREAKER_STATE.set(_CIRCUIT_STATE_MAP.get(state.upper(), 0.0))

    def set_outbox_lag(self, lag: int) -> None:
        PROM_OUTBOX_LAG.set(max(0, lag))

    def record_http_request(
        self,
        method: str,
        path: str,
        status_code: int,
        duration_seconds: float,
    ) -> None:
        now = time.time()
        PROM_HTTP_REQUESTS.labels(
            method=method,
            path=path,
            status=str(status_code),
        ).inc()
        PROM_HTTP_DURATION.labels(method=method, path=path).observe(duration_seconds)
        with self._lock:
            self._recent_latencies_ms.append(duration_seconds * 1000.0)
            self._recent_request_timestamps.append(now)

    def get_live_telemetry(self) -> dict[str, float | int]:
        """Computes rolling RPS and P95 latency for the Operations Console."""
        now = time.time()
        cutoff = now - 10.0
        with self._lock:
            while self._recent_request_timestamps and self._recent_request_timestamps[0] < cutoff:
                self._recent_request_timestamps.popleft()
            rps = round(len(self._recent_request_timestamps) / 10.0, 2)
            latencies = sorted(self._recent_latencies_ms)
            p95_ms = 0.0
            if latencies:
                idx = min(len(latencies) - 1, int(0.95 * len(latencies)))
                p95_ms = round(latencies[idx], 2)
            outbox_lag = max(
                0,
                self.outbox_events_saved_total - self.outbox_events_published_total,
            )
            return {
                "rps": rps,
                "p95_latency_ms": p95_ms,
                "outbox_lag": outbox_lag,
                "transfers_settled_total": self.transfers_settled_total,
                "transfers_failed_total": self.transfers_failed_total,
                "rate_limit_rejections_total": self.rate_limit_rejections_total,
            }

    def snapshot(self) -> dict[str, int]:
        with self._lock:
            return {
                "transfers_settled_total": self.transfers_settled_total,
                "transfers_failed_total": self.transfers_failed_total,
                "outbox_events_saved_total": self.outbox_events_saved_total,
                "outbox_events_published_total": self.outbox_events_published_total,
                "consumer_processed_total": self.consumer_processed_total,
                "consumer_duplicates_skipped_total": self.consumer_duplicates_skipped_total,
                "consumer_dlq_routed_total": self.consumer_dlq_routed_total,
            }


def render_prometheus_metrics() -> tuple[bytes, str]:
    """Serializes Prometheus metrics in standard exposition format."""
    return generate_latest(), CONTENT_TYPE_LATEST


metrics = MetricCounters()
