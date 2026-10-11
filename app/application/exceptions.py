"""Application layer exceptions for LedgerCore.

Defines application-specific orchestration errors, idempotency conflicts,
and reconciliation divergence errors adhering to Clean Architecture.
"""

from decimal import Decimal
from typing import Any


class ApplicationError(Exception):
    """Base exception for all application layer orchestration errors."""
    pass


class AccountNotFoundError(ApplicationError):
    """Raised when an operation references a non-existent account."""

    def __init__(self, account_id: str) -> None:
        self.account_id = account_id
        super().__init__(f"Account with ID '{account_id}' was not found.")


class SelfTransferNotAllowedError(ApplicationError):
    """Raised when the sender and receiver accounts are identical."""

    def __init__(self, account_id: str) -> None:
        self.account_id = account_id
        super().__init__(f"Self-transfer not allowed: sender and receiver are both '{account_id}'.")


class IdempotencyConflictError(ApplicationError):
    """Raised when a concurrent request with the same idempotency key is already in-flight."""

    def __init__(self, key: str) -> None:
        self.key = key
        super().__init__(
            f"An identical request with idempotency key '{key}' is currently in-flight."
        )


class IdempotencyPayloadMismatchError(ApplicationError):
    """Raised when an idempotency key was previously used with a different request payload."""

    def __init__(self, key: str) -> None:
        self.key = key
        super().__init__(
            "Idempotency key was previously used with a different request payload."
        )


class IdempotencyInFlightError(IdempotencyConflictError):
    """Raised when an identical request with the same idempotency key is actively processing."""

    def __init__(self, key: str, retry_after_seconds: int = 1) -> None:
        self.retry_after_seconds = retry_after_seconds
        super().__init__(key)


class ReconciliationDivergenceError(ApplicationError):
    """Raised when mathematical audit reconciliation detects an invariant divergence."""

    def __init__(
        self,
        divergence: Decimal,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.divergence = divergence
        self.details = details or {}
        super().__init__(
            f"Audit reconciliation failed: Non-zero system divergence of {divergence} detected."
        )
