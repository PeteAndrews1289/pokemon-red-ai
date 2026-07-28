from __future__ import annotations

import json
from pathlib import Path

import pytest

from pokemon_red_ai.report import (
    TraceReportError,
    generate_run_report,
    read_trace,
    render_run_report,
)


def _write_trace(path: Path, records: list[dict[str, object]]) -> None:
    path.write_text("".join(json.dumps(record) + "\n" for record in records), encoding="utf-8")


def test_bootstrap_report_has_narrative_sections_and_no_training_claim(tmp_path: Path) -> None:
    trace_path = tmp_path / "trace.jsonl"
    full_hash = "a" * 64
    _write_trace(
        trace_path,
        [
            {
                "kind": "manifest",
                "schema_version": 1,
                "created_at": "2026-07-19T04:00:51+00:00",
                "rom": {"title": "POKEMON RED", "sha256": full_hash},
                "config": {"sequence": "clean_boot_to_bedroom_red_blue"},
            },
            {"kind": "bootstrap_attempt_started", "label": "a"},
            {
                "kind": "bootstrap_attempt_finished",
                "label": "a",
                "frame": 9804,
                "reached_bedroom": True,
                "screen_sha256": "b" * 64,
                "state": {"map_id": 38, "coordinates": {"x": 3, "y": 6}},
            },
            {"kind": "result", "passed": True, "deterministic": True},
        ],
    )

    report_path = generate_run_report(trace_path)
    document = report_path.read_text(encoding="utf-8")

    assert report_path == tmp_path / "report.html"
    assert "Clean-game bootstrap" in document
    assert "Run manifest" in document
    assert "Outcomes" in document
    assert "Attempt a" in document
    assert "Run timeline" in document
    assert "No model training metrics yet." in document
    assert "Every recorded pass condition was satisfied." in document
    assert "aaaaaaaaaaaa…" in document
    assert full_hash not in document
    assert "<script" not in document
    assert "http://" not in document
    assert "https://" not in document


def test_report_escapes_trace_content_and_redacts_absolute_paths(tmp_path: Path) -> None:
    trace_path = tmp_path / "trace.jsonl"
    private_path = "/Users/example/Downloads/Pokemon Red.gb"
    attack = '<script>alert("not safe")</script>'
    _write_trace(
        trace_path,
        [
            {
                "kind": "manifest",
                "rom": {"title": attack},
                "note": f"ROM was loaded from {private_path}",
                "ratio": "17 / 20 attempts",
                private_path: "also private",
            },
            {"kind": "result", "passed": True, "message": attack},
        ],
    )

    output = tmp_path / "public" / "summary.html"
    generate_run_report(trace_path, output)
    document = output.read_text(encoding="utf-8")

    assert attack not in document
    assert '&lt;script&gt;alert(&quot;' in document
    assert private_path not in document
    assert "/Users/example" not in document
    assert "[private path omitted]" in document
    assert "17 / 20 attempts" in document


def test_smoke_report_handles_missing_attempts(tmp_path: Path) -> None:
    trace_path = tmp_path / "trace.jsonl"
    _write_trace(
        trace_path,
        [
            {"kind": "manifest", "config": {"boot_frames": 1800}},
            {"kind": "observation", "label": "title", "frame": 1800},
            {"kind": "action_result", "action": "start", "changed_screen": True},
            {"kind": "save_state_check", "deterministic": True},
            {"kind": "result", "passed": True},
        ],
    )

    generate_run_report(trace_path)
    document = (tmp_path / "report.html").read_text(encoding="utf-8")

    assert "Emulator smoke test" in document
    assert "This run type does not record repeated bootstrap attempts." in document
    assert "Controller action completed" in document
    assert "Save-state replay checked" in document


def test_read_trace_rejects_invalid_or_empty_input(tmp_path: Path) -> None:
    empty = tmp_path / "empty.jsonl"
    empty.write_text("\n", encoding="utf-8")
    with pytest.raises(TraceReportError, match="no records"):
        read_trace(empty)

    invalid = tmp_path / "invalid.jsonl"
    invalid.write_text('{"kind":', encoding="utf-8")
    with pytest.raises(TraceReportError, match="line 1"):
        read_trace(invalid)


def test_evaluation_records_are_separate_from_training() -> None:
    document = render_run_report(
        [
            {"kind": "manifest", "run_type": "evaluation", "actor": "frozen_policy"},
            {
                "kind": "evaluation_result",
                "attempts": 20,
                "successes": 17,
            },
            {"kind": "result", "passed": True},
        ]
    )

    assert "Model evaluation run" in document
    assert "Recorded evaluation metrics" in document
    assert "Successes: 17" in document
    assert "No model training metrics yet." in document
    assert "Recorded training metrics" not in document


def test_report_redacts_sensitive_fields_paths_and_oversized_values() -> None:
    secret = "s" * 700
    document = render_run_report(
        [
            {
                "kind": "manifest",
                "api_token": "do-not-display",
                "snapshot_payload": "do-not-display",
                "home": "~/private/run",
                "network": "\\\\server\\share\\run",
                "long_note": secret,
                "ratio": "17 / 20 attempts",
            }
        ]
    )

    assert "do-not-display" not in document
    assert "~/private/run" not in document
    assert "server\\share" not in document
    assert secret not in document
    assert "[sensitive value omitted]" in document
    assert "[private path omitted]" in document
    assert "[truncated 200 characters]" in document
    assert "17 / 20 attempts" in document


def test_report_refuses_to_overwrite_trace_or_write_non_html(tmp_path: Path) -> None:
    trace_path = tmp_path / "trace.jsonl"
    _write_trace(trace_path, [{"kind": "manifest"}])

    with pytest.raises(TraceReportError, match="same file"):
        generate_run_report(trace_path, trace_path)
    with pytest.raises(TraceReportError, match=".html extension"):
        generate_run_report(trace_path, tmp_path / "report.txt")

    assert trace_path.read_text(encoding="utf-8").startswith('{"kind": "manifest"}')


def test_report_limits_input_and_summarizes_long_timeline(tmp_path: Path) -> None:
    trace_path = tmp_path / "trace.jsonl"
    records = [{"kind": "event", "index": index} for index in range(205)]
    _write_trace(trace_path, records)

    with pytest.raises(TraceReportError, match="2-record"):
        read_trace(trace_path, max_records=2)
    with pytest.raises(TraceReportError, match="10-byte"):
        read_trace(trace_path, max_bytes=10)

    document = render_run_report(records)
    assert "Showing 200 of 205 timeline events; 5 omitted." in document
    assert "Event 1" in document
    assert "Event 205" in document
