"""Transfer execution routes with idempotency and circuit breaker protection."""

from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status

from app.api.dependencies import (
    enforce_transfer_rate_limit,
    get_async_transfer_use_case,
    get_circuit_breaker,
    get_postgres_uow,
)
from app.api.schemas import (
    LedgerEntryResponse,
    TransactionDetailResponse,
    TransferRequest,
    TransferResponse,
)
from app.application.exceptions import (
    ApplicationError,
    InvalidIdempotencyKeyError,
    MissingIdempotencyKeyError,
)
from app.application.use_cases.execute_transfer import TransferCommand
from app.application.use_cases.execute_transfer_async import AsyncExecuteTransferUseCase
from app.domain.exceptions import DomainError
from app.domain.strategies.fee_strategy import (
    FlatFeeStrategy,
    IFeeStrategy,
    MerchantFeeStrategy,
    P2PPeerFeeStrategy,
)
from app.domain.value_objects import Currency, Money
from app.infrastructure.observability.metrics import metrics
from app.infrastructure.persistence.postgres.unit_of_work import PostgresUnitOfWork
from app.infrastructure.resilience.circuit_breaker import CircuitBreaker

router = APIRouter(prefix="/transfers", tags=["Transfers"])


def _resolve_fee_strategy(request: TransferRequest) -> IFeeStrategy:
    """Instantiates the appropriate commercial fee calculation strategy."""
    strat_type = request.fee_strategy_type.upper()
    if strat_type == "FLAT":
        return FlatFeeStrategy(flat_fee=request.flat_fee)
    if strat_type == "MERCHANT":
        rate = request.fee_rate if request.fee_rate > Decimal("0.00") else Decimal("0.015")
        return MerchantFeeStrategy(rate=rate)
    # Default to P2P Strategy
    return P2PPeerFeeStrategy(flat_fee=request.flat_fee, rate=request.fee_rate)


@router.post(
    "",
    response_model=TransferResponse,
    status_code=status.HTTP_200_OK,
    summary="Execute an atomic double-entry money transfer",
)
async def execute_transfer(
    request: TransferRequest,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
    use_case: AsyncExecuteTransferUseCase = Depends(get_async_transfer_use_case),
    circuit_breaker: CircuitBreaker = Depends(get_circuit_breaker),
    _: None = Depends(enforce_transfer_rate_limit),
) -> TransferResponse:
    """Executes a financial transfer with required idempotency and resilience protection."""
    # Fast-fail if circuit breaker is OPEN
    if not circuit_breaker.can_execute():
        circuit_breaker.execute(lambda: None)

    # Require and validate idempotency key for payment creation
    key = idempotency_key or getattr(request, "idempotency_key", None)
    if not key or not str(key).strip():
        raise MissingIdempotencyKeyError()
    clean_key = str(key).strip()
    if len(clean_key) > 128:
        raise InvalidIdempotencyKeyError(clean_key, "Key exceeds maximum length of 128 characters.")

    strategy = _resolve_fee_strategy(request)
    currency = Currency(request.currency.upper())
    amount = Money(request.amount, currency)

    command = TransferCommand(
        from_account_id=request.from_account_id,
        to_account_id=request.to_account_id,
        amount=amount,
        fee_strategy=strategy,
        fee_account_id=request.fee_account_id,
        idempotency_key=clean_key,
        metadata=request.metadata,
    )

    try:
        result = await use_case.execute(command)
        circuit_breaker.record_success()
        metrics.inc_transfers_settled()
        metrics.set_circuit_breaker_state(circuit_breaker.get_state().value)
    except (DomainError, ApplicationError, ValueError, HTTPException):
        # Expected business, validation, and rate-limit errors must never trip the circuit breaker
        metrics.inc_transfers_failed()
        raise
    except Exception:
        # Only genuine infrastructure/downstream faults count toward circuit breaker tripping
        circuit_breaker.record_failure()
        metrics.inc_transfers_failed()
        metrics.set_circuit_breaker_state(circuit_breaker.get_state().value)
        raise

    return TransferResponse(
        transaction_id=result.transaction_id,
        from_account_id=result.from_account_id,
        to_account_id=result.to_account_id,
        amount=str(result.amount.amount),
        currency=str(result.amount.currency),
        fee=str(result.fee.amount),
        from_balance_after=str(result.from_balance_after.amount),
        to_balance_after=str(result.to_balance_after.amount),
        status=result.status,
        created_at=result.created_at,
        ledger_entry_ids=result.ledger_entry_ids,
        metadata=result.metadata,
    )


@router.get(
    "",
    response_model=list[TransactionDetailResponse],
    summary="List recent transfers",
)
async def list_transfers(
    limit: int = Query(default=50, ge=1, le=200),
    uow: PostgresUnitOfWork = Depends(get_postgres_uow),
) -> list[TransactionDetailResponse]:
    """Retrieves recent transactions directly from PostgreSQL."""
    async with uow:
        txs = await uow.get_transactions(limit=limit)
        return [
            TransactionDetailResponse(
                id=t.id,
                tenant_id=t.tenant_id,
                idempotency_key=t.idempotency_key,
                source_account_id=t.source_account_id,
                destination_account_id=t.destination_account_id,
                amount=str(t.amount),
                fee=str(t.fee),
                currency=t.currency,
                status=t.status,
                created_at=t.created_at.isoformat() if t.created_at else "",
                postings=[],
            )
            for t in txs
        ]


@router.get(
    "/{transaction_id}",
    response_model=TransactionDetailResponse,
    summary="Get transaction details and postings",
)
async def get_transfer(
    transaction_id: str,
    uow: PostgresUnitOfWork = Depends(get_postgres_uow),
) -> TransactionDetailResponse:
    """Retrieves transaction details and its associated double-entry ledger postings."""
    async with uow:
        tx = await uow.get_transaction_by_id(transaction_id)
        if tx is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Transaction with ID '{transaction_id}' not found.",
            )

        entries = await uow.ledger.get_entries_for_transaction(transaction_id)
        postings = [
            LedgerEntryResponse(
                id=e.entry_id,
                transaction_id=e.transaction_id,
                account_id=e.account_id,
                amount=str(abs(e.amount)),
                currency=e.currency,
                balance_after=str(e.balance_after),
                entry_type=e.entry_type,
                sequence_id=e.sequence_id,
                created_at=e.created_at.isoformat() if e.created_at else "",
            )
            for e in entries
        ]

        return TransactionDetailResponse(
            id=tx.id,
            tenant_id=tx.tenant_id,
            idempotency_key=tx.idempotency_key,
            source_account_id=tx.source_account_id,
            destination_account_id=tx.destination_account_id,
            amount=str(tx.amount),
            fee=str(tx.fee),
            currency=tx.currency,
            status=tx.status,
            created_at=tx.created_at.isoformat() if tx.created_at else "",
            postings=postings,
        )
