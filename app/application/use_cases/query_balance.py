"""Query Balance Use Case implementing the fast read path with Cache-Aside pattern."""

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from app.application.exceptions import AccountNotFoundError
from app.infrastructure.persistence.postgres.unit_of_work import PostgresUnitOfWork
from app.ports.cache_port import ICachePort
from app.ports.repository_ports import IAccountRepository


@dataclass(frozen=True)
class AccountBalanceDTO:
    """Read model DTO containing account balance snapshot."""

    account_id: str
    owner_name: str
    balance: Decimal
    currency: str
    status: str
    is_active: bool
    cached: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Serializes balance DTO to dictionary."""
        return {
            "account_id": self.account_id,
            "owner_name": self.owner_name,
            "balance": str(self.balance),
            "currency": self.currency,
            "status": self.status,
            "is_active": self.is_active,
            "cached": self.cached,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any], cached: bool = True) -> "AccountBalanceDTO":
        """Deserializes balance DTO from dictionary."""
        return cls(
            account_id=str(data["account_id"]),
            owner_name=str(data["owner_name"]),
            balance=Decimal(str(data["balance"])),
            currency=str(data["currency"]),
            status=str(data["status"]),
            is_active=bool(data["is_active"]),
            cached=cached,
        )


class QueryBalanceUseCase:
    """Executes high-throughput balance queries with L1 cache-aside acceleration."""

    def __init__(
        self,
        account_repo: IAccountRepository,
        cache: ICachePort | None = None,
        ttl_seconds: float | int = 60.0,
    ) -> None:
        self.account_repo = account_repo
        self.cache = cache
        self.ttl_seconds = ttl_seconds

    def execute(self, account_id: str) -> AccountBalanceDTO:
        """Retrieves account balance using cache-aside optimization.

        Args:
            account_id: Unique account identifier.

        Returns:
            AccountBalanceDTO: Snapshot of account balance and status.

        Raises:
            AccountNotFoundError: If account does not exist in repository.
        """
        # 1. Check L1 Cache
        if self.cache is not None:
            cached_val = self.cache.get(account_id)
            if cached_val is not None and isinstance(cached_val, dict):
                return AccountBalanceDTO.from_dict(cached_val, cached=True)

        # 2. Cache Miss: Query repository
        account = self.account_repo.get_by_id(account_id)
        if account is None:
            raise AccountNotFoundError(account_id)

        dto = AccountBalanceDTO(
            account_id=account.account_id,
            owner_name=account.owner_name,
            balance=account.balance.amount,
            currency=str(account.balance.currency),
            status=str(account.status),
            is_active=account.is_active(),
            cached=False,
        )

        # 3. Populate L1 Cache
        if self.cache is not None:
            self.cache.put(account_id, dto.to_dict(), ttl_seconds=self.ttl_seconds)

        return dto


class AsyncQueryBalanceUseCase:
    """Executes high-throughput balance queries with L1 cache-aside acceleration
    backed by PostgreSQL.
    """

    def __init__(
        self,
        uow: PostgresUnitOfWork,
        cache: ICachePort | None = None,
        ttl_seconds: float | int = 60.0,
    ) -> None:
        self.uow = uow
        self.cache = cache
        self.ttl_seconds = ttl_seconds

    async def execute(self, account_id: str) -> AccountBalanceDTO:
        """Retrieves account balance using cache-aside optimization from PostgreSQL.

        Args:
            account_id: Unique account identifier.

        Returns:
            AccountBalanceDTO: Snapshot of account balance and status.

        Raises:
            AccountNotFoundError: If account does not exist in repository.
        """
        # 1. Check L1 Cache
        if self.cache is not None:
            cached_val = self.cache.get(account_id)
            if cached_val is not None and isinstance(cached_val, dict):
                return AccountBalanceDTO.from_dict(cached_val, cached=True)

        # 2. Cache Miss: Query PostgreSQL via Unit of Work
        async with self.uow as uow:
            account = await uow.accounts.get_by_id(account_id)

        if account is None:
            raise AccountNotFoundError(account_id)

        dto = AccountBalanceDTO(
            account_id=account.account_id,
            owner_name=account.owner_name,
            balance=account.balance.amount,
            currency=str(account.balance.currency),
            status=str(account.status),
            is_active=account.is_active(),
            cached=False,
        )

        # 3. Populate L1 Cache
        if self.cache is not None:
            self.cache.put(account_id, dto.to_dict(), ttl_seconds=self.ttl_seconds)

        return dto
