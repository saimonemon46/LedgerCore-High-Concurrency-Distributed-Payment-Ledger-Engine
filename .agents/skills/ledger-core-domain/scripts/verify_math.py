#!/usr/bin/env python3
"""Double-entry balance verification script.

Accepts lists of debit and credit amounts, parses them into exact Decimal values,
and verifies mathematical zero-drift conservation.
"""

import argparse
import sys
from decimal import Decimal


def verify_balance(debits: list[str], credits: list[str]) -> tuple[bool, Decimal, Decimal, Decimal]:
    dec_debits = [Decimal(str(d)) for d in debits]
    dec_credits = [Decimal(str(c)) for c in credits]

    sum_debits = sum(dec_debits, Decimal("0.00"))
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
        help="List of debit amounts (e.g. 100.00 5.00)",
    )
    parser.add_argument(
        "--credits",
        nargs="+",
        required=True,
        help="List of credit amounts (e.g. 105.00)",
    )

    args = parser.parse_args()

    balanced, sum_debits, sum_credits, drift = verify_balance(args.debits, args.credits)

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
