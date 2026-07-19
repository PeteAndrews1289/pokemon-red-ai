from __future__ import annotations

import html
import json
import re
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any


class TraceReportError(ValueError):
    """Raised when a trace cannot be turned into a trustworthy report."""


Record = dict[str, Any]

MAX_TRACE_BYTES = 16 * 1024 * 1024
MAX_TRACE_RECORDS = 50_000
MAX_TIMELINE_EVENTS = 200
MAX_METRIC_ROWS = 200
MAX_ATTEMPTS = 20
MAX_FIELDS_PER_RECORD = 100
MAX_NESTING_DEPTH = 8
MAX_COLLECTION_ITEMS = 50
MAX_DISPLAY_STRING = 500
MAX_DISPLAY_VALUE = 1_500

_HASH_RE = re.compile(r"^[0-9a-fA-F]{32,}$")
_WINDOWS_PATH_RE = re.compile(r"(?:^|[\s\"'=([])[A-Za-z]:[\\/]")
_POSIX_PATH_RE = re.compile(r"(?:^|[\s\"'=([])/(?!/|\s)")
_HOME_PATH_RE = re.compile(r"(?:^|[\s\"'=([])~[\\/]")
_UNC_PATH_RE = re.compile(r"(?:^|[\s\"'=([])\\\\[^\\\s]+\\[^\\\s]+")
_SECRET_VALUE_PATTERNS = (
    re.compile(r"(?i)\b(?:bearer|basic)\s+[A-Za-z0-9._~+/=-]{12,}"),
    re.compile(r"\b(?:sk-[A-Za-z0-9_-]{16,}|gh[pousr]_[A-Za-z0-9_]{16,})\b"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{16,}\b"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\b[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b"),
    re.compile(r"(?i)\b(?:token|secret|password|api[ _-]?key)\s*[:=]\s*\S+"),
)
_SENSITIVE_KEY_PARTS = {"token", "secret", "password", "path", "payload"}
_TRAINING_METRIC_KINDS = {
    "episode",
    "episode_result",
    "metric",
    "training_metric",
    "training_result",
}
_EVALUATION_METRIC_KINDS = {
    "evaluation",
    "evaluation_metric",
    "evaluation_result",
}
_RUN_TITLES = {
    "bootstrap": "Clean-game bootstrap",
    "calibration": "Environment calibration",
    "development": "Development run",
    "evaluation": "Model evaluation run",
    "smoke": "Emulator smoke test",
    "training": "Model training run",
}


def read_trace(
    trace_path: Path,
    *,
    max_bytes: int = MAX_TRACE_BYTES,
    max_records: int = MAX_TRACE_RECORDS,
) -> list[Record]:
    """Read a JSONL trace and validate its record-level shape.

    The report deliberately accepts evolving event payloads, but every non-empty
    line must contain one JSON object with a string ``kind`` field.
    """
    if max_bytes < 1 or max_records < 1:
        raise ValueError("Trace limits must be positive integers.")

    records: list[Record] = []
    total_bytes = 0
    try:
        source = trace_path.open("rb")
    except OSError as error:
        raise TraceReportError("Could not read the trace file.") from error

    with source:
        line_number = 0
        while True:
            remaining_bytes = max_bytes - total_bytes
            raw_line = source.readline(remaining_bytes + 1)
            if not raw_line:
                break
            line_number += 1
            total_bytes += len(raw_line)
            if total_bytes > max_bytes:
                raise TraceReportError(f"The trace exceeds the {max_bytes}-byte report limit.")
            if not raw_line.strip():
                continue
            if len(records) >= max_records:
                raise TraceReportError(f"The trace exceeds the {max_records}-record report limit.")
            try:
                line = raw_line.decode("utf-8")
                record = json.loads(line)
            except (UnicodeDecodeError, json.JSONDecodeError) as error:
                raise TraceReportError(
                    f"Trace line {line_number} is not valid UTF-8 JSON."
                ) from error
            if not isinstance(record, dict) or not isinstance(record.get("kind"), str):
                raise TraceReportError(
                    f"Trace line {line_number} must be an object with a string kind field."
                )
            records.append(record)

    if not records:
        raise TraceReportError("The trace contains no records.")
    return records


def generate_run_report(trace_path: Path, output_path: Path | None = None) -> Path:
    """Generate a self-contained HTML run report and return its path.

    The generator adds no screenshots, ROM bytes, JavaScript, or remote assets.
    Its redaction is defense in depth, not a replacement for reviewing and
    sanitizing a trace before sharing it.
    """
    destination = output_path or trace_path.with_name("report.html")
    if trace_path.resolve() == destination.resolve():
        raise TraceReportError("The report output cannot be the same file as the source trace.")
    if output_path is not None and destination.suffix.lower() != ".html":
        raise TraceReportError("An explicit report output must use the .html extension.")

    records = read_trace(trace_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    document = render_run_report(records)
    try:
        destination.write_text(document, encoding="utf-8")
    except OSError as error:
        raise TraceReportError("Could not write the run report.") from error
    return destination


def render_run_report(records: Iterable[Mapping[str, Any]]) -> str:
    """Render already-loaded trace records as safe, standalone HTML."""
    copied_records: list[Record] = []
    for index, record in enumerate(records, start=1):
        if index > MAX_TRACE_RECORDS:
            raise TraceReportError(
                f"The trace exceeds the {MAX_TRACE_RECORDS}-record report limit."
            )
        if not isinstance(record, Mapping) or not isinstance(record.get("kind"), str):
            raise TraceReportError(f"Record {index} must have a string kind field.")
        copied_records.append(dict(record))
    if not copied_records:
        raise TraceReportError("The trace contains no records.")

    manifest = next((record for record in copied_records if record.get("kind") == "manifest"), {})
    result = next(
        (record for record in reversed(copied_records) if record.get("kind") == "result"),
        {},
    )
    attempts = [
        record for record in copied_records if record.get("kind") == "bootstrap_attempt_finished"
    ]
    run_type = _run_type(copied_records, manifest)
    training = [
        record for record in copied_records if _is_training_record(record, run_type=run_type)
    ]
    evaluations = [record for record in copied_records if _is_evaluation_record(record, run_type)]
    run_title = _run_title(manifest, run_type)
    outcome_label, outcome_class, outcome_detail = _outcome(result)

    title = _escape(run_title)
    status = _escape(outcome_label)
    detail = _escape(outcome_detail)
    manifest_section = _record_table(manifest, "Run manifest", exclude={"kind"})
    outcome_section = _record_table(result, "Outcomes", exclude={"kind"})
    attempts_section = _attempts_section(attempts)
    training_section = _training_section(training)
    evaluation_section = _evaluation_section(evaluations)
    timeline_section = _timeline_section(copied_records)

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="color-scheme" content="light dark">
  <title>{title} · Pokémon Red AI</title>
  <style>
    :root {{
      color-scheme: light dark;
      --bg: #f5f2e9;
      --surface: #fffdf7;
      --text: #1c2530;
      --muted: #58636f;
      --line: #d2c9b6;
      --accent: #c62828;
      --accent-soft: #f5dada;
      --success: #176b3a;
      --success-soft: #dcefe3;
      --warning: #865a00;
      --warning-soft: #f8ebc7;
      --failure: #9d1c1c;
      --failure-soft: #f8dede;
      --code: #eee8da;
    }}
    @media (prefers-color-scheme: dark) {{
      :root {{
        --bg: #111820;
        --surface: #18232e;
        --text: #f5f1e7;
        --muted: #bec7d0;
        --line: #43515f;
        --accent: #ff6868;
        --accent-soft: #4b282b;
        --success: #82d9a2;
        --success-soft: #193b2a;
        --warning: #f4cc69;
        --warning-soft: #43371c;
        --failure: #ff8a8a;
        --failure-soft: #4b2626;
        --code: #24323e;
      }}
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font-family:
        ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      line-height: 1.55;
    }}
    main {{ width: min(72rem, calc(100% - 2rem)); margin: 0 auto; padding: 3rem 0 5rem; }}
    header {{ border-top: .5rem solid var(--accent); padding: 2rem; background: var(--surface); }}
    h1, h2, h3 {{ line-height: 1.15; }}
    h1 {{ margin: .2rem 0 .7rem; font-size: clamp(2rem, 6vw, 4.25rem); letter-spacing: -.04em; }}
    h2 {{ margin: 0 0 1rem; font-size: 1.45rem; }}
    h3 {{ margin: 0; font-size: 1.05rem; }}
    .eyebrow {{
      color: var(--accent);
      font-weight: 800;
      letter-spacing: .12em;
      text-transform: uppercase;
    }}
    .lede {{ color: var(--muted); max-width: 66ch; margin: 0; }}
    .status {{
      display: inline-flex;
      gap: .55rem;
      align-items: center;
      margin: 1.4rem 0 .6rem;
      padding: .45rem .75rem;
      border: 1px solid currentColor;
      border-radius: 999px;
      font-weight: 800;
    }}
    .status::before {{
      content: "";
      width: .7rem;
      height: .7rem;
      border-radius: 50%;
      background: currentColor;
    }}
    .status.passed {{ color: var(--success); background: var(--success-soft); }}
    .status.failed {{ color: var(--failure); background: var(--failure-soft); }}
    .status.recorded {{ color: var(--warning); background: var(--warning-soft); }}
    section {{
      margin-top: 1rem;
      padding: 1.5rem;
      background: var(--surface);
      border: 1px solid var(--line);
    }}
    .section-note {{ color: var(--muted); margin: -.45rem 0 1rem; }}
    .table-wrap {{ overflow-x: auto; }}
    table {{ width: 100%; border-collapse: collapse; }}
    caption {{ text-align: left; font-weight: 800; margin-bottom: .6rem; }}
    th, td {{
      padding: .65rem .7rem;
      border-bottom: 1px solid var(--line);
      text-align: left;
      vertical-align: top;
    }}
    th {{ width: 34%; color: var(--muted); font-weight: 700; }}
    code {{
      overflow-wrap: anywhere;
      padding: .1rem .3rem;
      background: var(--code);
      border-radius: .2rem;
    }}
    .attempts {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(15rem, 1fr));
      gap: .8rem;
    }}
    .attempt {{
      padding: 1rem;
      border: 1px solid var(--line);
      border-left: .35rem solid var(--accent);
    }}
    .attempt dl {{
      display: grid;
      grid-template-columns: minmax(7rem, auto) 1fr;
      gap: .35rem .8rem;
      margin: .75rem 0 0;
    }}
    dt {{ color: var(--muted); }}
    dd {{ margin: 0; overflow-wrap: anywhere; }}
    .empty {{
      padding: 1rem;
      border-left: .35rem solid var(--warning);
      background: var(--warning-soft);
    }}
    .timeline {{ list-style: none; margin: 0; padding: 0; }}
    .timeline li {{
      position: relative;
      margin-left: .6rem;
      padding: 0 0 1.2rem 1.7rem;
      border-left: 2px solid var(--line);
    }}
    .timeline li::before {{
      content: "";
      position: absolute;
      left: -.42rem;
      top: .25rem;
      width: .7rem;
      height: .7rem;
      border-radius: 50%;
      background: var(--accent);
    }}
    .timeline li:last-child {{ border-left-color: transparent; padding-bottom: 0; }}
    .event-meta {{ color: var(--muted); font-size: .9rem; }}
    details {{ margin-top: .4rem; }}
    summary {{ cursor: pointer; color: var(--muted); }}
    footer {{ color: var(--muted); margin-top: 1.5rem; font-size: .9rem; }}
    @media print {{
      :root {{ color-scheme: light; }}
      body {{ background: white; }}
      main {{ width: 100%; padding: 0; }}
      section, header {{ break-inside: avoid; box-shadow: none; }}
    }}
  </style>
</head>
<body>
  <main>
    <header>
      <div class="eyebrow">Pokémon Red AI · Run report</div>
      <h1>{title}</h1>
      <p class="lede">
        A human-readable account of what this experiment ran, observed, and proved.
      </p>
      <div class="status {outcome_class}" role="status">{status}</div>
      <p class="lede">{detail}</p>
    </header>
    {manifest_section}
    {outcome_section}
    {attempts_section}
    {training_section}
    {evaluation_section}
    {timeline_section}
    <footer>
      Generated locally. The generator adds no screenshots, ROM data, JavaScript, or remote
      assets. Review and sanitize the source trace before sharing this report.
    </footer>
  </main>
</body>
</html>
"""


def _run_type(records: list[Record], manifest: Mapping[str, Any]) -> str:
    declared = manifest.get("run_type")
    if isinstance(declared, str):
        normalized = declared.lower().strip().replace("-", "_").replace(" ", "_")
        aliases = {
            "bootstrap_test": "bootstrap",
            "calibration_run": "calibration",
            "development_run": "development",
            "evaluation_run": "evaluation",
            "smoke_test": "smoke",
            "training_run": "training",
        }
        normalized = aliases.get(normalized, normalized)
        if normalized in _RUN_TITLES:
            return normalized

    # Legacy bootstrap and smoke traces predate manifest.run_type. Keep their
    # established titles, but do not infer training or evaluation from events.
    kinds = {str(record.get("kind", "")) for record in records}
    if any(kind.startswith("bootstrap_") for kind in kinds):
        return "bootstrap"
    if kinds & {"observation", "action_result", "save_state_check"}:
        return "smoke"
    return "development"


def _run_title(manifest: Mapping[str, Any], run_type: str) -> str:
    declared = manifest.get("run_name")
    if isinstance(declared, str) and 1 <= len(declared.strip()) <= 100:
        return declared.strip()
    return _RUN_TITLES[run_type]


def _outcome(result: Mapping[str, Any]) -> tuple[str, str, str]:
    passed = result.get("passed")
    if passed is True:
        return "Passed", "passed", "Every recorded pass condition was satisfied."
    if passed is False:
        return "Failed", "failed", "At least one recorded pass condition was not satisfied."
    return "Recorded", "recorded", "This trace does not include a final pass/fail outcome."


def _record_table(
    record: Mapping[str, Any],
    heading: str,
    *,
    exclude: set[str] | None = None,
) -> str:
    omitted = exclude or set()
    fields = [(key, value) for key, value in _flatten(record) if key not in omitted]
    if not fields:
        body = '<p class="empty">No data was recorded for this section.</p>'
    else:
        rows = "".join(
            f"<tr><th scope=\"row\">{_escape(_friendly_label(key))}</th>"
            f"<td>{_format_value(key, value)}</td></tr>"
            for key, value in fields
        )
        body = (
            '<div class="table-wrap"><table>'
            f"<caption>{_escape(heading)} details</caption><tbody>{rows}</tbody></table></div>"
        )
    section_id = _slug(heading)
    return (
        f'<section aria-labelledby="{section_id}"><h2 id="{section_id}">'
        f"{_escape(heading)}</h2>{body}</section>"
    )


def _attempts_section(attempts: list[Record]) -> str:
    if not attempts:
        cards = '<p class="empty">This run type does not record repeated bootstrap attempts.</p>'
    else:
        sampled, omitted = _sample_indexed(attempts, MAX_ATTEMPTS)
        rendered: list[str] = []
        for index, attempt in sampled:
            label = _safe_text(attempt.get("label", index))
            fields = [
                (key, value)
                for key, value in _flatten(attempt)
                if key not in {"kind", "label", "schema_version"}
            ]
            details = "".join(
                f"<dt>{_escape(_friendly_label(key))}</dt><dd>{_format_value(key, value)}</dd>"
                for key, value in fields
            )
            rendered.append(
                '<article class="attempt">'
                f"<h3>Attempt {_escape(label)}</h3><dl>{details}</dl>"
                "</article>"
            )
        notice = _omission_notice("bootstrap attempts", omitted, len(attempts))
        cards = f'{notice}<div class="attempts">{"".join(rendered)}</div>'
    return (
        '<section aria-labelledby="attempts"><h2 id="attempts">Attempts</h2>'
        '<p class="section-note">Repeated attempts make determinism visible instead of assumed.</p>'
        f"{cards}</section>"
    )


def _training_section(training: list[Record]) -> str:
    if not training:
        content = (
            '<p class="empty"><strong>No model training metrics yet.</strong> '
            "This run validates the emulator and experiment harness; it does not claim that a "
            "model learned or improved.</p>"
        )
    else:
        sampled, omitted = _sample_indexed(training, MAX_METRIC_ROWS)
        rows: list[str] = []
        for index, record in sampled:
            kind = _safe_text(record.get("kind", "metric"))
            payload = [(key, value) for key, value in _flatten(record) if key != "kind"]
            summary = ", ".join(
                f"{_friendly_label(key)}: {_safe_text(_display_value(key, value))}"
                for key, value in payload
            )
            rows.append(
                f"<tr><th scope=\"row\">{index}</th><td>{_escape(kind)}</td>"
                f"<td>{_escape(summary)}</td></tr>"
            )
        content = (
            _omission_notice("training metric rows", omitted, len(training))
            + '<div class="table-wrap"><table><caption>Recorded training metrics</caption>'
            + '<thead><tr><th scope="col">#</th><th scope="col">Event</th>'
            + '<th scope="col">Values</th></tr></thead>'
            + f'<tbody>{"".join(rows)}</tbody></table></div>'
        )
    return (
        '<section aria-labelledby="training"><h2 id="training">Training progress</h2>'
        f"{content}</section>"
    )


def _evaluation_section(evaluations: list[Record]) -> str:
    if not evaluations:
        content = (
            '<p class="empty"><strong>No model evaluation metrics yet.</strong> '
            "This trace does not record a held-out or checkpoint evaluation.</p>"
        )
    else:
        sampled, omitted = _sample_indexed(evaluations, MAX_METRIC_ROWS)
        rows: list[str] = []
        for index, record in sampled:
            kind = _safe_text(record.get("kind", "evaluation"))
            payload = [(key, value) for key, value in _flatten(record) if key != "kind"]
            summary = ", ".join(
                f"{_friendly_label(key)}: {_safe_text(_display_value(key, value))}"
                for key, value in payload
            )
            rows.append(
                f'<tr><th scope="row">{index}</th><td>{_escape(kind)}</td>'
                f"<td>{_escape(summary)}</td></tr>"
            )
        content = (
            _omission_notice("evaluation metric rows", omitted, len(evaluations))
            + '<div class="table-wrap"><table><caption>Recorded evaluation metrics</caption>'
            + '<thead><tr><th scope="col">#</th><th scope="col">Event</th>'
            + '<th scope="col">Values</th></tr></thead>'
            + f'<tbody>{"".join(rows)}</tbody></table></div>'
        )
    return (
        '<section aria-labelledby="evaluation"><h2 id="evaluation">Evaluation evidence</h2>'
        f"{content}</section>"
    )


def _timeline_section(records: list[Record]) -> str:
    items: list[str] = []
    sampled, omitted = _sample_indexed(records, MAX_TIMELINE_EVENTS)
    for index, record in sampled:
        kind = _safe_text(record.get("kind", "event"))
        event_title = _event_title(record)
        frame = record.get("frame")
        frame_text = f" · frame {_escape(frame)}" if frame is not None else ""
        fields = [
            (key, value)
            for key, value in _flatten(record)
            if key not in {"kind", "frame", "schema_version"}
        ]
        rows = "".join(
            f"<tr><th scope=\"row\">{_escape(_friendly_label(key))}</th>"
            f"<td>{_format_value(key, value)}</td></tr>"
            for key, value in fields
        )
        details = (
            '<details><summary>Show recorded fields</summary><div class="table-wrap"><table>'
            f"<tbody>{rows}</tbody></table></div></details>"
            if rows
            else ""
        )
        items.append(
            "<li>"
            f"<h3>{_escape(event_title)}</h3>"
            f'<div class="event-meta">Event {index} · {_escape(kind)}{frame_text}</div>'
            f"{details}</li>"
        )
    return (
        '<section aria-labelledby="timeline"><h2 id="timeline">Run timeline</h2>'
        '<p class="section-note">Events appear in the exact order written to the trace.</p>'
        f'{_omission_notice("timeline events", omitted, len(records))}'
        f'<ol class="timeline">{"".join(items)}</ol></section>'
    )


def _event_title(record: Mapping[str, Any]) -> str:
    kind = str(record.get("kind", "event"))
    label = _safe_text(record.get("label", ""))
    titles = {
        "manifest": "Run configuration recorded",
        "observation": f"Observation recorded{f': {label}' if label else ''}",
        "action_result": "Controller action completed",
        "save_state_check": "Save-state replay checked",
        "bootstrap_attempt_started": f"Attempt {label or '?'} started",
        "bootstrap_attempt_finished": f"Attempt {label or '?'} finished",
        "result": "Final outcome recorded",
    }
    return titles.get(kind, _friendly_label(kind))


def _is_training_record(record: Mapping[str, Any], *, run_type: str) -> bool:
    kind = str(record.get("kind", "")).lower()
    if kind in _EVALUATION_METRIC_KINDS or kind.startswith("evaluation_"):
        return False
    if kind in {"training_metric", "training_result"}:
        return True
    return run_type == "training" and kind in _TRAINING_METRIC_KINDS


def _is_evaluation_record(record: Mapping[str, Any], run_type: str) -> bool:
    kind = str(record.get("kind", "")).lower()
    if kind in _EVALUATION_METRIC_KINDS or kind.startswith("evaluation_"):
        return True
    return run_type == "evaluation" and kind in {"episode", "episode_result", "metric"}


def _sample_indexed(records: list[Record], limit: int) -> tuple[list[tuple[int, Record]], int]:
    indexed = list(enumerate(records, start=1))
    if len(indexed) <= limit:
        return indexed, 0
    head_count = (limit + 1) // 2
    tail_count = limit - head_count
    sampled = indexed[:head_count]
    if tail_count:
        sampled.extend(indexed[-tail_count:])
    return sampled, len(indexed) - len(sampled)


def _omission_notice(label: str, omitted: int, total: int) -> str:
    if omitted == 0:
        return ""
    shown = total - omitted
    return (
        '<p class="empty">'
        f"Showing {shown} of {total} {_escape(label)}; {omitted} omitted. "
        "The first and last records are retained."
        "</p>"
    )


def _flatten(value: Mapping[str, Any], prefix: str = "") -> list[tuple[str, Any]]:
    fields: list[tuple[str, Any]] = []
    seen: set[int] = set()
    field_limit_reached = False

    def add(key: str, child: Any) -> None:
        nonlocal field_limit_reached
        if len(fields) >= MAX_FIELDS_PER_RECORD - 1:
            field_limit_reached = True
            return
        fields.append((key, child))

    def walk(mapping: Mapping[str, Any], parent: str, depth: int) -> None:
        nonlocal field_limit_reached
        if field_limit_reached:
            return
        if id(mapping) in seen:
            add(f"{parent}.[nested content]".strip("."), "[recursive content omitted]")
            return
        seen.add(id(mapping))
        try:
            for raw_key, child in mapping.items():
                if field_limit_reached:
                    break
                if _is_sensitive_key(raw_key):
                    key = f"{parent}.[sensitive field]".strip(".")
                    add(key, "[sensitive value omitted]")
                    continue
                key = _safe_text(raw_key)
                qualified = f"{parent}.{key}" if parent else key
                if isinstance(child, Mapping):
                    if depth >= MAX_NESTING_DEPTH:
                        add(qualified, "[nested content omitted: depth limit]")
                    else:
                        walk(child, qualified, depth + 1)
                else:
                    add(qualified, child)
        finally:
            seen.remove(id(mapping))

    walk(value, prefix, 0)
    if field_limit_reached:
        fields.append(("[additional fields]", "[omitted: display field limit reached]"))
    return fields


def _format_value(key: str, value: Any) -> str:
    display = _display_value(key, value)
    tag = "code" if _looks_like_hash(key, value) else "span"
    return f"<{tag}>{html.escape(display, quote=True)}</{tag}>"


def _display_value(key: str, value: Any) -> str:
    if _is_sensitive_key(key):
        return "[sensitive value omitted]"
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if value is None:
        return "—"
    if _looks_like_hash(key, value):
        safe = _safe_text(value)
        if safe.startswith("["):
            return safe
        return f"{safe[:12]}…" if len(safe) > 12 else safe
    if isinstance(value, (list, tuple)):
        redacted = _redact_nested(value)
        serialized = json.dumps(redacted, ensure_ascii=False, separators=(",", ":"))
        return _truncate_text(serialized, MAX_DISPLAY_VALUE)
    return _safe_text(value)


def _looks_like_hash(key: str, value: Any) -> bool:
    text = str(value)
    lowered_key = key.lower()
    return bool(_HASH_RE.fullmatch(text)) or "sha" in lowered_key or "hash" in lowered_key


def _redact_nested(value: Any, *, depth: int = 0) -> Any:
    if depth >= MAX_NESTING_DEPTH:
        return "[nested content omitted: depth limit]"
    if isinstance(value, str):
        return _safe_text(value)
    if isinstance(value, Mapping):
        redacted: dict[str, Any] = {}
        for index, (key, child) in enumerate(value.items(), start=1):
            if index > MAX_COLLECTION_ITEMS:
                redacted["[additional items]"] = "[omitted: collection limit reached]"
                break
            if _is_sensitive_key(key):
                redacted[f"[sensitive field {index}]"] = "[sensitive value omitted]"
            else:
                redacted[_safe_text(key)] = _redact_nested(child, depth=depth + 1)
        return redacted
    if isinstance(value, (list, tuple)):
        redacted_items = [
            _redact_nested(child, depth=depth + 1)
            for child in value[:MAX_COLLECTION_ITEMS]
        ]
        if len(value) > MAX_COLLECTION_ITEMS:
            redacted_items.append("[additional items omitted: collection limit reached]")
        return redacted_items
    return value


def _safe_text(value: Any) -> str:
    text = str(value)
    lowered = text.lower()
    if (
        "file://" in lowered
        or _WINDOWS_PATH_RE.search(text)
        or _POSIX_PATH_RE.search(text)
        or _HOME_PATH_RE.search(text)
        or _UNC_PATH_RE.search(text)
    ):
        return "[private path omitted]"
    if any(pattern.search(text) for pattern in _SECRET_VALUE_PATTERNS):
        return "[secret-like value omitted]"
    return _truncate_text(text, MAX_DISPLAY_STRING)


def _is_sensitive_key(value: Any) -> bool:
    text = str(value).lower()
    normalized = re.sub(r"[^a-z0-9]+", "", text)
    if normalized in {"apikey", "rawmemory"}:
        return True
    parts = {part for part in re.split(r"[^a-z0-9]+", text) if part}
    return (
        bool(parts & _SENSITIVE_KEY_PARTS)
        or {"api", "key"} <= parts
        or {"raw", "memory"} <= parts
    )


def _truncate_text(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    omitted = len(text) - limit
    return f"{text[:limit]}… [truncated {omitted} characters]"


def _escape(value: Any) -> str:
    return html.escape(_safe_text(value), quote=True)


def _friendly_label(value: str) -> str:
    return value.replace("_", " ").replace(".", " · ").strip().title()


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
