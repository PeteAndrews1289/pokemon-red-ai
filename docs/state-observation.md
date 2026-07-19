# Read-only state instrumentation

## Purpose

The Phase 0 instrumentation snapshot is intentionally small. It lets the harness validate maps,
position, party size, and battles without exposing all of game memory or providing any way to alter
it. No acting agent consumes these fields yet. Phase 1 will separately declare which fields, if any,
belong in policy observation version 1 and which remain referee-only.

The observer reads only six named bytes:

| Public field | Pokémon Red symbol | Address | Meaning |
| --- | --- | ---: | --- |
| `game_started` | `wStatusFlags6` bit 0 | `0xD732` | The game session/play timer has begun |
| `map_id` | `wCurMap` | `0xD35E` | Numeric map identifier |
| `coordinates.y` | `wYCoord` | `0xD361` | Player tile Y coordinate |
| `coordinates.x` | `wXCoord` | `0xD362` | Player tile X coordinate |
| `party_count` | `wPartyCount` | `0xD163` | Number of Pokémon in the party |
| `battle_state` | `wIsInBattle` | `0xD057` | No battle, wild battle, trainer battle, or loss transition |

The raw status byte is masked to one boolean and is never returned. Until `game_started` is true,
the other fields are returned as unavailable. This matters because the bedroom map and coordinates
are already present in RAM behind Professor Oak's introduction and otherwise look playable.

`battle_state` is interpreted as `0` for no battle, `1` for wild, `2` for trainer, and `255` for a
loss/blackout transition. Unknown values are preserved and labeled `unknown` rather than guessed.

## Boundaries and caveats

- The adapter has a read-one-byte interface and no memory-writing method.
- These addresses apply only to the exact supported ROM hash.
- The start flag means the session began; it is not a promise that the game is waiting for input at
  that exact frame.
- Coordinates are tile coordinates. At outdoor map connections they can briefly contain a boundary
  value while the map changes.
- A party count of zero is valid before the player chooses a starter.
- Menu and text scratch variables are deliberately excluded because they can remain stale.
- Map names, event flags, species, opponent data, text identifiers, and raw memory are not exposed.

Instrumentation fields should be sampled at controller action boundaries. A future policy
observation schema may select carefully justified fields, but it receives its own version and must
not silently redefine this instrumentation snapshot.

The clean-boot test separately checks the bedroom's map-script state and input-ignore byte to prove
the final frame accepts controller input. Those map-specific assertions are not exposed to an agent.

## Verification source

The symbols were generated from
[`pret/pokered` commit `1e960340`](https://github.com/pret/pokered/tree/1e96034092686d006e863cace09e87273051a3d8).
A local build produced SHA-1 `ea9bcae617fdf159b045185467ae58b2e4a48b9a`, matching the
supported ROM exactly. Primary references are
[`ram/wram.asm`](https://github.com/pret/pokered/blob/1e96034092686d006e863cace09e87273051a3d8/ram/wram.asm),
[`constants/ram_constants.asm`](https://github.com/pret/pokered/blob/1e96034092686d006e863cace09e87273051a3d8/constants/ram_constants.asm),
and [`roms.sha1`](https://github.com/pret/pokered/blob/1e96034092686d006e863cace09e87273051a3d8/roms.sha1).
