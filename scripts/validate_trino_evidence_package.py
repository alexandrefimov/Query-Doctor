#!/usr/bin/env python3
"""Validate a sanitized Trino evidence package without echoing payloads."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from query_doctor.cli.validate_trino_evidence_package import (  # noqa: E402
    main,
    print_safe_summary,
)


if __name__ == "__main__":
    raise SystemExit(main())
