# Financial Invariants & Double-Entry Mathematical Conservation

This reference guide establishes the mathematical theorems and numerical representations required for zero-drift financial engineering.

---

## 1. The Fundamental Equation of Double-Entry Bookkeeping

In double-entry bookkeeping, wealth is never created or destroyed; it is merely transferred between accounts. Every transaction must preserve the master accounting equation:

$$\text{Assets} = \text{Liabilities} + \text{Equity}$$

Expanded to accommodate operational income:

$$\text{Assets} + \text{Expenses} = \text{Liabilities} + \text{Equity} + \text{Revenue}$$

### Debit vs. Credit Conventions
- **Debits (Dr):** Increase Assets and Expenses; Decrease Liabilities, Equity, and Revenue.
- **Credits (Cr):** Increase Liabilities, Equity, and Revenue; Decrease Assets and Expenses.

### The Zero-Drift Conservation Theorem
In automated ledger systems, entries are assigned signed numbers:
- $\text{Debits} < 0$ (or unsigned $\text{Debit}$)
- $\text{Credits} > 0$ (or unsigned $\text{Credit}$)

For any valid transaction $T$ composed of entries $e_1, e_2, \dots, e_n$:

$$\sum_{i=1}^{n} \text{amount}(e_i) \equiv 0.00$$

If this sum evaluates to anything other than zero, the transaction is **mathematically defective** and must be aborted immediately before database persistence.

---

## 2. The Floating-Point Trap (IEEE-754)

### The Catastrophic Defect
Computers represent IEEE-754 floating-point numbers in base 2. In base 2, fractions like $0.1$ ($1/10$) and $0.2$ ($1/5$) are repeating infinite decimals, just as $1/3$ is in base 10:

```python
>>> 0.1 + 0.2
0.30000000000000004
>>> 0.1 + 0.2 == 0.3
False
```

### Cumulative Drift in High-Throughput Engines
When executing 10,000,000 transfers per day, infinitesimal errors of $0.00000000000000004$ accumulate into hundreds or thousands of dollars of unreconciled phantom money. In banking and fintech audits, this results in regulatory fines and license revocation.

### Mandatory Standards
1. **Always use Arbitrary-Precision Decimals:**
   - Python: `from decimal import Decimal`
   - SQL: `NUMERIC(18, 4)` or `NUMERIC(20, 2)`
   - Go: `shopspring/decimal`
2. **Explicit Rounding Modes:**
   - Standard Commercial: `ROUND_HALF_UP` (5 rounds away from zero).
   - High-Volume Financial: `ROUND_HALF_EVEN` (Banker's Rounding, rounds towards the nearest even number to prevent statistical upward drift).

---

## 3. Platform Fees and Intermediary Deductions

A frequent junior error is silently deducting platform fees:
```python
# BROKEN ANTI-PATTERN:
sender.balance -= (amount + fee)
receiver.balance += amount
# Where did the fee go? The ledger is out of balance by 'fee'!
```

### The Correct Three-Entry Pattern
Every fee must be explicitly recorded with a matching credit to a platform revenue/clearing account:
1. **Entry 1 (Debit Sender):** `-$105.00`
2. **Entry 2 (Credit Receiver):** `+$100.00`
3. **Entry 3 (Credit Platform Fee Account):** `+$5.00`

$$\text{Net Sum} = (-105.00) + (+100.00) + (+5.00) \equiv 0.00$$
The ledger balances perfectly, and the fee is fully auditable.
