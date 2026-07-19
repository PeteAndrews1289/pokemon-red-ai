# Experiment protocol

This document defines the claims the project may make and the evidence required to make them.

## Observation disclosure

Every experiment must list what reached the acting policy, what was visible only to the referee,
and what was used only during development. The initial track is called **instrumented**, not
screen-only.

## Training and evaluation separation

- Training may use task-specific private save states.
- Evaluation code, prompts, checkpoints, and budgets are frozen before official runs.
- Skill evaluations use held-out initial states or random seeds.
- End-to-end evaluations begin from a clean game unless explicitly labeled otherwise.
- Test-run notebook contents do not carry into later independent runs.
- Every human intervention is counted and described.

## Minimum reported metrics

- Task success rate
- Median controller actions for successful runs
- Timeouts, blackouts, and loop detections
- Human interventions and manual resets
- Wall-clock time and aggregate emulator-hours, reported separately
- Training steps and random seeds
- Language-model calls, tokens, and cost when applicable
- Git commit, ROM fingerprint, software versions, and configuration

Shaped training return is a diagnostic metric, not proof that a task was solved.

## Comparison language

The language-model, RL, and hybrid configurations use different resources. Their comparison is an
engineering ablation, not automatically a fair contest. Claims must not use "learned from scratch,"
"screen-only," "autonomous," "no walkthrough," or "beat Pokémon" unless the exact protocol supports
those words.

## Artifact handling

The public repository may contain code, configuration, aggregated metrics, diagrams, and explicitly
reviewed traces. It must not contain ROMs, save data, private snapshots, API keys, absolute ROM
paths, or copyrighted game assets extracted from the ROM.
