# PPO training package architecture

`pokemon_red_ai.ppo_training` was a single 7,255-line module. It is now the
`pokemon_red_ai.ppo` package, and the old module remains as a re-export shim so
every existing import path still works.

## Why it was split

The module held every concern in the training loop at once: mode predicates,
atomic artifact writing, curriculum management, observation construction, the
Gymnasium environment, distillation datasets, promotion, dashboard rendering,
and a 2,804-line callback class. Nothing about that was accidental — it grew one
study at a time, and each addition was individually reasonable. The result was
still a file no reviewer could hold in their head.

## Module map

| Module | Responsibility | Lines |
| --- | --- | ---: |
| `constants.py` | Protocol strings, field tables, observation dimensions, RL handles | ~220 |
| `modes.py` | Training-mode predicates and per-mode protocol selection | ~145 |
| `artifacts.py` | Atomic writes, canonical hashing, run-artifact integrity | ~230 |
| `telemetry.py` | Run counters, learning-state validation, control exceptions | ~240 |
| `observations.py` | Observation vectors and per-episode trackers | ~285 |
| `config.py` | `ParallelPpoConfig`, `PpoEnvironmentConfig` | ~245 |
| `state_io.py` | Self-skill and student-practice checkpoint/restore | ~290 |
| `curriculum.py` | Verified-curriculum import, freeze, retain, round-trip | ~590 |
| `environment.py` | `PokemonRedPpoEnvironment` and its feature extractor | ~595 |
| `distillation.py` | Replay signatures, datasets, self-imitation training | ~1020 |
| `promotion.py` | Candidate verification, admission, warm start | ~230 |
| `dashboard.py` | Run-status HTML rendering | ~170 |
| `callback*.py` | The training callback, split across five mixins | ~420 + mixins |
| `runner.py` | `run_parallel_ppo` and the stop/status entry points | ~645 |

## The callback

`PpoRunCallback` was 2,804 lines in one class. Its methods now live in mixins
grouped by responsibility:

- `StatusReportingMixin` — status payloads, narrative, dashboard data
- `RunPersistenceMixin` — checkpoints, ledgers, status artifacts
- `ExplorerRecoveryMixin` — explorer-loop recovery bookkeeping
- `V8DistillationMixin` — student datasets, training, frozen composition replay
- `V9PracticeMixin` — the v9 practice loop
- `V12EvaluationMixin` — terminal exams, blank-goal probes, hindsight

The concrete class keeps construction, the Stable-Baselines3 hooks, and
candidate handling — the parts that decide *when* everything else runs.

Method bodies were moved verbatim. `self` resolution and attribute access are
unchanged, and no method name is duplicated across mixins, so MRO order is not
load-bearing. A test asserts that last property.

## What changed for callers

Nothing, by design. `from pokemon_red_ai.ppo_training import X` still works for
all 144 previously importable names, and `tests/test_ppo_package_structure.py`
asserts the shim exposes the identical objects rather than copies.

The one thing that did change: **tests that monkeypatch a module-level name must
now patch the module that resolves it**, not the shim. When everything lived in
one namespace, `monkeypatch.setattr(ppo_training, "route_guidance", ...)` worked
because that was the namespace the code read from. Now `route_guidance` is
resolved in `ppo.observations`, so that is where it must be patched. This is the
standard "patch where it is looked up" rule; eleven call sites in
`tests/test_ppo_training.py` were updated accordingly.

## Keeping it split

`tests/test_ppo_package_structure.py` enforces:

- no module exceeds 1,200 lines — split rather than raise the cap;
- every module has a docstring;
- the shim still re-exports the whole original surface, as the same objects;
- the callback still composes its mixins; and
- no two mixins define the same method name.
