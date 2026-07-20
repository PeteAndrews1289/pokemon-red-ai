# Read-only state instrumentation

## Purpose

The read-only state adapter began as a six-field Phase 0 instrument and now also supplies the sealed
training referee with declared collection and party progress. It never provides a memory-writing
method. Pixels-only policies consume none of these fields; the trainer may use the expanded fields
for reward, curriculum, replay verification, and reporting under an explicitly labeled protocol.

The original six public fields remain:

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

The expanded referee additionally reads badges, party species/levels/moves, Pokédex bitfields,
event flags, bag item identifiers, and the Pokédex story flag. Parallel PPO version 3 adds each
party member's three-byte `MON_EXP` value at offset 14 of the 44-byte `wPartyMons` structure. Those
bytes are decoded in big-endian order and exposed as `party_experience`; their sum is
`total_party_experience`. Experience remains trainer-only in pixels mode. It is used to distinguish
a battle with durable growth from merely fleeing or closing the battle interface.

## Boundaries and caveats

- The adapter has a read-one-byte interface and no memory-writing method.
- These addresses apply only to the exact supported ROM hash.
- The start flag means the session began; it is not a promise that the game is waiting for input at
  that exact frame.
- Coordinates are tile coordinates. At outdoor map connections they can briefly contain a boundary
  value while the map changes.
- A party count of zero is valid before the player chooses a starter.
- Menu and text scratch variables are deliberately excluded because they can remain stale.
- Opponent data, text identifiers, arbitrary raw memory, and memory mutation remain excluded.

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
[`constants/pokemon_data_constants.asm`](https://github.com/pret/pokered/blob/1e96034092686d006e863cace09e87273051a3d8/constants/pokemon_data_constants.asm),
[`constants/ram_constants.asm`](https://github.com/pret/pokered/blob/1e96034092686d006e863cace09e87273051a3d8/constants/ram_constants.asm),
and [`roms.sha1`](https://github.com/pret/pokered/blob/1e96034092686d006e863cace09e87273051a3d8/roms.sha1).
