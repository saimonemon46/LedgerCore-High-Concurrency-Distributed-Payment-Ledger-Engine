"""Audit and mathematical reconciliation routes."""

from fastapi import APIRouter, Depends, Query, status

from app.api.dependencies import get_async_audit_use_case
from app.api.schemas import (
    AccountDiscrepancySchema,
    AuditReconciliationResponse,
)
from app.application.use_cases.audit_reconciliation_async import (
    AsyncAuditReconciliationUseCase,
)

router = APIRouter(prefix="/audit", tags=["Audit"])


@router.post(
    "/reconcile",
    response_model=AuditReconciliationResponse,
    status_code=status.HTTP_200_OK,
    summary="Trigger real-time mathematical ledger reconciliation",
)
async def reconcile_ledger(
    raise_on_error: bool = Query(
        default=False,
        description="Whether to fail with 500 error on divergence",
    ),
    use_case: AsyncAuditReconciliationUseCase = Depends(get_async_audit_use_case),
) -> AuditReconciliationResponse:
    """Audits system-wide financial invariants, ensuring net zero conservation."""
    report = await use_case.reconcile(raise_on_error=raise_on_error)
    return AuditReconciliationResponse(
        total_account_balances=str(report.total_account_balances),
        total_ledger_credits=str(report.total_ledger_credits),
        total_ledger_debits=str(report.total_ledger_debits),
        total_system_net=str(report.total_system_net),
        is_system_net_zero=report.is_system_net_zero,
        is_balanced=report.is_balanced,
        accounts_audited_count=report.accounts_audited_count,
        ledger_entries_count=report.ledger_entries_count,
        discrepancies=[
            AccountDiscrepancySchema(
                account_id=d.account_id,
                actual_balance=str(d.actual_balance),
                expected_balance=str(d.expected_balance),
                discrepancy=str(d.discrepancy),
            )
            for d in report.discrepancies
        ],
        timestamp=report.timestamp,
    )
