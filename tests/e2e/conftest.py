"""E2E test infrastructure.

- Collects per-test timing and outcome.
- Writes a Markdown report at `docs/E2E-REPORT.md` mirroring the team's
  reference format (overview, summary, skipped table, slow-test table).

The `--report` CLI flag is registered in the root `tests/conftest.py`
so it is recognised regardless of which test path is passed.
"""

from __future__ import annotations

import time
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

REPORT_PATH = Path("docs/E2E-REPORT.md")
SLOW_THRESHOLD_S = 10.0


@pytest.fixture(scope="session")
def e2e_state() -> dict[str, Any]:
    return {
        "started_at": datetime.now(UTC),
        "tests": [],
        "totals": defaultdict(int),
    }


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item: pytest.Item, call: pytest.CallInfo[None]) -> Any:
    outcome = yield
    result = outcome.get_result()
    if result.when != "call" and not (result.when == "setup" and result.skipped):
        return

    bucket = getattr(item.session, "_e2e_results", None)
    if bucket is None:
        bucket = []
        item.session._e2e_results = bucket  # type: ignore[attr-defined]

    skip_reason = ""
    if result.skipped:
        skip_reason = str(result.longrepr) if result.longrepr else "skipped"

    fspath = Path(item.fspath)
    file_path = str(fspath.relative_to(Path.cwd())) if fspath.is_absolute() else str(fspath)

    bucket.append(
        {
            "file": file_path,
            "name": item.name,
            "outcome": result.outcome,
            "duration": result.duration,
            "skip_reason": skip_reason,
        }
    )


def pytest_sessionstart(session: pytest.Session) -> None:
    session._e2e_started_at = time.time()  # type: ignore[attr-defined]


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:  # noqa: PLR0915
    if not session.config.getoption("--report"):
        return

    results: list[dict[str, Any]] = getattr(session, "_e2e_results", [])
    started_at = getattr(session, "_e2e_started_at", time.time())
    duration_s = time.time() - started_at
    duration_min = duration_s / 60

    passed = sum(1 for r in results if r["outcome"] == "passed")
    failed = sum(1 for r in results if r["outcome"] == "failed")
    skipped = sum(1 for r in results if r["outcome"] == "skipped")
    total = len(results)

    skipped_rows = [r for r in results if r["outcome"] == "skipped"]
    slow_rows = sorted(
        (r for r in results if r["duration"] >= SLOW_THRESHOLD_S),
        key=lambda r: r["duration"],
        reverse=True,
    )

    today = datetime.now(UTC).date().isoformat()
    lines: list[str] = []
    lines.append(f"# E2E Test Report — {today}")
    lines.append("")
    lines.append("## Overview")
    lines.append("")
    if total == 0:
        lines.append("No E2E tests executed.")
    else:
        verdict = "excellent" if failed == 0 else "needs attention"
        lines.append(
            f"All {total} tests ran in {duration_min:.1f} minutes. "
            f"{passed} passed, {failed} failed, {skipped} skipped. "
            f"The suite is in {verdict} shape."
        )
    lines.append("")
    lines.append("## Results Summary")
    lines.append("")
    lines.append("| Status | Count |")
    lines.append("|---|---|")
    lines.append(f"| Passed | {passed} |")
    lines.append(f"| Failed | {failed} |")
    lines.append(f"| Skipped | {skipped} |")
    lines.append(f"| Total | {total} |")
    lines.append("")

    lines.append("## Skipped Tests")
    lines.append("")
    if not skipped_rows:
        lines.append("None.")
    else:
        lines.append("| # | Test File | Test Name | Why Skipped |")
        lines.append("|---|---|---|---|")
        for i, r in enumerate(skipped_rows, start=1):
            reason = r["skip_reason"].replace("\n", " ").strip() or "skipped"
            lines.append(f"| {i} | {r['file']} | {r['name']} | {reason} |")
    lines.append("")

    lines.append(f"## Slow Tests (>{int(SLOW_THRESHOLD_S)}s)")
    lines.append("")
    if not slow_rows:
        lines.append("None.")
    else:
        lines.append("| # | Test File | Test Name | Duration |")
        lines.append("|---|---|---|---|")
        for i, r in enumerate(slow_rows, start=1):
            lines.append(f"| {i} | {r['file']} | {r['name']} | {r['duration']:.1f}s |")
    lines.append("")

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")
