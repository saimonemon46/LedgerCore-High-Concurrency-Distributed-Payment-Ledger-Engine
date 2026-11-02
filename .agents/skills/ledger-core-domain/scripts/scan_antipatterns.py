#!/usr/bin/env python3
"""Fintech Static Anti-Pattern Scanner.

Zero-dependency static analysis tool to detect common financial engineering flaws:
- Floating-point currency usage (Python, TypeScript, Go, SQL).
- Unsorted / deadlock-prone row locks (SELECT FOR UPDATE).
- Mutating queries on immutable journal tables.
- Unrounded division on monetary values.

Outputs clean human-readable terminal reports or machine-readable JSON for AI agents.
"""

import argparse
import ast
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

FINANCIAL_KEYWORDS = {
    "amount",
    "balance",
    "price",
    "fee",
    "cost",
    "total",
    "subtotal",
    "debit",
    "credit",
    "principal",
    "money",
    "salary",
    "wage",
    "interest_rate",
    "tax_rate",
    "exchange_rate",
    "fx_rate",
}

NON_FINANCIAL_RATE_EXCLUSIONS = {
    "failure_threshold_rate",
    "sample_rate",
    "error_rate",
    "dropout_rate",
    "frame_rate",
    "refresh_rate",
    "success_rate",
    "hit_rate",
    "miss_rate",
}

IGNORE_DIRS = {
    ".git",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    "dist",
    "build",
    ".next",
    ".nuxt",
    "vendor",
}


class Finding:
    def __init__(
        self,
        file_path: str,
        line: int,
        rule_id: str,
        severity: str,
        message: str,
        code_snippet: str,
        remediation: str,
    ) -> None:
        self.file_path = file_path
        self.line = line
        self.rule_id = rule_id
        self.severity = severity
        self.message = message
        self.code_snippet = code_snippet.strip()
        self.remediation = remediation

    def to_dict(self) -> dict[str, Any]:
        return {
            "file": self.file_path,
            "line": self.line,
            "rule_id": self.rule_id,
            "severity": self.severity,
            "message": self.message,
            "code_snippet": self.code_snippet,
            "remediation": self.remediation,
        }


class PythonASTVisitor(ast.NodeVisitor):
    def __init__(self, file_path: str, lines: list[str]) -> None:
        self.file_path = file_path
        self.lines = lines
        self.findings: list[Finding] = []

    def _get_line_snippet(self, lineno: int) -> str:
        if 1 <= lineno <= len(self.lines):
            return self.lines[lineno - 1]
        return ""

    def _is_currency_name(self, name: str) -> bool:
        lower = name.lower()
        if any(ex in lower for ex in NON_FINANCIAL_RATE_EXCLUSIONS):
            return False
        return any(kw in lower for kw in FINANCIAL_KEYWORDS)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        target_name = ""
        if isinstance(node.target, ast.Name):
            target_name = node.target.id
        elif isinstance(node.target, ast.Attribute):
            target_name = node.target.attr

        if target_name and self._is_currency_name(target_name):
            type_str = ""
            if isinstance(node.annotation, ast.Name):
                type_str = node.annotation.id
            elif isinstance(node.annotation, ast.Constant):
                type_str = str(node.annotation.value)

            if type_str.lower() == "float":
                self.findings.append(
                    Finding(
                        file_path=self.file_path,
                        line=node.lineno,
                        rule_id="FIN-001-FLOAT-CURRENCY",
                        severity="CRITICAL",
                        message=f"Monetary field '{target_name}' is annotated as float.",
                        code_snippet=self._get_line_snippet(node.lineno),
                        remediation=(
                            "Use decimal.Decimal (or fixed-point integer cents) "
                            "with explicit precision."
                        ),
                    )
                )
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._check_function_args(node)
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._check_function_args(node)
        self.generic_visit(node)

    def _check_function_args(self, node: Any) -> None:
        for arg in node.args.args:
            if self._is_currency_name(arg.arg) and arg.annotation:
                type_str = ""
                if isinstance(arg.annotation, ast.Name):
                    type_str = arg.annotation.id
                if type_str.lower() == "float":
                    self.findings.append(
                        Finding(
                            file_path=self.file_path,
                            line=arg.lineno,
                            rule_id="FIN-001-FLOAT-CURRENCY",
                            severity="CRITICAL",
                            message=f"Monetary parameter '{arg.arg}' is typed as float.",
                            code_snippet=self._get_line_snippet(arg.lineno),
                            remediation="Replace float with Decimal or Money Value Object.",
                        )
                    )

    def visit_BinOp(self, node: ast.BinOp) -> None:
        if isinstance(node.op, ast.Div):
            var_name = ""
            if isinstance(node.left, ast.Name):
                var_name = node.left.id
            if var_name and self._is_currency_name(var_name):
                self.findings.append(
                    Finding(
                        file_path=self.file_path,
                        line=node.lineno,
                        rule_id="FIN-002-FLOAT-DIVISION",
                        severity="WARNING",
                        message=f"True division ('/') performed on currency variable '{var_name}'.",
                        code_snippet=self._get_line_snippet(node.lineno),
                        remediation=(
                            "Use Decimal division with explicit quantize(ROUND_HALF_EVEN) "
                            "to avoid float drift."
                        ),
                    )
                )
        self.generic_visit(node)


class CodebaseScanner:
    def __init__(self, root_dir: str) -> None:
        self.root_dir = Path(root_dir)
        self.findings: list[Finding] = []

    def scan(self) -> list[Finding]:
        if self.root_dir.is_file():
            self._scan_single_file(self.root_dir)
            return self.findings

        for root, dirs, files in os.walk(self.root_dir):
            dirs[:] = [d for d in dirs if d not in IGNORE_DIRS]
            for file in files:
                file_path = Path(root) / file
                self._scan_single_file(file_path)

        return self.findings

    def _scan_single_file(self, file_path: Path) -> None:
        ext = file_path.suffix.lower()
        rel_path = str(file_path)

        if ext == ".py":
            self._scan_python(file_path, rel_path)
        elif ext in [".ts", ".tsx", ".js", ".jsx"]:
            self._scan_javascript(file_path, rel_path)
        elif ext == ".go":
            self._scan_go(file_path, rel_path)
        elif ext == ".sql":
            self._scan_sql(file_path, rel_path)

    def _scan_python(self, path: Path, rel_path: str) -> None:
        try:
            content = path.read_text(encoding="utf-8", errors="ignore")
            lines = content.splitlines()
        except Exception:
            return

        try:
            tree = ast.parse(content, filename=str(path))
            visitor = PythonASTVisitor(rel_path, lines)
            visitor.visit(tree)
            self.findings.extend(visitor.findings)
        except SyntaxError:
            pass

        in_multiline_doc = False
        for i, line in enumerate(lines, start=1):
            stripped = line.strip()
            if '"""' in stripped or "'''" in stripped:
                if stripped.count('"""') % 2 != 0 or stripped.count("'''") % 2 != 0:
                    in_multiline_doc = not in_multiline_doc
                continue
            if in_multiline_doc:
                continue

            if (
                stripped.startswith("#")
                or stripped.startswith("//")
                or stripped.startswith("/*")
                or stripped.startswith("*")
            ):
                continue

            lower = line.lower()
            if any(ex in lower for ex in NON_FINANCIAL_RATE_EXCLUSIONS):
                continue

            if any(kw in lower for kw in FINANCIAL_KEYWORDS):
                if re.search(r"\b(Float|FloatField|Column\s*\(\s*Float)\b", line):
                    self.findings.append(
                        Finding(
                            file_path=rel_path,
                            line=i,
                            rule_id="FIN-003-ORM-FLOAT-COLUMN",
                            severity="CRITICAL",
                            message="Database model defines currency column with float type.",
                            code_snippet=line,
                            remediation="Use Numeric(18, 4) or Integer (representing cents).",
                        )
                    )

            if ("with_for_update" in line or "for update" in lower) and "skip_locked" not in lower:
                sorting_hints = ["sorted", "order_by", "order by", "canonical", "min("]
                if not any(k in lower for k in sorting_hints):
                    self.findings.append(
                        Finding(
                            file_path=rel_path,
                            line=i,
                            rule_id="FIN-004-UNORDERED-LOCK",
                            severity="WARNING",
                            message="Row lock (for_update) without evident canonical sorting.",
                            code_snippet=line,
                            remediation=(
                                "Ensure multiple accounts are locked in deterministic order: "
                                "sorted([acc_a, acc_b])."
                            ),
                        )
                    )

    def _scan_javascript(self, path: Path, rel_path: str) -> None:
        try:
            lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
        except Exception:
            return

        for i, line in enumerate(lines, start=1):
            stripped = line.strip()
            if stripped.startswith("//") or stripped.startswith("/*") or stripped.startswith("*"):
                continue
            lower = line.lower()
            if any(kw in lower for kw in FINANCIAL_KEYWORDS):
                if re.search(r":\s*number\b", line):
                    self.findings.append(
                        Finding(
                            file_path=rel_path,
                            line=i,
                            rule_id="FIN-005-TS-NUMBER-CURRENCY",
                            severity="CRITICAL",
                            message="Monetary property typed as JS 'number' (IEEE-754 float).",
                            code_snippet=line,
                            remediation=(
                                "Use BigNumber, Decimal, or BigInt cents to prevent float drift."
                            ),
                        )
                    )
                if re.search(r"@db\.Float|Float\b", line):
                    self.findings.append(
                        Finding(
                            file_path=rel_path,
                            line=i,
                            rule_id="FIN-003-ORM-FLOAT-COLUMN",
                            severity="CRITICAL",
                            message="Prisma schema defines currency field as Float.",
                            code_snippet=line,
                            remediation="Use Decimal @db.Decimal(18, 4) or Int in cents.",
                        )
                    )

    def _scan_go(self, path: Path, rel_path: str) -> None:
        try:
            lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
        except Exception:
            return

        for i, line in enumerate(lines, start=1):
            stripped = line.strip()
            if stripped.startswith("//") or stripped.startswith("/*") or stripped.startswith("*"):
                continue
            lower = line.lower()
            if any(kw in lower for kw in FINANCIAL_KEYWORDS):
                if re.search(r"\b(float32|float64)\b", line):
                    self.findings.append(
                        Finding(
                            file_path=rel_path,
                            line=i,
                            rule_id="FIN-006-GO-FLOAT-CURRENCY",
                            severity="CRITICAL",
                            message="Go monetary field or variable typed as float32/float64.",
                            code_snippet=line,
                            remediation="Use shopspring/decimal or int64 minor currency units.",
                        )
                    )

    def _scan_sql(self, path: Path, rel_path: str) -> None:
        try:
            content = path.read_text(encoding="utf-8", errors="ignore")
            lines = content.splitlines()
        except Exception:
            return

        for i, line in enumerate(lines, start=1):
            stripped = line.strip()
            if stripped.startswith("--") or stripped.startswith("/*") or stripped.startswith("*"):
                continue
            lower = line.lower()
            if any(kw in lower for kw in FINANCIAL_KEYWORDS):
                if re.search(r"\b(float|real|double\s+precision)\b", lower):
                    self.findings.append(
                        Finding(
                            file_path=rel_path,
                            line=i,
                            rule_id="FIN-007-SQL-FLOAT-TYPE",
                            severity="CRITICAL",
                            message="SQL table uses floating-point type for monetary column.",
                            code_snippet=line,
                            remediation="Use NUMERIC(18, 4) or BIGINT cents.",
                        )
                    )

            if re.search(
                r"\b(update|delete\s+from)\s+(journal_entries|ledger_entries|transactions)\b",
                lower,
            ):
                self.findings.append(
                    Finding(
                        file_path=rel_path,
                        line=i,
                        rule_id="FIN-008-MUTABLE-JOURNAL",
                        severity="CRITICAL",
                        message="UPDATE or DELETE query detected targeting immutable ledger.",
                        code_snippet=line,
                        remediation=(
                            "Double-entry records are append-only. "
                            "Implement explicit reversal entries."
                        ),
                    )
                )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Scan codebases for critical fintech & double-entry anti-patterns."
    )
    parser.add_argument(
        "path",
        nargs="?",
        default=".",
        help="Target directory to scan (default: current directory)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON for programmatic consumption",
    )

    args = parser.parse_args()
    target_dir = os.path.abspath(args.path)

    scanner = CodebaseScanner(target_dir)
    findings = scanner.scan()

    if args.json:
        data = {
            "scanned_directory": target_dir,
            "total_findings": len(findings),
            "critical_count": sum(1 for f in findings if f.severity == "CRITICAL"),
            "warning_count": sum(1 for f in findings if f.severity == "WARNING"),
            "findings": [f.to_dict() for f in findings],
        }
        print(json.dumps(data, indent=2))
    else:
        print("=" * 70)
        print("  FINTECH & DOUBLE-ENTRY INVARIANT STATIC SCANNER")
        print("=" * 70)
        print(f"Target Directory: {target_dir}")
        print(f"Total Findings:   {len(findings)}")
        print("-" * 70)

        if not findings:
            print("✅ ZERO anti-patterns detected! Clean fintech hygiene.")
            sys.exit(0)

        criticals = [f for f in findings if f.severity == "CRITICAL"]
        warnings = [f for f in findings if f.severity == "WARNING"]

        print(f"🔴 Critical Invariant Violations: {len(criticals)}")
        print(f"🟡 Warnings / Potential Hazards:  {len(warnings)}")
        print("-" * 70)

        for f in findings:
            color_tag = "🔴 [CRITICAL]" if f.severity == "CRITICAL" else "🟡 [WARNING]"
            print(f"\n{color_tag} {f.rule_id} at {f.file_path}:{f.line}")
            print(f"  Message:     {f.message}")
            print(f"  Code:        {f.code_snippet}")
            print(f"  Remediation: {f.remediation}")

        print("\n" + "=" * 70)

    sys.exit(1 if any(f.severity == "CRITICAL" for f in findings) else 0)


if __name__ == "__main__":
    main()
