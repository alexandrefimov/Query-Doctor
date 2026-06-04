#!/usr/bin/env python3
"""Validate a sanitized Spark compact evidence package without echoing payloads."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from query_doctor.cli.validate_spark_evidence_package import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())
