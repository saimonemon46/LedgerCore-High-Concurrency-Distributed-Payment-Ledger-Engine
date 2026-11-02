"""Production Value Objects template for double-entry financial ledgers.

Guarantees:
1. Strict Decimal representation (Zero IEEE-754 floats).
2. Immutable frozen dataclass semantics.
3. Currency isolation (prevents adding USD to EUR).
4. Canonical 2-decimal scale quantization (ROUND_HALF_UP).
"""

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum
from typing import Self


class CurrencyMismatchError(ValueError):
    """Raised when arithmetic is attempted between mismatched currencies."""
    pass


class InvalidMoneyError(ValueError):
    """Raised when an invalid monetary amount or precision is supplied."""
    pass


class Currency(StrEnum):
    """Supported ISO 4217 standard currency codes."""
    USD = "USD"
    EUR = "EUR"
    GBP = "GBP"
    BDT = "BDT"
    JPY = "JPY"


@dataclass(frozen=True)
class Money:
    """Immutable monetary representation enforcing exact Decimal scale and currency safety."""

    amount: Decimal
    currency: str = "USD"

    def __post_init__(self) -> None:
        if not isinstance(self.amount, Decimal):
            raise TypeError(
                f"Money amount must be Decimal, got {type(self.amount).__name__}."
            )

        if not self.amount.is_finite():
            raise InvalidMoneyError("Money amount must be a finite Decimal number.")

        if not isinstance(self.currency, str) or not self.currency.strip():
            raise ValueError("Currency must be a non-empty string.")

        # Normalize to canonical 2-decimal places and uppercase currency code
        canonical_amount = self.amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        object.__setattr__(self, "amount", canonical_amount)
        object.__setattr__(self, "currency", self.currency.strip().upper())

    def _assert_same_currency(self, other: "Money") -> None:
        if not isinstance(other, Money):
            raise TypeError(f"Expected Money instance, got {type(other).__name__}")
        if self.currency != other.currency:
            raise CurrencyMismatchError(
                f"Currency mismatch: {self.currency} vs {other.currency}"
            )

    def add(self, other: "Money") -> "Money":
        """Adds two Money amounts of identical currency."""
        self._assert_same_currency(other)
        return Money(self.amount + other.amount, self.currency)

    def subtract(self, other: "Money") -> "Money":
        """Subtracts another Money amount of identical currency."""
        self._assert_same_currency(other)
        return Money(self.amount - other.amount, self.currency)

    def multiply(self, factor: Decimal | int) -> "Money":
        """Multiplies Money amount by a scalar factor."""
        if not isinstance(factor, (Decimal, int)):
            raise TypeError("Multiply factor must be a Decimal or int instance.")
        dec_factor = Decimal(factor) if isinstance(factor, int) else factor
        product = (self.amount * dec_factor).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        return Money(product, self.currency)

    def is_positive(self) -> bool:
        """Returns True if amount > 0.00."""
        return self.amount > Decimal("0.00")

    def is_zero(self) -> bool:
        """Returns True if amount == 0.00."""
        return self.amount == Decimal("0.00")

    def is_negative(self) -> bool:
        """Returns True if amount < 0.00."""
        return self.amount < Decimal("0.00")

    def __add__(self, other: "Money") -> "Money":
        return self.add(other)

    def __sub__(self, other: "Money") -> "Money":
        return self.subtract(other)

    def __mul__(self, factor: Decimal | int) -> "Money":
        return self.multiply(factor)

    def __lt__(self, other: "Money") -> bool:
        self._assert_same_currency(other)
        return self.amount < other.amount

    def __le__(self, other: "Money") -> bool:
        self._assert_same_currency(other)
        return self.amount <= other.amount

    def __gt__(self, other: "Money") -> bool:
        self._assert_same_currency(other)
        return self.amount > other.amount

    def __ge__(self, other: "Money") -> bool:
        self._assert_same_currency(other)
        return self.amount >= other.amount

    def __str__(self) -> str:
        return f"{self.amount:.2f} {self.currency}"

    @classmethod
    def from_str(cls, amount_str: str, currency: str = "USD") -> Self:
        """Safe constructor from a numeric string."""
        return cls(Decimal(amount_str), currency)
