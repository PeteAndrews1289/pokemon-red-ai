from __future__ import annotations

import json
from pathlib import Path

from pokemon_red_ai.trace import JsonlTrace


def test_trace_writes_compact_jsonl(tmp_path: Path) -> None:
    trace_path = tmp_path / "trace.jsonl"
    with JsonlTrace(trace_path) as trace:
        trace.write("manifest", value=1)
        trace.write("result", passed=True)

    records = [json.loads(line) for line in trace_path.read_text().splitlines()]
    assert records == [
        {"kind": "manifest", "schema_version": 1, "value": 1},
        {"kind": "result", "passed": True, "schema_version": 1},
    ]
