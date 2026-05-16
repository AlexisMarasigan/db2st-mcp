#!/usr/bin/env python3
"""sync-domain — propose DOMAIN.md updates for a given domain.

Read-only — emits a Markdown proposal for the human to accept or reject;
never writes the file. Pair with `.claude/skills/sync-domain` for the
in-editor flow; this is the underlying command.

Usage:
    uv run python scripts/sync_domain.py <name>      # single domain
    uv run python scripts/sync_domain.py --all       # every domain

Output sections per domain:
- New public-surface symbols (exported but not in DOMAIN.md).
- Removed public-surface entries (in DOMAIN.md but no longer exported).
- Cross-domain imports that aren't yet documented as dependencies.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SRC = REPO / "src" / "db2st_mcp"
DOMAINS_ROOT = SRC / "domains"


def _exported(init_path: Path) -> list[str]:
    if not init_path.is_file():
        return []
    try:
        tree = ast.parse(init_path.read_text(encoding="utf-8"))
    except SyntaxError:
        return []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and node.targets[0].id == "__all__"
            and isinstance(node.value, ast.List | ast.Tuple)
        ):
            return [
                elt.value
                for elt in node.value.elts
                if isinstance(elt, ast.Constant) and isinstance(elt.value, str)
            ]
    return []


def _imports(path: Path) -> list[str]:
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


def proposal_for(domain: str) -> str:
    """Return a Markdown proposal block for one domain."""
    domain_dir = DOMAINS_ROOT / domain
    if not domain_dir.is_dir():
        return f"## {domain}\nDomain directory not found at {domain_dir.relative_to(REPO)}.\n"
    doc_path = domain_dir / "DOMAIN.md"
    doc = doc_path.read_text(encoding="utf-8") if doc_path.exists() else ""

    sections: list[str] = [f"## {domain}"]

    # 1. Public-surface drift.
    surfaces: list[tuple[str, list[str]]] = []
    for sub in ("shared", "server", "client"):
        init = domain_dir / sub / "__init__.py"
        if init.exists():
            surfaces.append((sub, _exported(init)))

    new_symbols: list[tuple[str, str]] = []
    for sub, symbols in surfaces:
        for s in symbols:
            if s and s not in doc:
                new_symbols.append((sub, s))

    if new_symbols:
        sections.append("**Add to Public surface:**")
        for sub, s in new_symbols:
            sections.append(f"- `{s}` (exported from `{sub}/__init__.py`)")
    else:
        sections.append("Public surface: in sync.")

    # 2. Cross-domain dependencies.
    cross: set[str] = set()
    for py in domain_dir.rglob("*.py"):
        for mod in _imports(py):
            if mod.startswith("db2st_mcp.domains."):
                other = mod.split(".")[2]
                if other != domain:
                    cross.add(other)

    undocumented = [d for d in sorted(cross) if d not in doc]
    if undocumented:
        sections.append("")
        sections.append("**Add to Dependencies on other domains:**")
        for d in undocumented:
            sections.append(f"- depends on `{d}`")
    elif cross:
        sections.append("")
        sections.append(f"Cross-domain deps documented: {', '.join(sorted(cross))}")
    else:
        sections.append("")
        sections.append("Cross-domain deps: none.")

    return "\n".join(sections) + "\n"


def run(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    if not args:
        print("usage: sync_domain.py <name> | --all", file=sys.stderr)
        return 2

    if args[0] == "--all":
        targets = sorted(
            d.name for d in DOMAINS_ROOT.iterdir() if d.is_dir() and not d.name.startswith("_")
        )
    else:
        targets = [args[0]]

    if not targets:
        print(f"no domains found under {DOMAINS_ROOT.relative_to(REPO)}", file=sys.stderr)
        return 1

    print(f"# sync-domain proposals — {len(targets)} domain(s)")
    print()
    for t in targets:
        print(proposal_for(t))
    print("---")
    print("Proposals only. No files were modified.")
    return 0


if __name__ == "__main__":
    sys.exit(run())
