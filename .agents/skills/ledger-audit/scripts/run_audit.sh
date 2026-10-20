#!/usr/bin/env bash
set -euo pipefail

# LedgerCore Automated Audit and Invariant Verification Script
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
cd "$PROJECT_ROOT"

echo "=== Running Ledger Invariant Unit Tests ==="
"${PROJECT_ROOT}/.venv/bin/pytest" tests/unit/domain/ -q

echo "=== Running Phase 1 Invariant Audit ==="
"${PROJECT_ROOT}/.venv/bin/python" scripts/verify_phase1.py || true

echo "=== Audit Completed ==="
