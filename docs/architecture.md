# Architecture

## Design goal

Build one reproducible harness that can compare a language-model controller, a trained RL policy,
and a hybrid system without changing the emulator or evaluation rules underneath them.

## Component boundaries

```text
Pokemon Red / PyBoy
        |
        v
Observation adapter -----> Referee and metrics
        |
        +-----> Planner -----> Skill selector -----+
        |                                           |
        +-----> Trained navigation/battle skills ---+--> Executor --> PyBoy
        |                                           |
        +-----> Persistent map and notebook <-------+
                                                    |
                                      Loop watchdog-+
```

### Emulator harness

Owns the private ROM stream, PyBoy lifecycle, controller timing, screenshots, logical frame count,
and in-memory snapshots. It never saves cartridge RAM beside the ROM and exposes no memory-writing
method.

### Observation adapter

Converts emulator state into an explicit, versioned observation. The initial instrumented track is
expected to include a screenshot, visible text, an anonymous map identifier, tile coordinates, and
limited party state. Observation fields must be documented individually.

Version 1 currently exposes only a game-start gate, anonymous map identifier, tile coordinates,
party count, and battle state. See [state-observation.md](state-observation.md) for the exact fields
and caveats.

### Planner

Chooses bounded goals such as exploring until a map transition or navigating to a previously
discovered doorway. It does not act every frame and cannot load snapshots, alter memory, or write
directly to the emulator.

### Skills

Execute bounded navigation and battle tasks. The first learned baseline will use PPO, but the
interface should permit deterministic and alternative learned implementations.

### Memory

Stores discovered map connections, evidence-backed facts, recent outcomes, and known failure
patterns. Official evaluation runs begin with empty run-specific memory unless a continual-learning
protocol is declared in advance.

### Executor and watchdog

The executor is the only agent-facing component allowed to request controller inputs. The watchdog
detects repeated screens, position cycles, and exhausted action budgets. During official evaluation
it may request replanning or terminate a run; it may not teleport or silently reload.

### Referee

Uses a separately declared set of read-only RAM fields to score progress and terminate tasks. Data
visible only to the referee must never leak into policy observations.

### Recorder

Writes JSONL events, metrics, and optional screenshots under ignored artifact directories. Traces
contain hashes and relative artifact references—not ROM paths, ROM bytes, raw save states, or secret
values.

## Reproducibility invariants

- A run is bound to one exact ROM SHA-256 and PyBoy version.
- Snapshots are accepted only when their payload hash, ROM hash, and PyBoy version match their
  metadata and the running emulator.
- Save/load occurs at neutral controller boundaries.
- Logical frame count rewinds with a snapshot even though PyBoy's own counter does not.
- Every action has explicit hold and release durations.
- Official prompts, checkpoints, and evaluation budgets are frozen before evaluation.
