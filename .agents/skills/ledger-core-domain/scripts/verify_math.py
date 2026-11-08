#!/usr/bin/env python3
"""Double-entry balance verification script.

Accepts lists of debit and credit amounts, parses them into exact Decimal values,
and verifies mathematical zero-drift conservation.
"""

import argparse
import sys
from decimal import (
    MAX_EMAX,
    MAX_PREC,
    MIN_EMIN,
    Context,
    Decimal,
    InvalidOperation,
    localcontext,
)

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


def verify_balance(debits: list[str], credits: list[str]) -> tuple[bool, Decimal, Decimal, Decimal]:
    dec_debits = _parse(debits)
    dec_credits = _parse(credits)

    # Require credits to follow standard non-negative credit convention
    for c in dec_credits:
        if c < Decimal("0.00"):
            raise InvalidOperation(f"credit amounts must be positive: {c}")

    # Debits can be provided either as signed negative entries (-100.00)
    # or unsigned magnitudes (100.00)
    # Calculate sums and drift under full precision context to prevent false zero-drift
    with localcontext(Context(prec=MAX_PREC, Emax=MAX_EMAX, Emin=MIN_EMIN)):
        sum_debits = sum((abs(d) for d in dec_debits), Decimal("0.00"))
        sum_credits = sum(dec_credits, Decimal("0.00"))
        drift = sum_debits - sum_credits
        balanced = (drift == Decimal("0.00"))

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

    print(f"Total Debits:  {sum_debits:.2f}")
    print(f"Total Credits: {sum_credits:.2f}")
    print(f"Net Drift:     {drift:.2f}")

    if balanced:
        print("✅ BALANCED: Double-entry conservation invariant holds (drift = 0.00).")
        sys.exit(0)
    else:
        print("❌ IMBALANCE DETECTED: Sum of debits does not equal sum of credits!")
        sys.exit(1)


if __name__ == "__main__":
    main()
