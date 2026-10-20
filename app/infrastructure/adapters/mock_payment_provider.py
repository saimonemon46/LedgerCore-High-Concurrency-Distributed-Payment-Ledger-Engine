"""Mock External Payment Provider for LedgerCore.

Simulates provider network behaviors:
- Happy path settlements
- Ambiguous network timeouts (inducing PENDING_RECONCILIATION)
- Provider status check reconciliation via idempotency keys
"""

import logging
import uuid
from typing import Any

from app.ports.payment_provider_port import (
    IPaymentProviderPort,
    ProviderPaymentCommand,
    ProviderPaymentResult,
    ProviderStatus,
)

logger = logging.getLogger("ledger_core.provider")


class MockPaymentProvider(IPaymentProviderPort):
    """Configurable mock provider for testing ambiguous timeout recovery and reconciliation."""

    def __init__(self, simulate_timeout_on_keys: set[str] | None = None) -> None:
        self.simulate_timeout_on_keys = simulate_timeout_on_keys or set()
        self._provider_records: dict[str, dict[str, Any]] = {}

    async def execute_payout(self, command: ProviderPaymentCommand) -> ProviderPaymentResult:
        key = command.idempotency_key

        # Check if already processed at provider
        if key in self._provider_records:
            rec = self._provider_records[key]
            return ProviderPaymentResult(
                status=rec["status"],
                idempotency_key=key,
                provider_tx_id=rec["provider_tx_id"],
                raw_response=rec["response"],
            )

        # Simulate network timeout / drop
        if key in self.simulate_timeout_on_keys:
            # The provider actually processed the payment, but the client socket timed out!
            provider_tx_id = f"prov_tx_{uuid.uuid4().hex[:12]}"
            self._provider_records[key] = {
                "status": ProviderStatus.SUCCEEDED,
                "provider_tx_id": provider_tx_id,
                "response": {"gateway": "mock_bank", "status": "captured"},
            }
            logger.warning(
                "Simulating provider network timeout for key %s. Operation outcome ambiguous.",
                key,
            )
            return ProviderPaymentResult(
                status=ProviderStatus.PENDING_RECONCILIATION,
                idempotency_key=key,
                error_message="Network read timeout while awaiting provider ACK.",
            )

        # Normal successful execution
        provider_tx_id = f"prov_tx_{uuid.uuid4().hex[:12]}"
        self._provider_records[key] = {
            "status": ProviderStatus.SUCCEEDED,
            "provider_tx_id": provider_tx_id,
            "response": {"gateway": "mock_bank", "status": "captured"},
        }

        return ProviderPaymentResult(
            status=ProviderStatus.SUCCEEDED,
            idempotency_key=key,
            provider_tx_id=provider_tx_id,
            raw_response={"gateway": "mock_bank", "status": "captured"},
        )

    async def check_status(
        self,
        idempotency_key: str,
        provider_tx_id: str | None = None,
    ) -> ProviderPaymentResult:
        if idempotency_key in self._provider_records:
            rec = self._provider_records[idempotency_key]
            return ProviderPaymentResult(
                status=rec["status"],
                idempotency_key=idempotency_key,
                provider_tx_id=rec["provider_tx_id"],
                raw_response=rec["response"],
            )

        return ProviderPaymentResult(
            status=ProviderStatus.FAILED,
            idempotency_key=idempotency_key,
            error_message="Transaction not found on provider ledger.",
        )
