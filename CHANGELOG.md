# Changelog

This project records milestones, not just software releases. A version is considered meaningful
only when its behavior and evidence can be reproduced from the corresponding Git commit.

## Unreleased

### Added

- Standalone visual HTML reports generated from sanitized smoke/bootstrap traces
- Documentation hub, narrative, evidence board, detailed roadmap, and visual storytelling guide
- Episode 0 YouTube production outline and plain-language glossary
- Experiment-record and agent-card templates
- GitHub experiment issue form and reproducibility-focused pull request template
- Automated local-document link and placeholder checks

### Planned

- Human Oak's Parcel baseline and action recorder
- Gymnasium-compatible environment boundary
- Random-action stability test and loop detector
- First deliberately weak navigation baseline

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
