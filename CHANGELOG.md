# Changelog

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
