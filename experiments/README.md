# Public experiment evidence

This directory contains reviewed, redistribution-safe evidence for claims made in the project
documentation. It is deliberately separate from `runs/`, which holds private local artifacts such
as gameplay screenshots.

Public evidence may include sanitized JSONL events, aggregate metrics, original diagrams, and
standalone reports. It must not include ROMs, save states, emulator snapshots, gameplay captures,
private paths, credentials, or extracted game assets.

| Experiment | Run class | Actor | Evidence | Result |
| --- | --- | --- | ---: | --- |
| [Phase 0 clean bootstrap](phase-0-bootstrap/README.md) | Calibration | Scripted harness | E3 — Repeated | Two clean boots matched |
| [Q1 house exit](q1-left-home/README.md) | Checkpoint discovery | Seeded random emitter | E3 / H3 | One of two seeds left the house; Q1 gate failed |
| [Archive v2 qualification](archive-v2-qualification/README.md) | Engineering qualification | Seeded random emitter | E3 — Repeated | Continuous, graceful-resume, and hard-crash gates passed |
| [Visual Apprentice Stage 0](visual-apprentice-stage0/README.md) | End-to-end learning smoke | Recurrent pixel policy | E3 — Qualified pipeline | Exact 419-action route reproduced once from clean power-on; no recovery claim |
| [V12 final experiential run](v12-final/README.md) | Final training result | Recurrent goal-conditioned visual PPO policy | E3 training / E2 terminal limitation | 8.24M actions and Route 1; 55/502 exams, zero competent skills, no composition |

An experiment appearing here is not automatically a model evaluation. Read its run class, actor,
information boundaries, and limitations before interpreting the result.
