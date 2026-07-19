# Changelog

## Unreleased — evolutionary successor decision

- Implemented the 13,096-parameter recurrent pixel policy, deterministic genome serialization,
  mutation-only reproduction, bounded quality-diversity archive, immutable genealogy, and resume
  checkpoints.
- Added a clean-start evolutionary runner and living family-tree dashboard; replaced Monkey with
  Evolutionary Explorer in the successor arena pretrial.
- Set the pretrial lifetime to 12,000 actions and the founding population to 16 genomes.
- Added an early action-profile diversity bin after a two-child qualification revealed archive
  collapse before either child reached a semantic milestone.
- Retired Pure Monkey from future headline arenas after it completed its role as a non-learning
  random baseline; retained its runner and artifacts for reproducibility.
- Specified Evolutionary Explorer as its planned replacement: a small recurrent pixels-only policy
  evolved through mutation-only, quality-diversity selection.
- Defined separate clean-start and checkpoint-assisted evidence tracks, with complete power-on
  lineage replay required for promoted expedition milestones.
- Added planned genome, archive, genealogy, dashboard, compute, storage, and qualification gates.
- Reframed the video narrative around the question, “What if a useful accident could reproduce?”

## Unreleased — discovery reward protocol

- Standardized all continuous agents on eight deterministic actions and removed Select.
- Added a sealed RAM referee for every lane without leaking its measurements into blind policies.
- Added Pokédex, event-flag, warp, party-level, move, item, and blackout measurements.
- Rebalanced generic outcome rewards away from local-coordinate farming.
- Added explicit Oak's Parcel, Pokédex, Poké Ball, key-item, and HM milestones for Conventional.
- Added mild repeated-action, revisitation, and stationary-loop penalties.
- Added per-component reward ledgers and richer live dashboard fields.
- Ignore temporary starter-preview Pokédex bits until the in-game Pokédex is obtained.

## Unreleased

- Scale the final arena to 1,048,576 policy buckets and a 150-million-action safety ceiling.
- Add 128-step returns, bounded uniform replay, and protected important-transition replay.
- Remove visual novelty from Outcome-Rewarded and Conventional reward channels.
- Capture exact screenshots and referee telemetry for semantic milestones.

This project records milestones, not just software releases. A version is considered meaningful
only when its behavior and evidence can be reproduced from the corresponding Git commit.

## Unreleased

### Added

- Game-naive pixels-only Monkey and visual-novelty Archivist runners from clean power-on
- Narrow actor capability exposing pixels and buttons but no RAM, tiles, snapshots, or raw emulator
- Bounded visual novelty, compressed discovery archive, action lineage, and deterministic seeds
- Atomic checkpoints plus wall-clock, action, archive, output-size, and free-disk safeguards
- Live visual dashboard with discovery curve, action distribution, latest screen, and discovery reel
- Blind-curiosity protocol covering leakage, honest claims, expected failures, and run controls
- Standalone visual HTML reports generated from sanitized smoke/bootstrap traces
- Reviewed public Phase 0 calibration evidence with a sanitized trace and generated report
- Documentation hub, narrative, evidence board, detailed roadmap, and visual storytelling guide
- Episode 0 YouTube production outline and plain-language glossary
- Experiment-record and agent-card templates
- GitHub experiment issue form and reproducibility-focused pull request template
- Automated local-document link and placeholder checks
- Git commit, dirty-worktree, actor, run-class, schema, start, and intervention provenance in traces
- Private home-path and common credential-pattern checks in the repository safety guard

### Planned

- Matched overnight Monkey and Archivist development runs
- Pixel-only learned curiosity policy without demonstrations or semantic rewards
- Sealed post-hoc referee for interpretation, visibly separate from training inputs
- Frozen restore-free power-on evaluations

## 0.1.0 — 2026-07-19

### Added

- Exact Pokémon Red US Rev. 0 ROM fingerprint validation
- Headless PyBoy 2.7.0 emulator lifecycle and controller timing
- In-memory, integrity-checked snapshots bound to the ROM and emulator version
- Sanitized JSONL traces and private local screenshots
- Deterministic clean boot through the RED and BLUE name menus
- Verified first playable bedroom state at logical frame 9,804
- Versioned, six-field read-only state observation
- One-tile controller calibration from the bedroom start
- Unit, private-ROM integration, lint, CI, and artifact-safety checks

### Evidence

- 13 tests passed on the development machine
- Two independent clean boots produced identical state, screen, game-area, and snapshot hashes
- No ROM, save data, private path, or generated gameplay image entered Git

The detailed engineering record is in [docs/devlog.md](docs/devlog.md). Future model results will
be reported separately from harness milestones so infrastructure progress cannot be mistaken for
learning progress.
