# AGENTS.md — LedgerCore Development Guidelines

## Project Overview & Architecture
LedgerCore is a high-concurrency, distributed financial payment & double-entry ledger engine built with **Clean / Hexagonal Architecture** (Python 3.12, FastAPI, PostgreSQL, Redis).

For in-depth architectural patterns, see [docs/architecture.md](file:///home/saimon/Emon_work/project/ledger_core/docs/architecture.md).

```
app/
├── domain/            # Pure business entities, Money VO, state machine, zero I/O
├── ports/             # Abstract interfaces (Repositories, UnitOfWork, Cache, Idempotency)
├── application/       # Use cases (Transfers, Balance, Audit) & Decorators
├── infrastructure/    # Adapters (PostgreSQL asyncpg/SQLAlchemy, Lock Manager, Cache, Workers)
└── api/               # FastAPI routes, schemas, and DI container
```

## Important File Paths
- **API Entrypoint:** [app/api/main.py](file:///home/saimon/Emon_work/project/ledger_core/app/api/main.py)
- **Dependency Container:** [app/api/dependencies.py](file:///home/saimon/Emon_work/project/ledger_core/app/api/dependencies.py)
- **Domain Models & Invariants:** [app/domain/models.py](file:///home/saimon/Emon_work/project/ledger_core/app/domain/models.py), [app/domain/value_objects.py](file:///home/saimon/Emon_work/project/ledger_core/app/domain/value_objects.py)
- **Use Cases:** [app/application/use_cases/](file:///home/saimon/Emon_work/project/ledger_core/app/application/use_cases/)
- **Postgres Persistence & UoW:** [app/infrastructure/persistence/postgres/](file:///home/saimon/Emon_work/project/ledger_core/app/infrastructure/persistence/postgres/)
- **Concurrency & Lock Manager:** [app/infrastructure/concurrency/lock_manager.py](file:///home/saimon/Emon_work/project/ledger_core/app/infrastructure/concurrency/lock_manager.py)
- **Application Config:** [app/infrastructure/config.py](file:///home/saimon/Emon_work/project/ledger_core/app/infrastructure/config.py)
- **Test Suite:** [tests/](file:///home/saimon/Emon_work/project/ledger_core/tests/)

## Development Commands
```bash
# Activate virtual environment
source .venv/bin/activate

# Run FastAPI development server
uvicorn app.api.main:create_app --factory --reload --port 8000

# Run full stack with Docker Compose
docker compose up --build

# Run concurrency benchmarks & verification scripts
python scripts/run_benchmarks.py
python scripts/verify_phase1.py
python scripts/verify_phase2.py
```

## Testing & Quality Assurance Commands
```bash
# Run complete test suite (149 tests)
pytest

# Run tests with coverage report
pytest --cov=app --cov-report=term-missing

# Run linter
ruff check .

# Run static type checker (strict mode)
mypy app
```

## Core Engineering Conventions & Invariants
1. **Mathematical Conservation:** Every transfer strictly enforces double-entry balance ($\sum \text{Debits} + \sum \text{Credits} = 0$).
2. **Financial Precision:** Never use floats for currency amounts. All monetary arithmetic must use the immutable `Money` Value Object backed by `decimal.Decimal` with 2-decimal precision.
3. **Deadlock Elimination:** Locks on multiple accounts must always be acquired in canonical monotonic sort order by Account ID (`min(src, dest)` before `max(src, dest)`).
4. **Clean Architecture Boundary:**
   - Domain layer has ZERO dependencies on outer layers (no database, no HTTP, no external frameworks).
   - Application layer depends only on domain and ports.
   - External dependencies are adapted via ports.
5. **Strict Typing:** All function signatures and return types must be fully annotated; code must pass `mypy --strict`.
