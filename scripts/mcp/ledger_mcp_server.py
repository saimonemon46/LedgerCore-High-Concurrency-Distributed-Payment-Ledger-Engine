#!/usr/bin/env python3
"""LedgerCore Model Context Protocol (MCP) Server.

Communicates over stdio using JSON-RPC 2.0 to expose ledger verification,
database health, and balance conservation tools to AI agents.
"""

import json
import os
import subprocess
import sys
from decimal import (
    MAX_EMAX,
    MAX_PREC,
    MIN_EMIN,
    Context,
    Decimal,
    localcontext,
)
from typing import Any


def log(msg: str) -> None:
    sys.stderr.write(f"[ledger-mcp] {msg}\n")
    sys.stderr.flush()


def send_response(response: dict[str, Any]) -> None:
    data = json.dumps(response)
    sys.stdout.write(f"{data}\n")
    sys.stdout.flush()


TOOLS: list[dict[str, Any]] = [
    {
        "name": "verify_balance_math",
        "description": (
            "Verify double-entry balance: ensures sum of debits strictly equals "
            "sum of credits with 2-decimal precision."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "debits": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of debit amounts as strings (e.g. ['100.00', '2.50'])",
                },
                "credits": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of credit amounts as strings (e.g. ['102.50'])",
                },
            },
            "required": ["debits", "credits"],
        },
    },
    {
        "name": "run_domain_invariant_tests",
        "description": (
            "Runs pytest unit tests covering domain money, journal entries, "
            "and mathematical conservation."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
]


def handle_initialize(request_id: Any) -> None:
    send_response({
        "jsonrpc": "2.0",
        "id": request_id,
        "result": {
            "protocolVersion": "2024-11-05",
            "capabilities": {
                "tools": {}
            },
            "serverInfo": {
                "name": "ledger-core-mcp",
                "version": "1.0.0"
            }
        }
    })


def handle_tools_list(request_id: Any) -> None:
    send_response({
        "jsonrpc": "2.0",
        "id": request_id,
        "result": {
            "tools": TOOLS
        }
    })


MAX_ADJUSTED_EXPONENT = 30


def tool_verify_balance_math(args: dict[str, Any]) -> str:
    try:
        raw_debits = args.get("debits", [])
        raw_credits = args.get("credits", [])

        debits = []
        for x in raw_debits:
            d = Decimal(str(x))
            if not d.is_finite():
                return f"Invalid decimal input: non-finite amount '{x}'"
            if d.adjusted() > MAX_ADJUSTED_EXPONENT:
                return f"Invalid decimal input: amount too large '{x}'"
            if isinstance(d.as_tuple().exponent, int) and d.as_tuple().exponent < -2:
                return f"Invalid decimal input: excess decimal scale (max 2 allowed) '{x}'"
            debits.append(d)

        credits = []
        for x in raw_credits:
            c = Decimal(str(x))
            if not c.is_finite():
                return f"Invalid decimal input: non-finite amount '{x}'"
            if c.adjusted() > MAX_ADJUSTED_EXPONENT:
                return f"Invalid decimal input: amount too large '{x}'"
            if isinstance(c.as_tuple().exponent, int) and c.as_tuple().exponent < -2:
                return f"Invalid decimal input: excess decimal scale (max 2 allowed) '{x}'"
            if c < Decimal("0.00"):
                return f"Invalid decimal input: credit amounts must be positive '{x}'"
            credits.append(c)

        with localcontext(Context(prec=MAX_PREC, Emax=MAX_EMAX, Emin=MIN_EMIN)):
            sum_debits = sum((abs(d) for d in debits), Decimal("0.00"))
            sum_credits = sum(credits, Decimal("0.00"))
            drift = sum_debits - sum_credits
            balanced = (drift == Decimal("0.00"))

        return (
            f"Sum Debits: {sum_debits:.2f}\n"
            f"Sum Credits: {sum_credits:.2f}\n"
            f"Drift: {drift:.2f}\n"
            f"Balanced: {'YES (Double-entry invariant holds)' if balanced else 'NO (VIOLATION)'}"
        )
    except Exception as e:
        return f"Invalid decimal input: {e}"


def tool_run_domain_tests() -> str:
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
    pytest_bin = os.path.join(project_root, ".venv/bin/pytest")
    if not os.path.exists(pytest_bin):
        pytest_bin = "pytest"

    try:
        res = subprocess.run(
            [pytest_bin, "tests/test_domain_invariants.py", "-q"],
            cwd=project_root,
            capture_output=True,
            text=True,
            timeout=30
        )
        return f"Exit Code: {res.returncode}\nOutput:\n{res.stdout}\n{res.stderr}"
    except Exception as e:
        return f"Error running tests: {e}"


def handle_tools_call(request_id: Any, params: dict[str, Any]) -> None:
    name = params.get("name")
    args = params.get("arguments", {})

    if name == "verify_balance_math":
        output = tool_verify_balance_math(args)
    elif name == "run_domain_invariant_tests":
        output = tool_run_domain_tests()
    else:
        output = f"Unknown tool: {name}"

    send_response({
        "jsonrpc": "2.0",
        "id": request_id,
        "result": {
            "content": [
                {
                    "type": "text",
                    "text": output
                }
            ]
        }
    })


def main() -> None:
    log("LedgerCore MCP Server started (stdio transport)")
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except Exception as e:
            log(f"Failed to parse JSON: {e}")
            continue

        method = req.get("method")
        req_id = req.get("id")

        if method == "initialize":
            handle_initialize(req_id)
        elif method == "notifications/initialized":
            log("Client acknowledged initialization")
        elif method == "tools/list":
            handle_tools_list(req_id)
        elif method == "tools/call":
            handle_tools_call(req_id, req.get("params", {}))
        elif req_id is not None:
            send_response({
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {
                    "code": -32601,
                    "message": f"Method not found: {method}"
                }
            })


if __name__ == "__main__":
    main()
