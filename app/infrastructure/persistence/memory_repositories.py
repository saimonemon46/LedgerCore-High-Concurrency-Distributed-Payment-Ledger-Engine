"""Thread-safe in-memory repository implementations for LedgerCore.

NOTE: These in-memory adapters store state in process-local dictionaries and are
retained strictly for isolated unit testing, mocking, and local micro-benchmarking.
They are NOT intended as proof of distributed correctness or durability across
multiple processes or machines. Real multi-process and multi-node persistence is
provided by the PostgreSQL persistence layer.
"""

import threading
import time
from copy import copy
from decimal import Decimal
from typing import Any

from app.domain.models import Account, LedgerEntry
from app.domain.value_objects import Money
from app.ports.idempotency_port import IIdempotencyStore
from app.ports.repository_ports import IAccountRepository, ILedgerRepository


class InMemoryAccountRepository(IAccountRepository):
    """Thread-safe in-memory adapter implementing IAccountRepository."""

    def __init__(self) -> None:
        self._accounts: dict[str, Account] = {}
        self._lock: threading.RLock = threading.RLock()

    def get_by_id(self, account_id: str) -> Account | None:
        with self._lock:
            acc = self._accounts.get(account_id)
            return copy(acc) if acc is not None else None

    def save(self, account: Account) -> None:
        with self._lock:
            self._accounts[account.account_id] = copy(account)

    def get_all(self) -> list[Account]:
        with self._lock:
            return [copy(acc) for acc in self._accounts.values()]

    def update_balance(self, account_id: str, new_balance: Money) -> None:
        with self._lock:
            acc = self._accounts.get(account_id)
            if acc is None:
                raise KeyError(f"Account '{account_id}' not found.")
            acc.balance = new_balance

    def clear(self) -> None:
        """Utility method for test resets."""
        with self._lock:
            self._accounts.clear()


class InMemoryLedgerRepository(ILedgerRepository):
    """Thread-safe in-memory adapter implementing ILedgerRepository."""

    def __init__(self) -> None:
        self._entries: list[LedgerEntry] = []
        self._lock: threading.RLock = threading.RLock()

    def append_entry(self, entry: LedgerEntry) -> None:
        with self._lock:
            self._entries.append(entry)

    def append_entries(self, entries: list[LedgerEntry]) -> None:
        with self._lock:
            self._entries.extend(entries)

    def get_entries_for_account(self, account_id: str) -> list[LedgerEntry]:
        with self._lock:
            return [e for e in self._entries if e.account_id == account_id]

    def get_all_entries(self) -> list[LedgerEntry]:
        with self._lock:
            return list(self._entries)

    def get_total_system_net(self) -> Decimal:
        with self._lock:
            return sum((e.amount for e in self._entries), start=Decimal("0.00"))

    def clear(self) -> None:
        """Utility method for test resets."""
        with self._lock:
            self._entries.clear()


class InMemoryIdempotencyStore(IIdempotencyStore):
    """Thread-safe in-memory adapter implementing IIdempotencyStore with TTL."""

    def __init__(self) -> None:
        # Maps key -> (expires_at, is_completed, result)
        self._store: dict[str, tuple[float, bool, dict[str, Any] | None]] = {}
        self._lock: threading.RLock = threading.RLock()

    def try_acquire(self, key: str, ttl_seconds: float | int = 120) -> bool:
        with self._lock:
            now = time.time()
            if key in self._store:
                expires_at, is_completed, _ = self._store[key]
                if now < expires_at:
                    # Key is in-flight or already completed
                    return False

            # Acquire new in-flight lock
            expires_at = now + ttl_seconds
            self._store[key] = (expires_at, False, None)
            return True

    def get_result(self, key: str) -> dict[str, Any] | None:
        with self._lock:
            now = time.time()
            entry = self._store.get(key)
            if entry is None:
                return None

            expires_at, is_completed, result = entry
            if now >= expires_at:
                del self._store[key]
                return None

            return result if is_completed else None

    def store_result(
        self,
        key: str,
        result: dict[str, Any],
        ttl_seconds: float | int = 86400,
    ) -> None:
        with self._lock:
            now = time.time()
            expires_at = now + ttl_seconds
            self._store[key] = (expires_at, True, result)

    def release(self, key: str) -> None:
        with self._lock:
            if key in self._store:
                _, is_completed, _ = self._store[key]
                if not is_completed:
                    del self._store[key]

    def clear(self) -> None:
        """Utility method for test resets."""
        with self._lock:
            self._store.clear()
