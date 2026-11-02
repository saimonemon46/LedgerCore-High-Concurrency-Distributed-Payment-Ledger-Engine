---
name: ledger-core-domain
description: >-
  Provides domain modeling rules, core entities, immutable value objects, double-entry
  financial invariants, canonical lock ordering (deadlock elimination), and state machine
  patterns for building financial ledgers. Use when generating, refactoring, or extending
  double-entry ledger code, transfer use cases, journal models, and payment state machines.
---

# Ledger Core Domain Engineering Skill

This skill guides AI agents and engineers in architecting and implementing double-entry financial ledgers, transactional payment engines, and journal accounting systems. It codifies the non-negotiable mathematical and concurrency rules necessary to prevent monetary loss, deadlocks, and audit drift.

---

## 1. The 4 Non-Negotiable Financial Invariants

Whenever you write, refactor, or review financial ledger code, you **must strictly enforce** these four rules:

### Invariant 1: Mathematical Conservation (Zero Drift)
- Every financial transaction must consist of balanced journal entries:
  $$\sum \text{Debits} = \sum \text{Credits} \quad \Longleftrightarrow \quad \sum \text{Signed Amounts} \equiv 0.00$$
- A debit without an equal and opposite credit (or vice versa) is a critical defect.
- Fees, platform cuts, taxes, and cashbacks must **never** be silently subtracted from transfer amounts. They must be explicit, balanced ledger entries crediting or debiting dedicated system/fee accounts.
- See detailed mathematical proofs in [references/01_financial_invariants.md](./references/01_financial_invariants.md).

### Invariant 2: Zero-Float Monetary Precision
- **NEVER** use IEEE-754 floating-point numbers (`float`, `double`, JavaScript `number`) for currency math or balances.
- In Python: Always use `decimal.Decimal` wrapped in an immutable Value Object (e.g. `Money`) with explicit rounding (e.g. `ROUND_HALF_UP` or `ROUND_HALF_EVEN`).
- In Database Storage: Always use `NUMERIC(18, 4)` or `NUMERIC(20, 2)`. Never `FLOAT` or `REAL`.
- Enforce currency isolation: Adding or subtracting amounts with different currencies (e.g., `USD` + `EUR`) must raise an explicit `CurrencyMismatchError`.

### Invariant 3: Canonical Monotonic Lock Ordering (Deadlock Elimination)
- When transferring funds between two or more accounts, **never** acquire locks in the arbitrary order accounts appear in the client request.
- **The Circular-Wait Deadlock Trap:**
  - Thread 1 transfers $A \to B$ (locks $A$, then waits for $B$).
  - Thread 2 transfers $B \to A$ (locks $B$, then waits for $A$).
  - Result: Postgres `40P01` deadlock or worker thread starvation.
- **The Monotonic Rule:** Always sort account identifiers lexicographically or numerically before acquiring row locks or mutexes:
  ```python
  # Always lock in canonical sorted order:
  first_id, second_id = sorted([from_account_id, to_account_id])
  async with lock(first_id):
      async with lock(second_id):
          # Mutate balances safely without deadlock risk
  ```
- See formal proof in [references/02_deadlock_elimination.md](./references/02_deadlock_elimination.md).

### Invariant 4: Atomic Idempotency & Immutable Journal
- Ledger entries are **strictly append-only**.
- **NEVER** run `UPDATE` or `DELETE` queries on posted ledger entries. Corrections must be handled via explicit reversing entries (contra-entries).
- Every mutating request must require a client-provided `idempotency_key` backed by a database unique constraint and payload hash fingerprinting.
- Use a deterministic finite state machine to govern transaction lifecycles:
  $$\text{INITIATED} \longrightarrow \text{LOCKED} \longrightarrow \text{COMMITTED} \longrightarrow \text{SETTLED}$$
- See transition rules in [references/03_state_machine_matrix.md](./references/03_state_machine_matrix.md).

---

## 2. Standard Code Generation Workflow for Agents

When requested to create double-entry ledger code:

### Step 1: Copy or Adapt Production Templates
Do not invent ledger patterns from scratch. Use the battle-tested templates bundled with this skill:
1. **Value Objects:** [templates/value_objects.py](./templates/value_objects.py) (`Money`, `Currency`)
2. **Domain Entities:** [templates/domain_models.py](./templates/domain_models.py) (`Account`, `LedgerEntry`, `Transaction`)
3. **State Machine:** [templates/state_machine.py](./templates/state_machine.py) (`TransactionStateMachine`)
4. **Transfer Engine:** [templates/transfer_engine.py](./templates/transfer_engine.py) (Canonical lock ordering & atomic transfer)
5. **Database Schema:** [templates/double_entry_schema.sql](./templates/double_entry_schema.sql) (PostgreSQL DDL)

### Step 2: Adhere to Clean / Hexagonal Architecture Boundaries
- **Zero I/O in the Domain Layer:** Keep domain models and value objects completely free of database drivers, ORM annotations, HTTP frameworks, or network calls.
- **Ports & Adapters:** Access repositories and unit-of-work exclusively through abstract interfaces (`abc.ABC`).

### Step 3: Run the Anti-Pattern Scanner
After writing or editing code, execute the static scanner:
```bash
python .agents/skills/ledger-core-domain/scripts/scan_antipatterns.py path/to/your/code.py
```
Ensure **zero warnings** for floats, unsorted locks, and mutable updates.

---

## 3. Quick Red-Flag Checklist

| Red Flag Pattern | Severity | Correct Pattern |
| :--- | :---: | :--- |
| `amount: float` or `balance = 100.50` | 🔴 **CRITICAL** | `amount: Decimal` or `Money(Decimal("100.50"), "USD")` |
| `SELECT ... FOR UPDATE` without sorting IDs | 🔴 **CRITICAL** | `for acc_id in sorted([src_id, dst_id]): lock(acc_id)` |
| `UPDATE ledger_entries SET amount = ...` | 🔴 **CRITICAL** | Append-only. Insert a new reversing entry. |
| Silently subtracting fees: `dst = src - fee` | 🔴 **CRITICAL** | Create 3 entries: debit src, credit fee_acc, credit dst. |
| Catching exceptions without rollback | 🔴 **CRITICAL** | Atomic transaction rollback; re-raise domain exception. |
| Missing `idempotency_key` | 🟡 **HIGH** | Require idempotency key with unique database constraint. |
