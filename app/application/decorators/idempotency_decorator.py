"""Idempotency Decorator and Wrapper ensuring once-and-only-once execution."""

from collections.abc import Callable
from functools import wraps
from typing import Any, TypeVar

from app.application.exceptions import (
    IdempotencyInFlightError,
    IdempotencyPayloadMismatchError,
)
from app.application.fingerprint import (
    compute_request_hash,
    compute_transfer_fingerprint,
)
from app.application.use_cases.execute_transfer import TransferResult
from app.ports.idempotency_port import IIdempotencyStore

T = TypeVar("T")


def _extract_idempotency_key(args: tuple[Any, ...], kwargs: dict[str, Any]) -> str | None:
    """Extracts idempotency key from arguments or TransferCommand."""
    if "idempotency_key" in kwargs and kwargs["idempotency_key"]:
        return str(kwargs["idempotency_key"])

    if "key" in kwargs and kwargs["key"]:
        return str(kwargs["key"])

    for arg in args:
        if hasattr(arg, "idempotency_key") and arg.idempotency_key:
            return str(arg.idempotency_key)
        if isinstance(arg, dict) and "idempotency_key" in arg:
            return str(arg["idempotency_key"])

    return None


def _extract_payload_dict(args: tuple[Any, ...], kwargs: dict[str, Any]) -> dict[str, Any]:
    """Extracts business request attributes for canonical cryptographic fingerprinting."""
    payload: dict[str, Any] = {}
    for k, v in kwargs.items():
        if k not in ("idempotency_key", "key"):
            payload[k] = v
    for arg in args:
        if hasattr(arg, "__dict__"):
            d = dict(arg.__dict__)
            d.pop("idempotency_key", None)
            payload.update(d)
        elif isinstance(arg, dict):
            d = dict(arg)
            d.pop("idempotency_key", None)
            payload.update(d)
    return payload


def _extract_payload_hash(args: tuple[Any, ...], kwargs: dict[str, Any]) -> str:
    """Extracts and computes canonical SHA-256 fingerprint for request arguments."""
    for arg in args:
        if (
            hasattr(arg, "from_account_id")
            and hasattr(arg, "to_account_id")
            and hasattr(arg, "amount")
        ):
            curr = getattr(arg, "currency", "USD") or "USD"
            if hasattr(arg.amount, "currency"):
                curr = arg.amount.currency
                amt = arg.amount.amount
            else:
                amt = arg.amount
            tenant_id = getattr(arg, "tenant_id", "default")
            return compute_transfer_fingerprint(
                from_account_id=str(arg.from_account_id),
                to_account_id=str(arg.to_account_id),
                amount=amt,
                currency=str(curr),
                tenant_id=str(tenant_id),
            )
    if "from_account_id" in kwargs and "to_account_id" in kwargs and "amount" in kwargs:
        curr = kwargs.get("currency", "USD") or "USD"
        tenant_id = kwargs.get("tenant_id", "default")
        return compute_transfer_fingerprint(
            from_account_id=str(kwargs["from_account_id"]),
            to_account_id=str(kwargs["to_account_id"]),
            amount=kwargs["amount"],
            currency=str(curr),
            tenant_id=str(tenant_id),
        )

    payload = _extract_payload_dict(args, kwargs)
    return compute_request_hash(payload)


class IdempotencyWrapper:
    """Wraps any use case or callable with atomic idempotency semantics."""

    def __init__(
        self,
        target: Callable[..., Any],
        store: IIdempotencyStore,
        in_flight_ttl_seconds: float | int = 120,
        result_ttl_seconds: float | int = 86400,
    ) -> None:
        self.target = target
        self.store = store
        self.in_flight_ttl_seconds = in_flight_ttl_seconds
        self.result_ttl_seconds = result_ttl_seconds

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        key = _extract_idempotency_key(args, kwargs)

        # Passthrough if no idempotency key provided
        if not key:
            return self.target(*args, **kwargs)

        req_hash = _extract_payload_hash(args, kwargs)

        # 1. Fast-path: Return cached completed execution
        cached = self.store.get_result(key)
        if cached is not None:
            if "__request_hash__" in cached and cached["__request_hash__"] != req_hash:
                raise IdempotencyPayloadMismatchError(key)
            res_data = cached.get("__payload__", cached)
            if (
                isinstance(res_data, dict)
                and "transaction_id" in res_data
                and "from_balance_after" in res_data
            ):
                return TransferResult.from_dict(res_data)
            return res_data

        # 2. Acquire in-flight distributed lock
        acquired = self.store.try_acquire(key, ttl_seconds=self.in_flight_ttl_seconds)
        if not acquired:
            # Re-check in case concurrent worker completed in the intervening microsecond
            cached = self.store.get_result(key)
            if cached is not None:
                if "__request_hash__" in cached and cached["__request_hash__"] != req_hash:
                    raise IdempotencyPayloadMismatchError(key)
                res_data = cached.get("__payload__", cached)
                if (
                    isinstance(res_data, dict)
                    and "transaction_id" in res_data
                    and "from_balance_after" in res_data
                ):
                    return TransferResult.from_dict(res_data)
                return res_data
            raise IdempotencyInFlightError(key)

        # 3. Execute target function
        try:
            result = self.target(*args, **kwargs)
        except Exception:
            # Release lock so subsequent retries are not blocked by a failed execution
            self.store.release(key)
            raise

        # 4. Cache successful result
        serialized: dict[str, Any]
        if hasattr(result, "to_dict"):
            serialized = result.to_dict()
        elif isinstance(result, dict):
            serialized = result
        else:
            serialized = {"result": result}

        store_payload = {
            "__request_hash__": req_hash,
            "__payload__": serialized,
        }
        store_payload.update(serialized)
        self.store.store_result(key, store_payload, ttl_seconds=self.result_ttl_seconds)
        return result


def idempotent(
    store: IIdempotencyStore,
    in_flight_ttl_seconds: float | int = 120,
    result_ttl_seconds: float | int = 86400,
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """Function decorator applying idempotency protection to a callable."""

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        wrapper = IdempotencyWrapper(
            target=func,
            store=store,
            in_flight_ttl_seconds=in_flight_ttl_seconds,
            result_ttl_seconds=result_ttl_seconds,
        )

        @wraps(func)
        def inner(*args: Any, **kwargs: Any) -> T:
            return wrapper(*args, **kwargs)  # type: ignore[no-any-return]

        return inner

    return decorator
