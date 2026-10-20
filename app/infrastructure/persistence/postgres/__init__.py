"""PostgreSQL persistence layer with SQLAlchemy Async and asyncpg."""

from app.infrastructure.persistence.postgres.database import (
    check_db_health,
    create_async_db_engine,
    drop_db,
    get_async_session_factory,
    init_db,
)
from app.infrastructure.persistence.postgres.models import (
    AccountModel,
    Base,
    ConsumerProcessedEventModel,
    ExternalPaymentRecordModel,
    IdempotencyRecordModel,
    LedgerEntryModel,
    OutboxEventModel,
    TransactionModel,
)
from app.infrastructure.persistence.postgres.repositories import (
    PostgresAccountRepository,
    PostgresConsumerDeduplicationRepository,
    PostgresIdempotencyRepository,
    PostgresLedgerRepository,
    PostgresOutboxRepository,
)
from app.infrastructure.persistence.postgres.unit_of_work import PostgresUnitOfWork

__all__ = [
    "AccountModel",
    "Base",
    "ConsumerProcessedEventModel",
    "ExternalPaymentRecordModel",
    "IdempotencyRecordModel",
    "LedgerEntryModel",
    "OutboxEventModel",
    "PostgresAccountRepository",
    "PostgresConsumerDeduplicationRepository",
    "PostgresIdempotencyRepository",
    "PostgresLedgerRepository",
    "PostgresOutboxRepository",
    "PostgresUnitOfWork",
    "TransactionModel",
    "check_db_health",
    "create_async_db_engine",
    "drop_db",
    "get_async_session_factory",
    "init_db",
]
