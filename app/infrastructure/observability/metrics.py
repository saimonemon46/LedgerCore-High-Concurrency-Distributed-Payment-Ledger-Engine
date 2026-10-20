"""Observability & Prometheus-compatible Metrics for LedgerCore.

Tracks outbox queue lag, transfer counts, consumer deduplication stats, and DLQ volume.
"""

import threading
from dataclasses import dataclass, field


@dataclass
class MetricCounters:
    """Thread-safe metric counters."""

    transfers_settled_total: int = 0
    transfers_failed_total: int = 0
    outbox_events_saved_total: int = 0
    outbox_events_published_total: int = 0
    consumer_processed_total: int = 0
    consumer_duplicates_skipped_total: int = 0
    consumer_dlq_routed_total: int = 0
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def inc_transfers_settled(self) -> None:
        with self._lock:
            self.transfers_settled_total += 1

    def inc_transfers_failed(self) -> None:
        with self._lock:
            self.transfers_failed_total += 1

    def inc_outbox_saved(self) -> None:
        with self._lock:
            self.outbox_events_saved_total += 1

    def inc_outbox_published(self, count: int = 1) -> None:
        with self._lock:
            self.outbox_events_published_total += count

    def inc_consumer_processed(self) -> None:
        with self._lock:
            self.consumer_processed_total += 1

    def inc_consumer_duplicates(self) -> None:
        with self._lock:
            self.consumer_duplicates_skipped_total += 1

    def inc_consumer_dlq(self) -> None:
        with self._lock:
            self.consumer_dlq_routed_total += 1

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


metrics = MetricCounters()
