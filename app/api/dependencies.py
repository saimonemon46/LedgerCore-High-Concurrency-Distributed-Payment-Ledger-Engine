"""Dependency Injection container and service lifecycles for LedgerCore API."""

import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.application.use_cases.audit_reconciliation import AuditReconciliationUseCase
from app.application.use_cases.audit_reconciliation_async import (
    AsyncAuditReconciliationUseCase,
)
from app.application.use_cases.execute_transfer import ExecuteTransferUseCase
from app.application.use_cases.execute_transfer_async import (
    AsyncExecuteTransferUseCase,
)
from app.application.use_cases.query_balance import QueryBalanceUseCase
from app.infrastructure.concurrency.lock_manager import CanonicalLockManager
from app.infrastructure.dsa.lru_ttl_cache import LRUTTLCache
from app.infrastructure.os_threading.worker_pool import ThreadSafeWorkerPool
from app.infrastructure.persistence.memory_repositories import (
    InMemoryAccountRepository,
    InMemoryIdempotencyStore,
    InMemoryLedgerRepository,
)
from app.infrastructure.persistence.postgres.database import (
    create_async_db_engine,
    get_async_session_factory,
)
from app.infrastructure.persistence.postgres.unit_of_work import PostgresUnitOfWork
from app.infrastructure.resilience.circuit_breaker import CircuitBreaker
from app.ports.cache_port import ICachePort
from app.ports.event_publisher_port import IEventPublisher, TransactionSettledEvent
from app.ports.idempotency_port import IIdempotencyStore
from app.ports.repository_ports import IAccountRepository, ILedgerRepository

logger = logging.getLogger("ledger_core.api")


class WorkerPoolEventPublisher(IEventPublisher):
    """Event publisher adapter offloading side-effects to OS worker pool threads."""

    def __init__(self, worker_pool: ThreadSafeWorkerPool) -> None:
        self.worker_pool = worker_pool

    def _process_event(self, event: TransactionSettledEvent) -> None:
        logger.info(
            "Transaction settled event processed: tx=%s amount=%s",
            event.transaction_id,
            event.amount,
        )

    def publish(self, event: TransactionSettledEvent) -> None:
        if self.worker_pool.is_running:
            self.worker_pool.submit(lambda: self._process_event(event))

    def publish_generic(self, event_type: str, payload: dict[str, Any]) -> None:
        pass


class Container:
    """Singleton application service registry."""

    _instance: "Container | None" = None

    def __init__(self) -> None:
        self.account_repo: InMemoryAccountRepository = InMemoryAccountRepository()
        self.ledger_repo: InMemoryLedgerRepository = InMemoryLedgerRepository()
        self.idempotency_store: InMemoryIdempotencyStore = InMemoryIdempotencyStore()
        self.cache: LRUTTLCache = LRUTTLCache(capacity=5000, default_ttl_seconds=60.0)
        self.lock_manager: CanonicalLockManager = CanonicalLockManager()
        self.circuit_breaker: CircuitBreaker = CircuitBreaker(
            name="api_storage_breaker",
            failure_threshold_rate=0.5,
            min_requests=5,
            recovery_timeout_seconds=5.0,
        )
        self.worker_pool: ThreadSafeWorkerPool = ThreadSafeWorkerPool(
            worker_count=4,
            max_queue_size=1000,
        )
        self.worker_pool.start()
        self.event_publisher: IEventPublisher = WorkerPoolEventPublisher(self.worker_pool)
        self._db_engine: AsyncEngine | None = None
        self._session_factory: async_sessionmaker[AsyncSession] | None = None

    def get_db_engine(self) -> AsyncEngine:
        """Lazy-initializes and provides the PostgreSQL async engine."""
        if self._db_engine is None:
            self._db_engine = create_async_db_engine()
        return self._db_engine

    def get_session_factory(self) -> async_sessionmaker[AsyncSession]:
        """Lazy-initializes and provides the PostgreSQL async session factory."""
        if self._session_factory is None:
            self._session_factory = get_async_session_factory(self.get_db_engine())
        return self._session_factory

    def get_postgres_uow(self) -> PostgresUnitOfWork:
        """Instantiates a new PostgreSQL Unit of Work."""
        return PostgresUnitOfWork(self.get_session_factory())

    @classmethod
    def get_instance(cls) -> "Container":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        """Resets the singleton container for test isolation."""
        if cls._instance is not None:
            if cls._instance.worker_pool.is_running:
                cls._instance.worker_pool.shutdown(wait=False)
        cls._instance = cls()


def get_container() -> Container:
    """Retrieves application container."""
    return Container.get_instance()


def get_account_repo() -> IAccountRepository:
    """Provides Account Repository port."""
    return get_container().account_repo


def get_ledger_repo() -> ILedgerRepository:
    """Provides Ledger Repository port."""
    return get_container().ledger_repo


def get_idempotency_store() -> IIdempotencyStore:
    """Provides Idempotency Store port."""
    return get_container().idempotency_store


def get_cache() -> ICachePort:
    """Provides Cache port."""
    return get_container().cache


def get_lock_manager() -> CanonicalLockManager:
    """Provides Lock Manager."""
    return get_container().lock_manager


def get_circuit_breaker() -> CircuitBreaker:
    """Provides Circuit Breaker."""
    return get_container().circuit_breaker


def get_worker_pool() -> ThreadSafeWorkerPool:
    """Provides Worker Pool."""
    return get_container().worker_pool


def get_postgres_uow() -> PostgresUnitOfWork:
    """Provides PostgreSQL Unit of Work."""
    return get_container().get_postgres_uow()


def get_async_transfer_use_case() -> AsyncExecuteTransferUseCase:
    """Builds and provides AsyncExecuteTransferUseCase backed by PostgreSQL Unit of Work."""
    c = get_container()
    return AsyncExecuteTransferUseCase(
        uow=c.get_postgres_uow(),
        cache=c.cache,
        event_publisher=c.event_publisher,
    )


def get_async_audit_use_case() -> AsyncAuditReconciliationUseCase:
    """Builds and provides AsyncAuditReconciliationUseCase backed by PostgreSQL."""
    c = get_container()
    return AsyncAuditReconciliationUseCase(uow=c.get_postgres_uow())


def get_transfer_use_case() -> ExecuteTransferUseCase:
    """Builds and provides ExecuteTransferUseCase."""
    c = get_container()
    return ExecuteTransferUseCase(
        account_repo=c.account_repo,
        ledger_repo=c.ledger_repo,
        lock_manager=c.lock_manager,
        event_publisher=c.event_publisher,
        cache=c.cache,
    )


def get_audit_use_case() -> AuditReconciliationUseCase:
    """Builds and provides AuditReconciliationUseCase."""
    c = get_container()
    return AuditReconciliationUseCase(
        account_repo=c.account_repo,
        ledger_repo=c.ledger_repo,
    )


def get_query_balance_use_case() -> QueryBalanceUseCase:
    """Builds and provides QueryBalanceUseCase."""
    c = get_container()
    return QueryBalanceUseCase(
        account_repo=c.account_repo,
        cache=c.cache,
        ttl_seconds=60.0,
    )
