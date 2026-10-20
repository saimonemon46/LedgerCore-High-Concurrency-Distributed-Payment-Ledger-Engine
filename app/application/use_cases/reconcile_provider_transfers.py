"""External Payment Provider Reconciliation Use Case.

Resolves transactions stuck in PENDING_RECONCILIATION state by querying provider
APIs with stored idempotency keys, eliminating duplicate financial executions.
"""

import logging
from dataclasses import dataclass

from sqlalchemy import select

from app.infrastructure.persistence.postgres.models import ExternalPaymentRecordModel
from app.infrastructure.persistence.postgres.unit_of_work import PostgresUnitOfWork
from app.ports.payment_provider_port import IPaymentProviderPort, ProviderStatus

logger = logging.getLogger("ledger_core.reconciliation")


@dataclass(frozen=True)
class ReconciliationReport:
    """Summary of external payment reconciliation execution."""

    scanned_count: int
    resolved_success_count: int
    resolved_failed_count: int
    pending_count: int


class ReconcileProviderTransfersUseCase:
    """Reconciles ambiguous external payments against provider ledgers."""

    def __init__(
        self,
        uow: PostgresUnitOfWork,
        provider: IPaymentProviderPort,
    ) -> None:
        self.uow = uow
        self.provider = provider

    async def execute(self) -> ReconciliationReport:
        async with self.uow as uow:
            assert uow.session is not None
            stmt = select(ExternalPaymentRecordModel).where(
                ExternalPaymentRecordModel.status == ProviderStatus.PENDING_RECONCILIATION.value
            )
            result = await uow.session.execute(stmt)
            records = list(result.scalars().all())

            scanned = len(records)
            resolved_success = 0
            resolved_failed = 0
            pending = 0

            for rec in records:
                try:
                    status_res = await self.provider.check_status(
                        idempotency_key=rec.idempotency_key,
                        provider_tx_id=rec.provider_tx_id,
                    )

                    if status_res.status == ProviderStatus.SUCCEEDED:
                        rec.status = ProviderStatus.SUCCEEDED.value
                        rec.provider_tx_id = status_res.provider_tx_id
                        rec.last_response = status_res.raw_response
                        resolved_success += 1
                        logger.info(
                            "Reconciliation SUCCESS for tx %s (provider_tx=%s)",
                            rec.transaction_id,
                            rec.provider_tx_id,
                        )
                    elif status_res.status == ProviderStatus.FAILED:
                        rec.status = ProviderStatus.FAILED.value
                        resolved_failed += 1
                        logger.warning(
                            "Reconciliation FAILED for tx %s: %s",
                            rec.transaction_id,
                            status_res.error_message,
                        )
                    else:
                        pending += 1

                except Exception as e:
                    logger.error(
                        "Error checking status for payment record %s: %s",
                        rec.id,
                        e,
                    )
                    pending += 1

            await uow.commit()

            return ReconciliationReport(
                scanned_count=scanned,
                resolved_success_count=resolved_success,
                resolved_failed_count=resolved_failed,
                pending_count=pending,
            )
