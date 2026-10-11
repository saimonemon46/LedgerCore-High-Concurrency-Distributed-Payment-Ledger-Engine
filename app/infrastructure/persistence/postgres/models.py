"""SQLAlchemy ORM models defining the relational database schema for LedgerCore."""

from decimal import Decimal
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Base declarative model with common dictionary serialization."""

    def to_dict(self) -> dict[str, Any]:
        """Converts model attributes to a standard dictionary."""
        return {col.name: getattr(self, col.name) for col in self.__table__.columns}


class AccountModel(Base):
    """Relational model for financial accounts with database-level balance constraints."""

    __tablename__ = "accounts"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_name: Mapped[str] = mapped_column(String(255), nullable=False)
    balance: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ACTIVE")
    created_at: Mapped[Any] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[Any] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    __table_args__ = (
        CheckConstraint("balance >= 0", name="chk_account_balance_non_negative"),
    )


class TransactionModel(Base):
    """Relational model recording causal transactions and state machine history."""

    __tablename__ = "transactions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    source_account_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("accounts.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    destination_account_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("accounts.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    fee: Mapped[Decimal] = mapped_column(
        Numeric(18, 4),
        nullable=False,
        default=Decimal("0.0000"),
    )
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)  # PENDING, SETTLED, FAILED
    error_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[Any] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[Any] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    source_account: Mapped[AccountModel] = relationship(
        "AccountModel",
        foreign_keys=[source_account_id],
        lazy="joined",
    )
    destination_account: Mapped[AccountModel] = relationship(
        "AccountModel",
        foreign_keys=[destination_account_id],
        lazy="joined",
    )


class LedgerEntryModel(Base):
    """Immutable, append-only double-entry journal model with identity sequence ordering."""

    __tablename__ = "ledger_entries"

    sequence_id: Mapped[int] = mapped_column(
        BigInteger,
        Identity(always=True),
        primary_key=True,
    )
    entry_id: Mapped[str] = mapped_column(String(36), unique=True, nullable=False, index=True)
    transaction_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("transactions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    account_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("accounts.id", ondelete="RESTRICT"),
        nullable=False,
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    balance_after: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    entry_type: Mapped[str] = mapped_column(String(10), nullable=False)  # DEBIT, CREDIT
    created_at: Mapped[Any] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    transaction: Mapped[TransactionModel] = relationship(
        "TransactionModel",
        foreign_keys=[transaction_id],
    )

    __table_args__ = (
        Index("idx_ledger_account_sequence", "account_id", "sequence_id"),
        Index("idx_ledger_transaction", "transaction_id"),
    )
