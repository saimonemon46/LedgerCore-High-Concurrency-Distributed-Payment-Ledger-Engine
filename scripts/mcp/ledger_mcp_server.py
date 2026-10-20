#!/usr/bin/env python3
"""LedgerCore Model Context Protocol (MCP) Server.

Communicates over stdio using JSON-RPC 2.0 to expose ledger verification,
database health, and balance conservation tools to AI agents.
"""

from decimal import Decimal
import json
import os
import subprocess
import sys
from typing import Any, Dict, List


def log(msg: str) -> None:
    sys.stderr.write(f"[ledger-mcp] {msg}\n")
    sys.stderr.flush()


def send_response(response: Dict[str, Any]) -> None:
    data = json.dumps(response)
    sys.stdout.write(f"{data}\n")
    sys.stdout.flush()


TOOLS: List[Dict[str, Any]] = [
    {
        "name": "verify_balance_math",
        "description": "Verify double-entry balance: ensures sum of debits strictly equals sum of credits with 2-decimal precision.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "debits": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of debit amounts as strings (e.g. ['100.00', '2.50'])"
                },
                "credits": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of credit amounts as strings (e.g. ['102.50'])"
                }
            },
            "required": ["debits", "credits"]
        }
    },
    {
        "name": "run_domain_invariant_tests",
        "description": "Runs pytest unit tests covering domain money, journal entries, and mathematical conservation.",
        "inputSchema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    }
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


def tool_verify_balance_math(args: Dict[str, Any]) -> str:
    try:
        debits = [Decimal(str(x)) for x in args.get("debits", [])]
        credits = [Decimal(str(x)) for x in args.get("credits", [])]
    except Exception as e:
        return f"Invalid decimal input: {e}"

    sum_debits = sum(debits, Decimal("0.00"))
    sum_credits = sum(credits, Decimal("0.00"))
    balanced = (sum_debits == sum_credits)

    return (
        f"Sum Debits: {sum_debits}\n"
        f"Sum Credits: {sum_credits}\n"
        f"Drift: {sum_debits - sum_credits}\n"
        f"Balanced: {'YES (Double-entry invariant holds)' if balanced else 'NO (VIOLATION)'}"
    )


def tool_run_domain_tests() -> str:
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
    pytest_bin = os.path.join(project_root, ".venv/bin/pytest")
    if not os.path.exists(pytest_bin):
        pytest_bin = "pytest"

    try:
        res = subprocess.run(
            [pytest_bin, "tests/unit/domain/", "-q"],
            cwd=project_root,
            capture_output=True,
            text=True,
            timeout=30
        )
        return f"Exit Code: {res.returncode}\nOutput:\n{res.stdout}\n{res.stderr}"
    except Exception as e:
        return f"Error running tests: {e}"


def handle_tools_call(request_id: Any, params: Dict[str, Any]) -> None:
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
