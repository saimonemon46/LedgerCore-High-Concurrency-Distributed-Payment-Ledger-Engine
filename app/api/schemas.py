"""Pydantic v2 request and response schemas for LedgerCore REST API."""

import time
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class CreateAccountRequest(BaseModel):
    """Payload for provisioning a new ledger account."""

    model_config = ConfigDict(str_strip_whitespace=True)

    account_id: str = Field(..., min_length=1, max_length=64, description="Unique account ID")
    owner_name: str = Field(..., min_length=1, max_length=128, description="Legal owner name")
    initial_balance: Decimal = Field(
        default=Decimal("0.00"),
        ge=Decimal("0.00"),
        description="Opening balance",
    )
    currency: str = Field(
        default="USD", min_length=3, max_length=3, description="ISO currency code"
    )

    @field_validator("initial_balance")
    @classmethod
    def validate_scale(cls, val: Decimal) -> Decimal:
        exponent = val.as_tuple().exponent
        if isinstance(exponent, int) and exponent < -2:
            raise ValueError("Balance cannot exceed 2 decimal places.")
        return val


class AccountResponse(BaseModel):
    """Response payload for account details and balance."""

    account_id: str
    owner_name: str
    balance: str
    currency: str
    status: str
    is_active: bool
    cached: bool = False


class TransferRequest(BaseModel):
    """Payload for initiating a financial transfer."""

    model_config = ConfigDict(str_strip_whitespace=True)

    from_account_id: str = Field(..., min_length=1, max_length=64)
    to_account_id: str = Field(..., min_length=1, max_length=64)
    amount: Decimal = Field(..., gt=Decimal("0.00"), description="Transfer amount")
    currency: str = Field(default="USD", min_length=3, max_length=3)
    fee_strategy_type: str = Field(
        default="P2P",
        description="Fee strategy: 'P2P', 'FLAT', or 'MERCHANT'",
    )
    flat_fee: Decimal = Field(default=Decimal("0.00"), ge=Decimal("0.00"))
    fee_rate: Decimal = Field(default=Decimal("0.00"), ge=Decimal("0.00"))
    fee_account_id: str | None = Field(default=None)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("amount")
    @classmethod
    def validate_amount_scale(cls, val: Decimal) -> Decimal:
        exponent = val.as_tuple().exponent
        if isinstance(exponent, int) and exponent < -2:
            raise ValueError("Transfer amount precision cannot exceed 2 decimal places.")
        return val


class TransferResponse(BaseModel):
    """Response payload for settled transactions."""

    transaction_id: str
    from_account_id: str
    to_account_id: str
    amount: str
    currency: str
    fee: str
    from_balance_after: str
    to_balance_after: str
    status: str
    created_at: float
    ledger_entry_ids: list[str]
    metadata: dict[str, Any] = Field(default_factory=dict)


class LedgerEntryResponse(BaseModel):
    """Schema for individual ledger journal entries."""

    id: str
    transaction_id: str
    account_id: str
    amount: str
    currency: str
    balance_after: str
    entry_type: str
    sequence_id: int
    created_at: str


class TransactionDetailResponse(BaseModel):
    """Schema for detailed transaction queries."""

    id: str
    tenant_id: str
    idempotency_key: str | None = None
    source_account_id: str
    destination_account_id: str
    amount: str
    fee: str
    currency: str
    status: str
    created_at: str
    postings: list[LedgerEntryResponse] = Field(default_factory=list)


class AccountDiscrepancySchema(BaseModel):
    """Schema for individual account discrepancies found during reconciliation."""

    account_id: str
    actual_balance: str
    expected_balance: str
    discrepancy: str


class AuditReconciliationResponse(BaseModel):
    """Response payload for system-wide mathematical reconciliation."""

    total_account_balances: str
    total_ledger_credits: str
    total_ledger_debits: str
    total_system_net: str
    is_system_net_zero: bool
    is_balanced: bool
    accounts_audited_count: int
    ledger_entries_count: int
    discrepancies: list[AccountDiscrepancySchema] = Field(default_factory=list)
    timestamp: float


class HealthResponse(BaseModel):
    """Service health and circuit breaker status."""

    status: str = "healthy"
    circuit_breaker_state: str
    timestamp: float = Field(default_factory=time.time)
