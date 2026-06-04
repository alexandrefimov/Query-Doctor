#!/usr/bin/env python3
"""Export sanitized Spark compact evidence package samples as fixtures."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from query_doctor.cli.export_spark_evidence_fixtures import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())
