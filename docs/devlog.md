# Development log

## 2026-07-18 — Project start

### Decisions

- Selected Pokémon Red US Rev. 0 and pinned its SHA-256, SHA-1, size, and cartridge title.
- Selected PyBoy 2.7.0. PyBoy 2.7.1 is not used because that release was withdrawn after a
  Pokémon Red/Blue regression.
- Kept the ROM outside the repository and designed the harness to open it as a private binary
  stream.
- Chose sanitized JSONL traces and in-memory save states for Phase 0.
- Kept the RL dependency stack optional until the training phase.

### Verified locally

- The supplied ROM matches the supported fingerprint exactly.
- PyBoy 2.7.0 installs and boots the ROM on Python 3.14 and Apple Silicon.
- PyBoy exposes a 160 by 144 RGBA screen and the Pokémon Gen 1 game wrapper.
- The committed doctor command passes against the private ROM.
- The smoke test reaches the title, presses Start, opens the New Game menu, and restores the title
  from an in-memory snapshot deterministically.
- The generated JSONL trace contains no absolute path, Downloads directory, or ROM filename.
- All 13 unit and private-ROM integration tests pass; lint and the private-artifact guard pass.
- A frozen clean-boot sequence selects the built-in RED and BLUE names and reaches the bedroom
  reproducibly at logical frame 9,804.
- Six read-only WRAM fields were verified against a matching build of `pret/pokered`; pre-game
  scratch values are hidden until the game-start flag is set.
- The default 8-frame hold and 16-frame release moved RED exactly one tile down at the first
  playable bedroom state, then an in-memory snapshot restored the untouched starting point.

### Next

1. Build the human action recorder for the Oak's Parcel baseline.
2. Define the first Gymnasium-compatible observation and action space.
3. Add loop detection for repeated screens and coordinate cycles.

## 2026-07-19 — Public baseline

### Published

- Created the public `PeteAndrews1289/pokemon-red-ai` repository under the MIT license.
- Published the verified Phase 0 harness on `main` before beginning model-training claims.
- Used the GitHub private commit address so the local personal email is not exposed in history.

### Documentation direction

- Treat the project as both an engineering experiment and a documented story.
- Keep infrastructure, training, and evaluation progress visually distinct.
- Generate local run reports from sanitized traces while keeping gameplay captures outside Git.
- Preserve failed attempts and interventions so a future video can show the real learning process,
  not only a successful montage.

### Verified on the documentation branch

- The expanded suite contains 25 passing unit and private-ROM integration tests.
- Trace manifests now identify the source commit, worktree state, run class, actor, start condition,
  schemas, and intervention count without recording a checkout path.
- The report generator keeps training and evaluation evidence separate, bounds large traces, escapes
  content, redacts common sensitive forms, and refuses to overwrite its source trace.
- A reviewed public Phase 0 trace and standalone report make the repeated calibration claim
  inspectable without publishing gameplay images or snapshot payloads.
