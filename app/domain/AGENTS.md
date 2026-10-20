# Domain Layer Constraints (`app/domain/`)

This directory contains pure enterprise domain entities, value objects, and business invariants for LedgerCore.

## Core Rules for `app/domain/`
1. **Zero I/O Policy:** No database connections, HTTP calls, filesystem access, or external network calls allowed.
2. **Zero Outer-Layer Dependencies:** Never import from `app.infrastructure`, `app.api`, `app.ports`, or third-party web frameworks (e.g. FastAPI, SQLAlchemy).
3. **Immutability:** Value objects such as `Money` and `Currency` must be frozen/immutable dataclasses.
4. **Precision:** All monetary arithmetic must use Python's `decimal.Decimal`. Floating-point numbers are strictly forbidden.
5. **Conservation Invariant:** Domain entities representing double-entry journal entries must mathematically balance ($\sum \text{Debits} == \sum \text{Credits}$).
