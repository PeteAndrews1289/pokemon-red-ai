# Development log

## 2026-07-19 — Random baseline retired; Evolutionary Explorer designed

### Evidence changed the plan

- Concluded that Pure Monkey had answered its question: a fixed uniform action distribution can
  create lucky game progress, but it cannot retain or amplify that success.
- Retired Monkey from future headline arenas while preserving its command, artifacts, and role as
  the reproducible random baseline.
- Gracefully ended the active four-lane pretrial rather than spend the remaining budget on an
  obsolete comparison. All four final checkpoints and narrative artifacts were preserved.

### Evolutionary decision

- Chose fixed-topology, mutation-only neuroevolution for version 1 rather than starting with NEAT
  topology growth and crossover.
- Chose MAP-Elites-style quality diversity instead of allowing one scalar-score dynasty to erase
  behaviorally different champions.
- Split evidence into clean-start policy evolution and checkpoint-assisted expedition modes.
- Required every promoted checkpoint-assisted milestone to replay its full ancestral action lineage
  from power-on.
- Specified a small recurrent pixel policy, four-worker evaluation queue, immutable genealogy,
  milestone-first selection, dashboard family tree, and bounded calibration sequence.

### Next

1. Implement deterministic recurrent inference and genome round trips.
2. Implement mutation, archive replacement, genealogy, and resume tests.
3. Qualify 16-candidate and 128-candidate populations before changing the living arena.

## 2026-07-19 — Game-naive direction and first curiosity runner

### Decisions

- Made pixels-only curiosity the primary experimental track.
- Defined Monkey, Curious, and Archivist arms so random luck, learned novelty seeking, and
  snapshot-assisted archive search can be compared instead of conflated.
- Started every strict run at clean power-on; the scripted bedroom bootstrap remains calibration.
- Prohibited RAM, tile data, OCR, semantic rewards, walkthroughs, demonstrations, and language-model
  calls from the action/reward loop.
- Chose a non-neural visual archive as the first learner because it can produce millions of local
  decisions overnight without additional downloads or model usage.

### Implemented and calibrated

- Added a narrow pixels-and-buttons runner capability with no public privileged emulator methods;
  the current button sampler itself receives only a seeded pseudorandom-number generator.
- Added a frozen 20×18 quantized pixel-cell representation and bounded first-visit reward.
- Added compressed snapshot lineage, under-visited archive selection, deterministic seeds,
  recoverable checkpoints, and time/action/disk limits.
- Added a self-contained live dashboard showing the information contract, discovery curve, action
  histogram, latest screen, and discovery reel.
- A 5,000-action calibration completed in about 19 seconds, found 591 coarse visual cells, retained
  a 591-cell archive in 4.4 MiB, and reached the name-entry interface without any game-state reward.

### Next

1. Run matched overnight Monkey and Archivist development arms.
2. Inspect whether visual novelty represents progress, text variation, or animation farming.
3. Freeze the next visual-cell version only after the failure evidence is understood.

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
