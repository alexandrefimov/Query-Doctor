"""Optimizer route defaults."""

from __future__ import annotations

import os


BUILTIN_OPTIMIZER_MODEL = "deepseek-coder-v2:16b"
DEFAULT_OPTIMIZER_MODEL = os.getenv("QD_OPTIMIZER_MODEL", BUILTIN_OPTIMIZER_MODEL)
