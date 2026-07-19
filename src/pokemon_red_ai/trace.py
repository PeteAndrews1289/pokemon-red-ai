from __future__ import annotations

import json
from pathlib import Path
from typing import Any, TextIO

from pokemon_red_ai.constants import TRACE_SCHEMA_VERSION


class JsonlTrace:
    """Append-only trace writer with stable JSON key ordering."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._file: TextIO | None = None

    def __enter__(self) -> JsonlTrace:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._file = self.path.open("x", encoding="utf-8")
        return self

    def __exit__(self, *_: object) -> None:
        if self._file is not None:
            self._file.close()
        self._file = None

    def write(self, kind: str, **payload: Any) -> None:
        if self._file is None:
            raise RuntimeError("Trace is not open.")
        record = {"schema_version": TRACE_SCHEMA_VERSION, "kind": kind, **payload}
        self._file.write(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n")
        self._file.flush()
