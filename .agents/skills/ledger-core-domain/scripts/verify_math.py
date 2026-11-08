#!/usr/bin/env python3
"""Double-entry balance verification script.

Accepts lists of debit and credit amounts, parses them into exact Decimal values,
and verifies mathematical zero-drift conservation.
"""

import argparse
import os
import sys
from decimal import (
    Decimal,
    InvalidOperation,
)

# Ensure repository root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../..")))

try:
    from app.domain.value_objects import Money
except ImportError:
    from templates.value_objects import Money  # type: ignore[no-redef]

MAX_ADJUSTED_EXPONENT = 30


def _parse(values: list[str]) -> list[Decimal]:
    parsed = []
    for v in values:
        p = Decimal(str(v))
        if not p.is_finite():
            raise InvalidOperation("non-finite amount")
        if p.adjusted() > MAX_ADJUSTED_EXPONENT:
            raise InvalidOperation(f"amount too large (max exponent {MAX_ADJUSTED_EXPONENT}): {v}")
        if isinstance(p.as_tuple().exponent, int) and p.as_tuple().exponent < -2:
            raise InvalidOperation(f"excess decimal scale (max 2 decimal places allowed): {v}")
        parsed.append(p)
    return parsed


def verify_balance(
    debits: list[str],
    credits: list[str],
    currency: str = "USD",
) -> tuple[bool, Money, Money, Money]:
    dec_debits = _parse(debits)
    dec_credits = _parse(credits)

    # Require credits to follow standard non-negative credit convention
    for c in dec_credits:
        if c < Decimal("0.00"):
            raise InvalidOperation(f"credit amounts must be positive: {c}")

    # Debits can be provided either as signed negative entries (-100.00)
    # or unsigned magnitudes (100.00). Use Money value object for exact calculation.
    zero_money = Money(Decimal("0.00"), currency)
    sum_debits = zero_money
    for d in dec_debits:
        sum_debits = sum_debits.add(Money(abs(d), currency))

    sum_credits = zero_money
    for c in dec_credits:
        sum_credits = sum_credits.add(Money(c, currency))

    drift = sum_debits.subtract(sum_credits)
    balanced = drift.is_zero()

    return balanced, sum_debits, sum_credits, drift


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Verify mathematical conservation: sum(debits) == sum(credits)"
    )
    parser.add_argument(
        "--debits",
        nargs="+",
        required=True,
        help="List of debit amounts (e.g. -100.00 -5.00 or 100.00 5.00, max 2 decimal places)",
    )
    parser.add_argument(
        "--credits",
        nargs="+",
        required=True,
        help="List of credit amounts (e.g. 105.00, max 2 decimal places)",
    )

    args = parser.parse_args()

    try:
        balanced, sum_debits, sum_credits, drift = verify_balance(args.debits, args.credits)
    except (InvalidOperation, ValueError) as exc:
        print(f"❌ INVALID INPUT: {exc}", file=sys.stderr)
        sys.exit(2)

    print(f"Total Debits:  {sum_debits.amount:.2f}")
    print(f"Total Credits: {sum_credits.amount:.2f}")
    print(f"Net Drift:     {drift.amount:.2f}")

    if balanced:
        print("✅ BALANCED: Double-entry conservation invariant holds (drift = 0.00).")
        sys.exit(0)
    else:
        print("❌ IMBALANCE DETECTED: Sum of debits does not equal sum of credits!")
        sys.exit(1)


if __name__ == "__main__":
    main()
