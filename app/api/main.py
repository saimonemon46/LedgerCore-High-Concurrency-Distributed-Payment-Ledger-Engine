"""FastAPI Application factory and exception handlers for LedgerCore."""

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.dependencies import get_container
from app.api.routes import accounts, audit, health, transfers
from app.application.exceptions import (
    AccountNotFoundError,
    IdempotencyConflictError,
    IdempotencyInFlightError,
    IdempotencyPayloadMismatchError,
    ReconciliationDivergenceError,
    SelfTransferNotAllowedError,
)
from app.domain.exceptions import (
    AccountFrozenError,
    AccountInactiveError,
    CurrencyMismatchError,
    DomainError,
    InsufficientFundsError,
    LedgerInvariantViolationError,
)
from app.infrastructure.persistence.postgres.database import (
    check_db_health,
    init_db,
)
from app.infrastructure.resilience.circuit_breaker import CircuitBreakerOpenError

logger = logging.getLogger("ledger_core.api")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Manages application startup and graceful shutdown drain."""
    container = get_container()
    logger.info("Starting LedgerCore API services...")
    engine = container.get_db_engine()
    try:
        if await check_db_health(engine):
            await init_db(engine)
            logger.info("PostgreSQL database initialized successfully.")
        else:
            logger.warning("PostgreSQL not reachable at startup. Schema init deferred.")
    except Exception as err:
        logger.warning("Could not initialize PostgreSQL on startup: %s", err)

    yield

    logger.info("Shutting down LedgerCore API services and draining workers...")
    if container.worker_pool.is_running:
        container.worker_pool.shutdown(wait=True)
    if container._db_engine is not None:
        await container._db_engine.dispose()


def create_app() -> FastAPI:
    """Creates and configures the FastAPI application instance."""
    app = FastAPI(
        title="LedgerCore API",
        description=(
            "High-concurrency, distributed double-entry financial ledger engine "
            "engineered with Hexagonal Architecture and strict invariant enforcement."
        ),
        version="1.0.0",
        lifespan=lifespan,
    )

    # CORS Middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Global Exception Handlers
    @app.exception_handler(AccountNotFoundError)
    async def account_not_found_handler(
        request: Request,
        exc: AccountNotFoundError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"detail": str(exc), "error_type": "AccountNotFound"},
        )

    @app.exception_handler(SelfTransferNotAllowedError)
    async def self_transfer_handler(
        request: Request,
        exc: SelfTransferNotAllowedError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={"detail": str(exc), "error_type": "SelfTransferNotAllowed"},
        )

    @app.exception_handler(InsufficientFundsError)
    async def insufficient_funds_handler(
        request: Request,
        exc: InsufficientFundsError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={"detail": str(exc), "error_type": "InsufficientFunds"},
        )

    @app.exception_handler(AccountFrozenError)
    async def account_frozen_handler(
        request: Request,
        exc: AccountFrozenError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={"detail": str(exc), "error_type": "AccountFrozen"},
        )

    @app.exception_handler(AccountInactiveError)
    async def account_inactive_handler(
        request: Request,
        exc: AccountInactiveError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={"detail": str(exc), "error_type": "AccountInactive"},
        )

    @app.exception_handler(CurrencyMismatchError)
    async def currency_mismatch_handler(
        request: Request,
        exc: CurrencyMismatchError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={"detail": str(exc), "error_type": "CurrencyMismatch"},
        )

    @app.exception_handler(DomainError)
    async def domain_error_handler(
        request: Request,
        exc: DomainError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={"detail": str(exc), "error_type": "DomainInvariantViolation"},
        )

    @app.exception_handler(IdempotencyConflictError)
    async def idempotency_conflict_handler(
        request: Request,
        exc: IdempotencyConflictError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={"detail": str(exc), "error_type": "IdempotencyConflict"},
        )

    @app.exception_handler(IdempotencyPayloadMismatchError)
    async def idempotency_payload_mismatch_handler(
        request: Request,
        exc: IdempotencyPayloadMismatchError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={
                "detail": str(exc),
                "error_type": "IdempotencyPayloadMismatch",
                "key": exc.key,
            },
        )

    @app.exception_handler(IdempotencyInFlightError)
    async def idempotency_in_flight_handler(
        request: Request,
        exc: IdempotencyInFlightError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_425_TOO_EARLY,
            headers={"Retry-After": str(exc.retry_after_seconds)},
            content={
                "detail": str(exc),
                "error_type": "IdempotencyInFlight",
                "key": exc.key,
                "retry_after_seconds": exc.retry_after_seconds,
            },
        )

    @app.exception_handler(CircuitBreakerOpenError)
    async def circuit_breaker_open_handler(
        request: Request,
        exc: CircuitBreakerOpenError,
    ) -> JSONResponse:
        retry_secs = max(1, int(exc.retry_after_seconds))
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            headers={"Retry-After": str(retry_secs)},
            content={
                "detail": str(exc),
                "error_type": "CircuitBreakerOpen",
                "retry_after_seconds": exc.retry_after_seconds,
            },
        )

    @app.exception_handler(LedgerInvariantViolationError)
    async def ledger_invariant_handler(
        request: Request,
        exc: LedgerInvariantViolationError,
    ) -> JSONResponse:
        logger.critical("Double-entry invariant violated: %s", exc)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": str(exc), "error_type": "LedgerInvariantViolation"},
        )

    @app.exception_handler(ReconciliationDivergenceError)
    async def reconciliation_divergence_handler(
        request: Request,
        exc: ReconciliationDivergenceError,
    ) -> JSONResponse:
        logger.critical("Audit reconciliation divergence: %s", exc)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "detail": str(exc),
                "error_type": "ReconciliationDivergence",
                "details": exc.details,
            },
        )

    # Root endpoint redirecting to API documentation
    @app.get("/", include_in_schema=False)
    async def root_redirect() -> dict[str, str]:
        return {
            "name": "LedgerCore API",
            "version": "1.0.0",
            "status": "operational",
            "docs_url": "/docs",
            "health_url": "/api/v1/health",
        }

    # Route Registration
    app.include_router(health.router, prefix="/api/v1")
    app.include_router(accounts.router, prefix="/api/v1")
    app.include_router(transfers.router, prefix="/api/v1")
    app.include_router(audit.router, prefix="/api/v1")

    return app


app = create_app()
