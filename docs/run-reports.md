# Run reports

The JSONL trace is the experiment's machine-readable evidence. A run report turns that evidence
into a single, local HTML page that a reader can understand without knowing the emulator code.
It is intended for development notes, comparisons between milestones, and visual storytelling.

## What the report communicates

Every report answers the same questions in the same order:

1. **What kind of run was this?** The manifest declares calibration, development, training, or
   evaluation, plus a human-readable run name and actor.
2. **Did it pass?** The final recorded result becomes a prominent status, with the underlying
   outcome fields shown below it.
3. **What exactly ran?** The manifest records ROM identity, software versions, and configuration.
   Hashes are shortened for readability while still serving as useful visual fingerprints.
4. **Was the result repeatable?** Bootstrap attempts are placed side by side so matching frames,
   states, and hashes can be compared.
5. **What happened in order?** Small traces show every event in order. Long traces retain the first
   and last events with an explicit omission count.
6. **Was a model actually trained?** Harness-only runs explicitly say **No model training metrics
   yet.** This prevents a successful emulator check from being mistaken for learning progress.

## Privacy and portability

The generated page is standalone: its styling is embedded and it needs no network connection. The
generator itself adds no JavaScript, remote assets, ROM bytes, screenshots, or source trace path.
Screenshots remain separate run artifacts by default, which keeps the report small and avoids
quietly copying visual artifacts into a shareable document.

**A report is only as publishable as its source trace.** Trace writers and the person publishing a
report remain responsible for review. As defense in depth, the generator redacts common path forms,
secret-like values, sensitive keys, oversized strings, deep nesting, and oversized collections.
Every displayed key and value is HTML-escaped, so trace text cannot become executable markup. These
checks reduce risk; they are not a universal secret detector or permission to feed arbitrary raw
memory into a report.

The report shows hash values as twelve hexadecimal characters plus an ellipsis. The source JSONL
remains the authoritative record when a complete hash is needed for verification.

## Python interface

The CLI can integrate the generator with two small functions:

```python
from pathlib import Path

from pokemon_red_ai.report import generate_run_report, render_run_report

report_path = generate_run_report(Path("runs/example/trace.jsonl"))

# Or render validated, already-loaded records without writing a file:
html_document = render_run_report(records)
```

`generate_run_report(trace_path)` writes `report.html` beside the trace. Passing a second `.html`
`Path` writes to that explicit destination instead. It refuses to overwrite the source trace. The
function returns the destination path. Invalid JSONL, non-object records, missing event kinds,
empty traces, oversized inputs, and excessive record counts raise `TraceReportError` with a concise
message that does not repeat private trace content.

The current limits accept at most 16 MiB and 50,000 records. Tables and timelines show bounded
first/last samples with exact omission counts rather than generating an unbounded page.

## Future training traces

When model training begins, metric events can use kinds such as `episode_result` or
`training_metric`. Held-out results use separate `evaluation` or `evaluation_result` events. The
report renders training diagnostics and evaluation evidence in different sections; an evaluation
event can never make the training section claim that learning occurred.

A later reporting milestone can add charts while preserving the same constraints: local assets
only, accessible text equivalents, explicit units, bounded data, and no claim of progress without
recorded evidence.
