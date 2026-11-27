"""Ledger journal exploration endpoints."""

from fastapi import APIRouter, Depends, Query

from app.api.dependencies import get_postgres_uow
from app.api.schemas import LedgerEntryResponse
from app.infrastructure.persistence.postgres.unit_of_work import PostgresUnitOfWork

router = APIRouter(prefix="/ledger", tags=["Ledger"])


@router.get(
    "/entries",
    response_model=list[LedgerEntryResponse],
    summary="Query immutable journal entries",
)
async def list_ledger_entries(
    limit: int = Query(default=100, ge=1, le=500),
    uow: PostgresUnitOfWork = Depends(get_postgres_uow),
) -> list[LedgerEntryResponse]:
    """Retrieves immutable append-only journal entries directly from PostgreSQL."""
    async with uow:
        entries = await uow.ledger.get_all_entries_models(limit=limit)
        return [
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
