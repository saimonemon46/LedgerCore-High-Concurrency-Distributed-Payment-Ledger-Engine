"""Account management and balance query routes."""

import time
import uuid
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.dependencies import (
    get_async_query_balance_use_case,
    get_postgres_uow,
)
from app.api.schemas import AccountResponse, CreateAccountRequest
from app.application.use_cases.query_balance import AsyncQueryBalanceUseCase
from app.domain.models import Account, LedgerEntry
from app.domain.value_objects import Currency, Money
from app.infrastructure.persistence.postgres.unit_of_work import PostgresUnitOfWork

router = APIRouter(prefix="/accounts", tags=["Accounts"])


@router.post(
    "",
    response_model=AccountResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Provision a new account",
)
async def create_account(
    request: CreateAccountRequest,
    uow: PostgresUnitOfWork = Depends(get_postgres_uow),
) -> AccountResponse:
    """Provisions a new account with optional initial balance and opening ledger entry."""
    currency = Currency(request.currency.upper())
    balance = Money(request.initial_balance, currency)
    account = Account(
        account_id=request.account_id,
        owner_name=request.owner_name,
        balance=balance,
    )

    async with uow:
        existing = await uow.accounts.get_by_id(request.account_id)
        if existing is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Account with ID '{request.account_id}' already exists.",
            )

        await uow.accounts.save(account)

        # If opening balance is positive, record balanced double-entry
        # (Reserve Debit + Account Credit)
        if request.initial_balance > Decimal("0.00"):
            reserve_id = f"ACC-SYSTEM-RESERVE-{currency.value}"
            reserve = await uow.accounts.get_by_id(reserve_id)
            if reserve is None:
                reserve = Account(
                    account_id=reserve_id,
                    owner_name=f"System Capital Reserve ({currency.value})",
                    balance=Money.zero(currency),
                )
            reserve.balance = reserve.balance.subtract(balance)
            await uow.accounts.save(reserve)

            now = time.time()
            tx_id = str(uuid.uuid4())
            await uow.record_transaction(
                tx_id=tx_id,
                from_account_id=reserve_id,
                to_account_id=request.account_id,
                amount=request.initial_balance,
                currency=str(currency),
                status="SETTLED",
            )
            credit_entry = LedgerEntry.create_credit(
                entry_id=str(uuid.uuid4()),
                transaction_id=tx_id,
                account_id=request.account_id,
                amount=request.initial_balance,
                balance_after=account.balance.amount,
                timestamp=now,
            )
            debit_entry = LedgerEntry.create_debit(
                entry_id=str(uuid.uuid4()),
                transaction_id=tx_id,
                account_id=reserve_id,
                amount=request.initial_balance,
                balance_after=reserve.balance.amount,
                timestamp=now,
            )
            await uow.append_entries([credit_entry, debit_entry], currency=str(currency))

        await uow.commit()

    return AccountResponse(
        account_id=account.account_id,
        owner_name=account.owner_name,
        balance=str(account.balance.amount),
        currency=str(account.balance.currency),
        status=str(account.status),
        is_active=account.is_active(),
        cached=False,
    )


@router.get(
    "/{account_id}/balance",
    response_model=AccountResponse,
    summary="Query account balance",
)
async def get_balance(
    account_id: str,
    query_use_case: AsyncQueryBalanceUseCase = Depends(get_async_query_balance_use_case),
) -> AccountResponse:
    """Retrieves account balance with L1 cache-aside acceleration."""
    dto = await query_use_case.execute(account_id)
    return AccountResponse(
        account_id=dto.account_id,
        owner_name=dto.owner_name,
        balance=str(dto.balance),
        currency=dto.currency,
        status=dto.status,
        is_active=dto.is_active,
        cached=dto.cached,
    )
