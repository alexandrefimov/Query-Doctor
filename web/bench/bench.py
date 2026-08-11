"""Time query_doctor.analyzer.service.analyze on a profile text.

Runs identically on CPython and inside Pyodide: no argparse, no I/O helpers,
no query_doctor.cli import.
"""
from __future__ import annotations

import sys
import time
from types import SimpleNamespace

from query_doctor.analyzer.action_cards import DEFAULT_LARGE_BYTES_THRESHOLD
from query_doctor.analyzer.service import analyze

ARGS = SimpleNamespace(
    top_n=10,
    rows_ratio_threshold=10.0,
    mem_ratio_threshold=4.0,
    slow_operator_ms=10_000.0,
    large_rows_threshold=1_000_000.0,
    large_bytes_threshold=DEFAULT_LARGE_BYTES_THRESHOLD,
    max_evidence_lines=30,
)


def run(text: str, repeats: int = 3) -> dict:
    best = None
    result = None
    for _ in range(repeats):
        t0 = time.perf_counter()
        result = analyze(text, ARGS)
        dt = time.perf_counter() - t0
        best = dt if best is None else min(best, dt)
    return {
        "seconds": best,
        "kib": len(text.encode()) / 1024,
        "operators": len(result.get("operators", []) or []),
        "keys": len(result),
    }


if __name__ == "__main__":
    with open(sys.argv[1], encoding="utf-8") as fh:
        text = fh.read()
    out = run(text)
    print(
        f"{sys.argv[1]}: {out['kib']:.0f} KiB -> {out['seconds'] * 1000:.0f} ms "
        f"(operators={out['operators']}, fact keys={out['keys']})"
    )
