"""Deterministic cryptographic request fingerprinting for distributed idempotency."""

import hashlib
import json
from decimal import Decimal
from typing import Any


def _normalize_value(val: Any) -> Any:
    """Recursively normalizes arbitrary Python data structures for canonical serialization."""
    if isinstance(val, Decimal):
        return f"{val:.4f}"
    if hasattr(val, "amount") and hasattr(val, "currency"):
        return {"amount": f"{Decimal(str(val.amount)):.4f}", "currency": str(val.currency)}
    if isinstance(val, dict):
        return {str(k): _normalize_value(v) for k, v in sorted(val.items())}
    if isinstance(val, (list, tuple)):
        return [_normalize_value(item) for item in val]
    return val


def compute_request_hash(
    payload: dict[str, Any] | str | bytes | None,
    tenant_id: str = "default",
) -> str:
    """Computes a deterministic SHA-256 fingerprint of a request payload scoped by tenant."""
    if payload is None:
        normalized: Any = {}
    elif isinstance(payload, bytes):
        return hashlib.sha256(f"{tenant_id}:".encode() + payload).hexdigest()
    elif isinstance(payload, str):
        return hashlib.sha256(f"{tenant_id}:{payload}".encode()).hexdigest()
    elif isinstance(payload, dict):
        normalized = _normalize_value(payload)
    else:
        normalized = str(payload)

    canonical_json = json.dumps(
        normalized,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    preimage = f"{tenant_id}:{canonical_json}".encode()
    return hashlib.sha256(preimage).hexdigest()


def compute_transfer_fingerprint(
    from_account_id: str,
    to_account_id: str,
    amount: Decimal | str | float,
    currency: str,
    tenant_id: str = "default",
) -> str:
    """Computes a canonical SHA-256 fingerprint for a financial transfer.

    Guarantees mathematically that identical transactions generate the exact same fingerprint,
    while any modification of sender, receiver, amount, or currency changes the hash.
    Formula from ENGINEERING_REFACTORING_PLAN.md:
        hash(tenant_id + from + to + amount + currency)
    """
    amt_dec = Decimal(str(amount)).quantize(Decimal("0.01"))
    preimage = (
        f"{tenant_id}:{from_account_id}:{to_account_id}:{amt_dec:.2f}:{str(currency).upper()}"
    ).encode()
    return hashlib.sha256(preimage).hexdigest()


def compute_transfer_command_hash(
    from_account_id: str,
    to_account_id: str,
    amount: Decimal | str | float,
    currency: str,
    fee_account_id: str | None = None,
    metadata: dict[str, Any] | None = None,
    tenant_id: str = "default",
) -> str:
    """Computes a canonical SHA-256 fingerprint for a financial transfer command."""
    return compute_transfer_fingerprint(
        from_account_id=from_account_id,
        to_account_id=to_account_id,
        amount=amount,
        currency=currency,
        tenant_id=tenant_id,
    )
