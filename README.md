# Pokémon Red AI

[![CI](https://github.com/PeteAndrews1289/pokemon-red-ai/actions/workflows/ci.yml/badge.svg)](https://github.com/PeteAndrews1289/pokemon-red-ai/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

**How far can an agent get in Pokémon Red when nobody tells it what Pokémon is?**

This is a transparent, reproducible Pokémon Red learning project. Every experiment separately
discloses what chooses buttons, what that component observes, and what its training system may know.
The original game-naive, pixels-only condition remains a strict control. The current Q0/Q1
completion search deliberately starts with a seeded random action emitter and a sealed, read-only
referee; later trials will compare learned pixel actors under the same checkpoint and replay rules.

> **Current status: the six-lane selection × mutation follow-up is complete and every tested
> condition failed its next-map gate.** All six conditions spent equal 1,536,000-action budgets and
> remained on one map with no party member. Frontier selection retained the known title-sequence
> behavior far better than uniform selection, but retention did not become progress. The
> [Hall of Fame completion program](docs/completion-program.md) now has 55 named milestones, a
> content-addressed checkpoint/action-lineage store, and a bounded single-writer runner. A real-ROM
> Q0 qualification replayed every admitted state exactly and survived a graceful stop/resume. It
> reached Oak's introduction, not the first playable milestone; Q1 and every learning claim remain
> open.

The current code preserves every historical runner, including Monkey, Archivist, online learners,
and clean-start neuroevolution, so rejected approaches remain reproducible. See
[the selection × mutation lab](docs/selection-mutation-lab.md) for the concluded matrix and
[the decision register](docs/decision-register.md) for every accepted, retired, superseded, and
failed-to-qualify choice.

## The story so far

Pokémon Red looks simple because a person brings an enormous amount of invisible knowledge: what a
door looks like, how dialogue advances, why walking in circles is bad, and which tiny victories
matter on the way to a distant goal. An agent has none of that for free.

Before asking whether a model can learn, this project asks a less glamorous question: **can we trust
the test?** A surprising amount has to be settled first—one exact ROM revision, deterministic button
timing, clean start states, observation boundaries, private artifact handling, and a record of every
attempt. That foundation is Act I of the project, not backstage work to be edited out later.

The primary completion protocol is the
[Hall of Fame completion program](docs/completion-program.md). The original
[game-naive, pixels-only curiosity](docs/blind-curiosity.md) protocol remains the philosophical
control. The editorial direction lives in [The project narrative](docs/narrative.md), and evidence
levels remain tracked in [Progress](docs/progress.md).

## At a glance

| Question | Current answer |
| --- | --- |
| Is there a trained neural Pokémon-playing model yet? | A neural population inherited game-start behavior, but there is no evaluated successful Pokémon-playing policy yet |
| Can a game-naive agent explore from power-on? | Yes: random, archive, and online pixels-only runners have been exercised |
| Why retire Pure Monkey? | Its action distribution never changes; lucky outcomes cannot become future behavior |
| What replaced it? | A quality-diversity neuroevolution population proved narrow inheritance, then failed to extend it beyond the opening |
| What guides the Archivist trainer? | Coarse pixels, novelty membership, and archive visit counts |
| Does RAM guide every arm? | No. Every run declares actor and training information separately; the completion referee may guide training but never chooses buttons |
| Does the supplied game boot and accept controlled input? | Yes |
| Can a clean run reach the first playable bedroom state? | Yes, deterministically |
| Can the harness identify map, position, party size, and battle state? | Yes, read-only |
| Are ROMs, saves, snapshots, and gameplay captures committed? | No |
| Preserved random comparison | Monkey vs. pixels-only Archivist under matched budgets |
| Completed 90-minute pretrial | Evolution reached tier 1; online learners plateaued around Pallet Town and Route 1 |
| Concluded neural experiment | Six inherited-archive lanes all failed the second-map/party gate under equal fuel |
| Current completion work | Q1 multi-seed house-exit search after a qualified private frontier runner and deterministic power-on replay |
| North star | First discover a replayable Hall-of-Fame lineage, then train and evaluate one frozen pixel policy |

## The journey

```mermaid
flowchart LR
    P0["✅ Harness<br/>trust the stage"] --> B0["✅ Monkey<br/>baseline concluded"]
    B0 --> B2["✅ Online learners<br/>pretrials"]
    B2 --> B1["✅ First inheritance<br/>repeat game start"]
    B1 --> EV["✅ 2 × 3 mechanism lab<br/>no next-map progress"]
    EV --> EX["✅ Q0 checkpoint runner<br/>remember stepping stones"]
    EX --> Q1["🟨 Q1 house exit<br/>two fresh seeds"]
    Q1 --> FR["⬜ Complete lineage<br/>then one frozen policy"]
```

GitHub issues and experiment records will attach evidence to this roadmap. A checked engineering
task is not automatically model progress; the [detailed roadmap](docs/roadmap.md) keeps those tracks
separate.

## What Phase 0 proves

- The target ROM is identified by exact title, size, SHA-1, and SHA-256 before emulation starts.
- PyBoy runs headlessly at unlimited speed without writing save data beside the private ROM.
- Every controller action has explicit hold and release durations.
- In-memory snapshots are integrity-checked and bound to the ROM hash and PyBoy version.
- A frozen input sequence reaches RED's bedroom at logical frame 9,804.
- Two independent clean boots produce identical state, pixels, game-area, and snapshot hashes.
- An 8-frame press plus 16-frame release moves RED exactly one tile at the bedroom start.
- The current instrumentation reader exposes six named fields and no memory-writing method.
- Pre-game scratch values are hidden so Oak's introduction cannot masquerade as playable state.
- Sanitized JSONL traces contain reproducibility hashes, not ROM paths or bytes.
- CI rejects common ROM, save, snapshot, private-path, and documentation mistakes.

These claims are covered by the unit and private-ROM integration test suite. They do **not** imply
that an agent has learned navigation, understood the screen, or completed a quest.

## Primary completion system

```mermaid
flowchart LR
    Game["Pokémon Red"] --> Pixels["Rendered RGB only"]
    Pixels -. "future learned input" .-> Emitter["Discovery emitter"]
    RNG["Seeded RNG<br/>current Q0/Q1"] --> Emitter
    Emitter --> Act["Controller buttons"]
    Act --> Game
    Game --> Referee["Sealed read-only referee"]
    Referee --> Archive["Verified frontier archive"]
    Archive --> Restore["Training-only checkpoint restore"]
    Restore --> Game
    Archive --> Replay["Complete power-on lineage replay"]
    Replay --> Story["Evidence + failures + narrative"]
```

The actor never receives RAM, checkpoint bytes, milestone names, or a route. The current Q0/Q1
qualification emitter receives only a seeded pseudorandom generator; it is an open-loop discovery
baseline, not a learned model and not yet a pixel actor. Later visual policies will receive rendered
pixels under a separate label. RAM-derived state may influence training reward, archive selection,
curriculum, and failure termination through the declared referee. Checkpoint restores are
trainer-owned and disclosed; they are disabled when evaluating one frozen model from power-on. See
[the experiment protocol](docs/experiment-protocol.md) and
[the completion program](docs/completion-program.md).

## What will count as progress?

The project uses the canonical [Progress evidence ladder](docs/progress.md#evidence-ladder) so a
polished clip cannot outrank a repeatable result.

| Level | Meaning | Example |
| --- | --- | --- |
| E0 — Proposed | A written design or roadmap item | Proposed reward function |
| E1 — Implemented | Code and a documented interface | Environment wrapper exists |
| E2 — Checked | Automated unit, integration, lint, or safety check | One-tile timing test passes |
| E3 — Repeated | Reproducible run artifacts with matching declared outcomes | Two clean boots agree |
| E4 — Evaluated | Frozen policy, budget, all attempts, and aggregate metrics | 17/20 held-out attempts |

Every public experiment should state its observation track, training budget, evaluation attempts,
interventions, failures, model usage, cost, and Git commit. Shaped reward is useful diagnostic data;
it is not proof that a task was solved.

## Documentation map

Start with [the documentation hub](docs/index.md), or jump directly to:

- [Project narrative](docs/narrative.md) — the central question and story arc
- [Blind curiosity protocol](docs/blind-curiosity.md) — pixels-only rules, novelty, archive, and run guide
- [Evolutionary Explorer](docs/neuroevolution.md) — how genomes, mutation, selection, and lineage worked, plus the checkpoint successor they motivated
- [Selection × mutation lab](docs/selection-mutation-lab.md) — the concluded 90-minute evidence, completed six-lane fork, and failed next-map gate
- [Hall of Fame completion program](docs/completion-program.md) — the checkpoint expedition, claim ladder, qualification gates, and path to one learned policy
- [Append-only decision register](docs/decision-register.md) — accepted, rejected, retired, superseded, and failed ideas with their evidence
- [Progress](docs/progress.md) — current evidence, status, and reporting rules
- [Roadmap](docs/roadmap.md) — engineering, learning, and storytelling milestones
- [Architecture](docs/architecture.md) — components, data flow, and authority boundaries
- [Experiment protocol](docs/experiment-protocol.md) — what claims require what evidence
- [State instrumentation](docs/state-observation.md) — exact read-only fields and caveats
- [Run reports](docs/run-reports.md) — turning traces into local visual summaries
- [Video outline](docs/video-outline.md) — a possible YouTube structure and shot plan
- [Visual storytelling](docs/visual-storytelling.md) — charts and visuals worth collecting
- [Glossary](docs/glossary.md) — technical ideas in audience-friendly language
- [Development log](docs/devlog.md) and [changelog](CHANGELOG.md) — what changed and why

Reusable records:

- [Experiment record template](docs/experiment-template.md)
- [Agent card template](docs/agent-card-template.md)

## Reproduce the current milestone

### Requirements

- Python 3.11 or newer
- A legally obtained Pokémon Red ROM matching the supported fingerprint below
- macOS, Linux, or Windows with a PyBoy-supported Python build

```bash
git clone https://github.com/PeteAndrews1289/pokemon-red-ai.git
cd pokemon-red-ai

python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
```

On Windows PowerShell, create and activate the environment with:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
py -m pip install -e ".[dev]"
```

Keep the ROM outside the repository and provide its path only at runtime:

```bash
export POKEMON_RED_ROM="/absolute/path/to/Pokemon Red.gb"

pokemon-red-ai doctor
pokemon-red-ai smoke-test
pokemon-red-ai bootstrap-test
```

The bootstrap test starts two clean games, compares the outcomes, verifies the input-ready bedroom
state, calibrates one-tile movement, and restores the untouched starting snapshot. Generated traces
and private screenshots go under `runs/`, which Git ignores.

Turn any smoke or bootstrap trace into a standalone visual report:

```bash
pokemon-red-ai report runs/bootstrap-YYYYMMDDTHHMMSSZ
```

The resulting `report.html` explains the manifest, outcome, repeated attempts, timeline, and the
important fact that these harness runs contain no model-training metrics. The generator does not
add screenshots, ROM assets, JavaScript, or remote dependencies; it redacts common sensitive
values, but reports still require review before publication. See [Run reports](docs/run-reports.md).

The reviewed, metadata-only evidence for the repeated Phase 0 run is published in
[experiments/phase-0-bootstrap](experiments/phase-0-bootstrap/README.md). It contains no gameplay
image or save state.

Use `--rom "/absolute/path/to/Pokemon Red.gb"` instead of the environment variable if preferred.
No OpenAI API key is needed for Phase 0.

Reproduce a bounded historical game-naive baseline directly from power-on:

```bash
pokemon-red-ai blind-run --mode monkey --hours 8 --max-actions 5000000
pokemon-red-ai blind-run --mode archivist --hours 8 --max-actions 5000000
```

Each run writes a live `index.html`, bounded screenshots, status, trace, and recoverable checkpoint
under ignored `runs/`. No OpenAI API key or reinforcement-learning download is required. See the
[blind curiosity protocol](docs/blind-curiosity.md) before interpreting or publishing a result.

The current `arena-run` command reproduces the concluded **successor pretrial** configuration:
Evolutionary Explorer plus the three online learners. Historical Monkey runs remain reproducible
through `blind-run --mode monkey` and their preserved artifacts. The ROM-backed six-lane mechanism
runner has passed a one-child-per-lane qualification: all six lanes imported the same 33-elite
archive, completed exactly 12,000 actions, wrote one genealogy record, and exited cleanly.

Run the paired 2 × 3 selection-by-mutation lab with one combined dashboard:

```bash
pokemon-red-ai evolution-lab-run \
  --output "/Volumes/External/PokemonRedAI/evolution-labs/selection-mutation-YYYYMMDD" \
  --seed-archive "/path/to/completed-pretrial/evolution" \
  --hours 4 \
  --max-actions-per-lane 1536000 \
  --seed 20260725 \
  --port 8765
```

The default matrix runs uniform/frontier selection × broad/gentle/multiscale mutation. All lanes
use the same archive, paired seed, 12,000-action child lifetime, and 1,536,000-action ceiling. Use
`evolution-lab-status PATH` to inspect it or `evolution-lab-stop PATH` for a graceful group stop.
The lab preserves a synchronized six-image frame set every ten minutes, exact first-milestone
screenshots with hashes, hourly Markdown comparisons, and JSONL evidence. After a reboot or
orchestrator interruption, repeat the identical command with `--resume`; configuration, source,
ROM, lane matrix, and predecessor hashes must all still match.

Run the bounded checkpoint expedition on an external SSD:

```bash
pokemon-red-ai expedition-run \
  --output "/Volumes/External/PokemonRedAI/expeditions/q1-seed-20260730" \
  --hours 1 \
  --max-actions 20000 \
  --seed 20260730 \
  --port 8765
```

The localhost dashboard exists only while the command is running; the finished `index.html`
remains in the run directory. Use `expedition-status PATH`, `expedition-stop PATH`, and repeat the
identical command with `--resume` after a graceful stop. The initial emitter is explicitly labeled
`RANDOM-ACTION-EMITTER`; archive selection remembers verified stepping stones, but this is not yet
one learned policy. Do not schedule a multi-day campaign until the multi-seed Q1 gate passes and
the replay/store scaling blockers in the completion program are addressed.

Historical reproducibility only: the command below is the retired 48-hour successor-arena design.
It is preserved so the earlier protocol can be audited, **not** as the current next run. Do not
launch it while the checkpoint expedition's Q1 and scaling gates remain open.

```bash
pokemon-red-ai arena-run \
  --output "/Volumes/T7 Developer/PokemonRedAI/arenas/four-agent-48h-YYYYMMDD" \
  --hours 48 \
  --max-actions 150000000 \
  --q-policy-buckets 1048576
```

If that historical arena is deliberately reproduced, its dashboard appears at
`http://127.0.0.1:8765/index.html`. Its recovery and storage controls do not remove the scientific
reason it was retired.
[The four-agent arena](docs/four-agent-arena.md) records both the historical protocol and the
replacement decision. [Evolutionary Explorer](docs/neuroevolution.md) defines the neural lane, and
[the selection × mutation lab](docs/selection-mutation-lab.md) preserves the concluded control.

## Supported ROM

**The ROM is not included in this repository.** The harness currently supports exactly:

```text
Title:   POKEMON RED
Size:    1,048,576 bytes
SHA-1:   ea9bcae617fdf159b045185467ae58b2e4a48b9a
SHA-256: 5ca7ba01642a3b27b0cc0b5349b52792795b62d3ed977e98a09390659af96b7b
```

The filename is not proof of identity. Other revisions can have different memory layouts and save
states, so the harness refuses them until they are deliberately supported. The named state fields
were checked against a matching build of
[`pret/pokered`](https://github.com/pret/pokered/tree/1e96034092686d006e863cace09e87273051a3d8).

## Development checks

```bash
python scripts/check_private_artifacts.py
python scripts/check_docs.py
ruff check .
pytest -m "not integration"
pytest -m integration  # Requires POKEMON_RED_ROM
```

The heavier reinforcement-learning stack remains optional because the current lightweight runners
do not require it:

```bash
python -m pip install -e ".[rl]"
```

See [Contributing](CONTRIBUTING.md) before adding observations, rewards, or published results.

## Legal and project hygiene

Pokémon is owned by Nintendo, Game Freak, and The Pokémon Company. This is an independent
educational and research project and is not affiliated with or endorsed by them.

The repository does not distribute ROMs, save data, emulator states, extracted game assets, or
gameplay recordings. Contributors are responsible for obtaining and using game software in
accordance with applicable law. Never commit ROMs, saves, snapshots, API keys, private machine
paths, checkpoints, or recordings.

The project code and original documentation are available under the [MIT License](LICENSE).
