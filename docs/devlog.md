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
