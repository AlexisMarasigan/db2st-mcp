#!/usr/bin/env python3
"""verify-docs — check DOMAIN.md / APP.md / ARCHITECTURE.md against the code.

Read-only. Emits a report grouped by file. Exit code 1 if any CRITICAL
finding is present, else 0. Pair with the `.claude/skills/verify-docs`
project skill for in-editor invocation; this script is what CI runs.

Checks (see .claude/skills/verify-docs/SKILL.md for the full spec):
1. Clara invariant — `db2st_mcp.shared.*` does not import from
   `db2st_mcp.domains.*` or `db2st_mcp.apps.*`.
2. Doc length caps:
   - ARCHITECTURE.md <= 220 lines
   - APP.md <= 220 lines
   - DOMAIN.md <= 440 lines
3. Decision Log section present in every committed doc.
4. Cross-domain imports are documented in the importer's DOMAIN.md
   under "Dependencies on other domains".
"""

from __future__ import annotations

import ast
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

REPO = Path(__file__).resolve().parent.parent
SRC = REPO / "src" / "db2st_mcp"

Severity = Literal["CRITICAL", "WARNING", "INFO"]


@dataclass(frozen=True)
class Finding:
    file: str
    severity: Severity
    message: str


# --- Clara invariants --------------------------------------------------------


def _imports(path: Path) -> list[str]:
    """Return every imported module path inside `path`."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (SyntaxError, OSError):
        return []
    out: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            out.extend(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            out.append(node.module)
    return out


def check_shared_one_way() -> list[Finding]:
    """`db2st_mcp.shared.*` must not import from domains or apps."""
    findings: list[Finding] = []
    shared_root = SRC / "shared"
    for py in shared_root.rglob("*.py"):
        for mod in _imports(py):
            if mod.startswith(("db2st_mcp.domains", "db2st_mcp.apps")):
                findings.append(
                    Finding(
                        file=str(py.relative_to(REPO)),
                        severity="CRITICAL",
                        message=f"shared/ imports forbidden module '{mod}' — Clara one-way rule violated",
                    )
                )
    return findings


def check_cross_domain_imports() -> list[Finding]:
    """Cross-domain imports must be documented in the importer's DOMAIN.md.

    A cross-domain import is any `from db2st_mcp.domains.<other> import ...`
    inside `db2st_mcp.domains.<self>/`. We don't enforce *direction*
    (planner job), only that the dependency is named in the doc.
    """
    findings: list[Finding] = []
    domains_root = SRC / "domains"
    if not domains_root.is_dir():
        return findings

    for domain_dir in domains_root.iterdir():
        if not domain_dir.is_dir():
            continue
        domain_md = domain_dir / "DOMAIN.md"
        doc_text = domain_md.read_text(encoding="utf-8") if domain_md.exists() else ""
        for py in domain_dir.rglob("*.py"):
            for mod in _imports(py):
                if not mod.startswith("db2st_mcp.domains."):
                    continue
                other = mod.split(".")[2]
                if other == domain_dir.name:
                    continue
                if other not in doc_text:
                    findings.append(
                        Finding(
                            file=str(py.relative_to(REPO)),
                            severity="WARNING",
                            message=(
                                f"domain '{domain_dir.name}' imports from '{other}' "
                                f"but '{other}' is not mentioned in {domain_md.relative_to(REPO)}"
                            ),
                        )
                    )
    return findings


# --- Length caps -------------------------------------------------------------


LENGTH_CAPS = {
    "ARCHITECTURE.md": 220,
    "APP.md": 220,
    "DOMAIN.md": 440,
}


def check_doc_lengths() -> list[Finding]:
    findings: list[Finding] = []
    for doc in REPO.rglob("*.md"):
        cap = LENGTH_CAPS.get(doc.name)
        if cap is None:
            continue
        lines = doc.read_text(encoding="utf-8").splitlines()
        if len(lines) > cap:
            findings.append(
                Finding(
                    file=str(doc.relative_to(REPO)),
                    severity="WARNING",
                    message=f"{doc.name} is {len(lines)} lines, exceeds cap of {cap}",
                )
            )
    return findings


# --- Decision Log presence ---------------------------------------------------


def check_decision_logs() -> list[Finding]:
    findings: list[Finding] = []
    targets = [*list(LENGTH_CAPS), "CLAUDE.md"]
    for doc in REPO.rglob("*.md"):
        if doc.name not in targets:
            continue
        text = doc.read_text(encoding="utf-8")
        if "## Decision Log" not in text and "# Decision Log" not in text:
            findings.append(
                Finding(
                    file=str(doc.relative_to(REPO)),
                    severity="INFO",
                    message=f"{doc.name} is missing a Decision Log section",
                )
            )
    return findings


# --- Runner ------------------------------------------------------------------


def run() -> int:
    findings = (
        check_shared_one_way()
        + check_cross_domain_imports()
        + check_doc_lengths()
        + check_decision_logs()
    )

    # Group by file
    by_file: dict[str, list[Finding]] = {}
    for f in findings:
        by_file.setdefault(f.file, []).append(f)

    print(f"# verify-docs report — {len(findings)} finding(s)")
    print()
    if not findings:
        print("All checks passed.")
        return 0

    for file in sorted(by_file):
        print(f"## {file}")
        for f in by_file[file]:
            sigil = {"CRITICAL": "🔴", "WARNING": "⚠", "INFO": "✏"}[f.severity]
            print(f"- {sigil} {f.severity}: {f.message}")
        print()

    criticals = sum(1 for f in findings if f.severity == "CRITICAL")
    warnings = sum(1 for f in findings if f.severity == "WARNING")
    print("## Summary")
    print(f"- Criticals: {criticals}")
    print(f"- Warnings:  {warnings}")
    print(f"- Info:      {len(findings) - criticals - warnings}")
    return 1 if criticals > 0 else 0


if __name__ == "__main__":
    sys.exit(run())
