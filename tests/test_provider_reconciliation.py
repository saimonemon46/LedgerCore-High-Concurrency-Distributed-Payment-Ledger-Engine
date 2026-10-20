"""Integration tests for External Provider Lifecycle and Unknown-Outcome Recovery.

Verifies:
1. Provider network timeout induces PENDING_RECONCILIATION state rather than blind retries.
2. Background reconciliation queries provider status via idempotency keys and resolves transactions.
"""

import uuid
from collections.abc import AsyncGenerator
from decimal import Decimal

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.application.use_cases.reconcile_provider_transfers import (
    ReconcileProviderTransfersUseCase,
)
from app.domain.models import Account, AccountStatus
from app.domain.value_objects import Currency, Money
from app.infrastructure.adapters.mock_payment_provider import MockPaymentProvider
from app.infrastructure.config import get_settings
from app.infrastructure.persistence.postgres.database import (
    check_db_health,
    create_async_db_engine,
    get_async_session_factory,
    init_db,
)
from app.infrastructure.persistence.postgres.models import (
    ExternalPaymentRecordModel,
    TransactionModel,
)
from app.infrastructure.persistence.postgres.unit_of_work import PostgresUnitOfWork
from app.ports.payment_provider_port import (
    ProviderPaymentCommand,
    ProviderStatus,
)


@pytest.fixture
async def pg_engine() -> AsyncGenerator[AsyncEngine, None]:
    settings = get_settings()
    engine = create_async_db_engine(settings.database_url)
    healthy = await check_db_health(engine)
    if not healthy:
        pytest.skip("PostgreSQL database is not reachable at " + settings.database_url)
    await init_db(engine)
    yield engine
    await engine.dispose()


@pytest.fixture
async def session_factory(
    pg_engine: AsyncEngine,
) -> AsyncGenerator[async_sessionmaker[AsyncSession], None]:
    factory = get_async_session_factory(pg_engine)
    async with pg_engine.begin() as conn:
        await conn.execute(
            text(
                "TRUNCATE TABLE external_payment_records, ledger_entries, "
                "transactions, accounts CASCADE;"
            )
        )
    yield factory


@pytest.fixture
def uow(session_factory: async_sessionmaker[AsyncSession]) -> PostgresUnitOfWork:
    return PostgresUnitOfWork(session_factory)


@pytest.mark.asyncio
class TestProviderLifecycleAndReconciliation:
    """Verifies external payment timeout handling and background reconciliation."""

    async def test_provider_timeout_enters_pending_reconciliation(
        self,
        uow: PostgresUnitOfWork,
    ) -> None:
        """Proves network timeout does not blindly retry; transitions to PENDING_RECONCILIATION."""
        timeout_key = "idemp_prov_timeout_123"
        provider = MockPaymentProvider(simulate_timeout_on_keys={timeout_key})

        cmd = ProviderPaymentCommand(
            idempotency_key=timeout_key,
            transfer_id="tx_payout_timeout",
            amount=Money(Decimal("250.00"), Currency.USD),
            recipient_identifier="card_tok_9988",
        )

        result = await provider.execute_payout(cmd)
        assert result.status == ProviderStatus.PENDING_RECONCILIATION
        assert "timeout" in (result.error_message or "").lower()

    async def test_reconciliation_resolves_ambiguous_payment(
        self,
        uow: PostgresUnitOfWork,
    ) -> None:
        """Proves background reconciliation recovers ambiguous outcome using idempotency key."""
        idemp_key = "idemp_prov_reconcile_456"
        tx_id = f"tx_rec_{uuid.uuid4().hex[:8]}"

        # 1. Setup mock provider where transaction actually succeeded at the gateway
        provider = MockPaymentProvider(simulate_timeout_on_keys={idemp_key})
        cmd = ProviderPaymentCommand(
            idempotency_key=idemp_key,
            transfer_id=tx_id,
            amount=Money(Decimal("100.00"), Currency.USD),
            recipient_identifier="bank_acc_1122",
        )
        # Induce timeout response
        timeout_result = await provider.execute_payout(cmd)
        assert timeout_result.status == ProviderStatus.PENDING_RECONCILIATION

        # 2. Persist underlying accounts, transaction & ambiguous external record in DB
        async with uow:
            assert uow.session is not None
            # Seed source and clearing accounts
            acc_src = Account(
                account_id="ACC-SOURCE",
                owner_name="Payout Sender",
                balance=Money(Decimal("1000.00"), Currency.USD),
                status=AccountStatus.ACTIVE,
            )
            acc_dest = Account(
                account_id="ACC-EXT-CLEARING",
                owner_name="Clearing Gateway",
                balance=Money(Decimal("0.00"), Currency.USD),
                status=AccountStatus.ACTIVE,
            )
            await uow.accounts.save(acc_src)
            await uow.accounts.save(acc_dest)

            # Seed transaction record
            tx_model = TransactionModel(
                id=tx_id,
                source_account_id="ACC-SOURCE",
                destination_account_id="ACC-EXT-CLEARING",
                amount=Decimal("100.00"),
                currency="USD",
                status="PENDING",
            )
            uow.session.add(tx_model)
            await uow.session.flush()

            # Seed external payment record in PENDING_RECONCILIATION state
            ext_record = ExternalPaymentRecordModel(
                id=str(uuid.uuid4()),
                transaction_id=tx_id,
                provider_name="mock_bank",
                idempotency_key=idemp_key,
                status=ProviderStatus.PENDING_RECONCILIATION.value,
            )
            uow.session.add(ext_record)
            await uow.commit()

        # 3. Execute background reconciliation use case
        reconcile_use_case = ReconcileProviderTransfersUseCase(uow=uow, provider=provider)
        report = await reconcile_use_case.execute()

        assert report.scanned_count == 1
        assert report.resolved_success_count == 1
        assert report.pending_count == 0

        # 4. Verify DB record transitioned to SUCCEEDED with provider tx ID
        async with uow:
            assert uow.session is not None
            stmt = select(ExternalPaymentRecordModel).where(
                ExternalPaymentRecordModel.transaction_id == tx_id
            )
            updated_rec = (await uow.session.execute(stmt)).scalar_one()
            assert updated_rec.status == ProviderStatus.SUCCEEDED.value
            assert updated_rec.provider_tx_id is not None
            assert updated_rec.provider_tx_id.startswith("prov_tx_")
