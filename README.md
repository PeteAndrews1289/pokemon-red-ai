# Pokémon Red AI

A transparent experiment in teaching an AI agent to play Pokémon Red.

The planned system combines a language model for high-level planning, trained reinforcement-
learning skills for execution, persistent memory, and a watchdog that detects loops. The immediate
goal is smaller: build a reliable emulator harness, then work toward delivering Oak's Parcel and
defeating Brock.

> **Project status:** Phase 0 — emulator harness and reproducibility groundwork.

## What makes this project different?

The goal is not merely to produce one successful run. It is to make the agent's behavior
inspectable and the results reproducible. The project will record:

- What the agent could observe
- Which component chose each action
- What the agent remembered
- When human intervention occurred
- Training time, emulator steps, language-model usage, and cost
- Every official evaluation attempt, not only the best run

This begins as an instrumented experiment, not a screen-only challenge. Emulator memory may be
read for observation, scoring, and debugging; every use will be documented explicitly.

## Planned architecture

- **Planner:** chooses goals and strategies
- **Skills:** execute navigation and battle behaviors
- **Memory:** stores discoveries, map connections, and failed approaches
- **Executor:** converts decisions into controller inputs
- **Watchdog:** detects repeated actions and unproductive loops
- **Referee:** measures progress without controlling the agent
- **Recorder:** saves sanitized traces, metrics, and video-ready artifacts

The project will eventually compare three configurations:

1. Language-model only
2. Reinforcement-learning only
3. Hybrid planner plus trained skills

See [the architecture document](docs/architecture.md) for the component boundaries.

## Current Phase 0 features

- Exact ROM revision validation before emulation starts
- Headless, unlimited-speed PyBoy wrapper
- Explicit press/release controller timing
- In-memory save-state snapshots with integrity hashes
- PNG screenshots and sanitized JSONL traces
- Read-only memory access at the harness boundary
- A deterministic clean boot to RED's bedroom, using the built-in RED and BLUE names
- A versioned six-field read-only state observation
- Unit and opt-in private-ROM integration tests
- CI guard against accidentally committing ROMs or save data

## Quick start

Requirements:

- Python 3.11 or newer
- A legally obtained supported Pokémon Red ROM
- macOS, Linux, or Windows with a PyBoy-supported Python build

```bash
git clone https://github.com/YOUR_USERNAME/pokemon-red-ai.git
cd pokemon-red-ai

python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
```

Keep the ROM outside the repository and provide its path at runtime:

```bash
export POKEMON_RED_ROM="/absolute/path/to/Pokemon Red.gb"

pokemon-red-ai doctor
pokemon-red-ai smoke-test
pokemon-red-ai bootstrap-test
```

You can use `--rom "/absolute/path/to/Pokemon Red.gb"` instead of the environment variable.
Generated screenshots and traces go under `runs/`, which Git ignores.

Run the test and safety checks:

```bash
python scripts/check_private_artifacts.py
ruff check .
pytest -m "not integration"
pytest -m integration  # Requires POKEMON_RED_ROM
```

The larger RL stack is optional until training begins:

```bash
python -m pip install -e ".[rl]"
```

No OpenAI API key is needed for Phase 0. Language-model setup will be added when the planner is
implemented.

## Supported ROM

**The ROM is not included in this repository.** The Phase 0 harness supports exactly:

```text
Title:   POKEMON RED
Size:    1,048,576 bytes
SHA-1:   ea9bcae617fdf159b045185467ae58b2e4a48b9a
SHA-256: 5ca7ba01642a3b27b0cc0b5349b52792795b62d3ed977e98a09390659af96b7b
```

The filename is not used as proof of identity. Other revisions may use different memory layouts
and save states, so the harness refuses them until they are deliberately supported.

## Roadmap

### Phase 0 — Emulator harness

- [x] Verify the target ROM fingerprint
- [x] Boot the ROM headlessly in PyBoy
- [x] Add controller, screenshot, save-state, and trace primitives
- [x] Prevent ROM and save artifacts from entering Git
- [x] Define and test named read-only game-state fields
- [x] Reproducibly reach the first playable bedroom state
- [x] Calibrate one-tile overworld controller timing at the bedroom start
- [ ] Record a human Oak's Parcel baseline
- [ ] Run an extended random-action stability test

### Phase 1 — Oak's Parcel

- [ ] Leave the bedroom and house
- [ ] Trigger Professor Oak
- [ ] Choose a starter
- [ ] Complete the first rival battle
- [ ] Reach Viridian City
- [ ] Collect and return Oak's Parcel

### Phase 2 — Brock

- [ ] Navigate Route 1 and Viridian Forest
- [ ] Train reusable navigation and battle skills
- [ ] Integrate planner, memory, and watchdog
- [ ] Defeat Brock from a clean game start

### Later experiments

- [ ] Compare language-model, RL, and hybrid agents
- [ ] Test stricter observation settings
- [ ] Run held-out evaluations across multiple seeds
- [ ] Explore a full-game run

## Reproducibility rules

Each reported experiment should identify its Git commit, configuration, ROM fingerprint, random
seeds, training budget, model usage, success criteria, and intervention count. Development save
states may accelerate training, but official end-to-end evaluations begin from a clean game unless
clearly stated otherwise.

The full rules are in [docs/experiment-protocol.md](docs/experiment-protocol.md).

## Legal and project hygiene

Pokémon is owned by Nintendo, Game Freak, and The Pokémon Company. This is an independent
educational and research project and is not affiliated with or endorsed by them.

This repository does not distribute game ROMs or proprietary game assets. Contributors are
responsible for obtaining and using game software in accordance with applicable law. Never commit
ROMs, save files, emulator states, API keys, private machine paths, checkpoints, or recordings.

## Development log

Decisions and milestones are recorded in [docs/devlog.md](docs/devlog.md).
The exact initial RAM observation and its limits are documented in
[docs/state-observation.md](docs/state-observation.md).
