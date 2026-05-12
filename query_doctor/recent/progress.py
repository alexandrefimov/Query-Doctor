"""Progress event writer for the Recent batch workflow."""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import TextIO


class ProgressWriter:
    def __init__(self, path: Path | None) -> None:
        self.path = path
        self._handle: TextIO | None = None
        self._lock: threading.Lock | None = None
        if path is not None:
            self._lock = threading.Lock()
            self._handle = path.open("a", encoding="utf-8")

    def close(self) -> None:
        if self._handle is not None:
            self._handle.close()

    def emit(self, **event: object) -> None:
        if self._handle is None:
            return
        payload = {key: value for key, value in event.items() if value is not None}
        line = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        assert self._lock is not None
        with self._lock:
            self._handle.write(line + "\n")
            self._handle.flush()
