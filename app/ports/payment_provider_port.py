"""Payment Provider Port for LedgerCore.

Defines the contract for external money movement, explicit provider states,
and recovery mechanisms for ambiguous network timeouts.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from app.domain.value_objects import Money


class ProviderStatus(StrEnum):
    """Explicit lifecycle states for external payment operations."""

    SUBMITTED = "SUBMITTED"
    PENDING_RECONCILIATION = "PENDING_RECONCILIATION"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"


@dataclass(frozen=True)
class ProviderPaymentCommand:
    """Command requesting an external payout or transfer."""

    idempotency_key: str
    transfer_id: str
    amount: Money
    recipient_identifier: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ProviderPaymentResult:
    """Result returned by external provider operations."""

    status: ProviderStatus
    idempotency_key: str
    provider_tx_id: str | None = None
    raw_response: dict[str, Any] = field(default_factory=dict)
    error_message: str | None = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))


class IPaymentProviderPort(ABC):
    """Port for interacting with external financial institutions and card/ACH rails."""

    @abstractmethod
    async def execute_payout(self, command: ProviderPaymentCommand) -> ProviderPaymentResult:
        """Submits a payout with provider-level idempotency protection.

        On ambiguous network timeout, must return PENDING_RECONCILIATION without blindly retrying.
        """
        pass

    @abstractmethod
    async def check_status(
        self,
        idempotency_key: str,
        provider_tx_id: str | None = None,
    ) -> ProviderPaymentResult:
        """Queries the external provider to reconcile the outcome of an ambiguous transaction."""
        pass
