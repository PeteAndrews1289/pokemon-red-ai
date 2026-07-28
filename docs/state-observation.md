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

## V11 semantic-state arbitration

A byte can be read correctly and still describe a state the player has not reached. Canary 3 made
that distinction concrete. While Professor Oak's introduction was visibly on screen, initialized
WRAM already contained the future bedroom map, coordinates `(3,6)`, player data, and money. The
server combined those individually plausible values with a permissive dialogue detector, reported
`RedsHouse2f` and `overworld`, exposed a bedroom path to A*, and accepted the planner's unsupported
request to complete `pallet_000`. The run was stopped after 251.630 seconds and 50 ordinary
controller actions. Its apparent bedroom and Potion progress is rejected as a semantic-state
failure.

The primary-source audit explains the transition. `StartNewGame` runs Oak's speech before
`SpecialEnterMap` sets `BIT_GAME_TIMER_COUNTING` in `wStatusFlags6`; see the pinned
[`main_menu.asm` transition](https://github.com/pret/pokered/blob/405b6246372d7e5a2cb029cbb65219b13286b8c9/engine/menus/main_menu.asm#L321-L340).
The ordinary message box is a full-width rectangle from `(0,12)` through `(19,17)` in the 20×18
tile map, as declared by
[`data/text_boxes.asm`](https://github.com/pret/pokered/blob/405b6246372d7e5a2cb029cbb65219b13286b8c9/data/text_boxes.asm#L8-L15).
Its six border tiles are `0x79`–`0x7e`; `0x7f` is a space, not a border, in
[`constants/charmap.asm`](https://github.com/pret/pokered/blob/405b6246372d7e5a2cb029cbb65219b13286b8c9/constants/charmap.asm#L57-L63).
The structural detector therefore matches that exact topology even when OCR is disabled. Before
the start bit is set, the only valid high-level labels are `pregame` and a structurally detected
interaction such as `dialog`; a cached absence of dialogue may never promote the state to
`overworld`.

V11 enforces state truth in four layers rather than asking the planner to resolve contradictory
sensors:

1. **Detached reads.** The HTTP state endpoint and direct tools deep-copy the emulator's 100 ms
   cached state before adding maps, formatting fields, or serializing a response. Dashboard polling
   therefore cannot mutate the planner's simultaneous read.
2. **Started-bit and map gates.** Until `wStatusFlags6` bit 0 is set, player, party, money, and map
   fields remain unavailable. `/state`, `/whole_map`, MCP state/map reads, and navigation all fail
   closed; stale server map caches are cleared rather than allowed to restore the staged bedroom.
3. **Fail-closed formatting.** The formatter suppresses map text whenever `game_started` is false,
   even if an upstream regression labels the frame `overworld` or hands it a populated map object.
4. **Empirical control proof.** Static readiness is only a candidate. The first objective remains
   locked until an ordinary directional input produces a real coordinate change in the upstairs
   bedroom. A planner's completion request is never its own evidence.

Canary 4 qualified that opening boundary. At `2026-07-22T03:22:41Z`, RIGHT moved RED from `(3,6)`
to `(4,6)`; only after that observed transition could `pallet_000` complete, at 450.05 seconds and
111 actions. The bounded run ended after 600.521 supervisor seconds with 136 actions in
`RedsHouse2f (0,2)`, story index 1/84, no party, no badges, and no Hall-of-Fame result. A residual
server-only pre-game map leak found during the canary was then closed by applying the same gates to
the dashboard, map endpoint, formatter, and direct tools.

The continuous run `v11-continuous-20260721-233300` closed after 950.308 seconds, 329 actions, and
144 online model calls. It established neither sustained planning nor completion: the Hall of Fame
remains unverified. V12 returns actor input to rendered frames, recent actions, recurrent state,
and a self-generated or blank visual goal; trainer-only referee fields remain excluded from policy
observations.

The expanded referee additionally reads badges, party species/levels/moves, Pokédex bitfields,
event flags, bag item identifiers, and the Pokédex story flag. Parallel PPO version 3 adds each
party member's three-byte `MON_EXP` value at offset 14 of the 44-byte `wPartyMons` structure. Those
bytes are decoded in big-endian order and exposed as `party_experience`; their sum is
`total_party_experience`. Experience remains trainer-only in pixels mode. It is used to distinguish
a battle with durable growth from merely fleeing or closing the battle interface.

Parallel PPO version 4 adds current and maximum HP for each party member plus the active opponent's
current and maximum HP. Party HP uses `MON_HP` and `MON_MAXHP` offsets 1 and 34. Active opponent HP
uses the generated `wEnemyMonHP` (`0xCFE6`) and `wEnemyMonMaxHP` (`0xCFF4`) symbols. Opponent values
are returned only while `wIsInBattle` denotes a wild or trainer battle, avoiding stale battle
scratch data outside combat. These fields remain trainer-only in pixels mode.

Parallel PPO version 5 adds one narrowly scoped lesson instrument:
`wViridianMartCurScript` at `0xD60D`. It is read only while the current map is Viridian Mart
(`0x2A`), so stale script scratch data cannot appear outside that map. Stages 0, 1, and 2 represent
the default clerk sequence, the Oak's Parcel handoff sequence, and the completed/no-op stage. The
field is trainer-only and supplies bounded dialogue-progress reward; it is not part of the pixel
actor or the teacher's observation. The public milestone `entered_viridian_mart` depends only on
the current map ID, while Oak's Parcel still depends on its canonical item/event evidence.

## Boundaries and caveats

- The adapter has a read-one-byte interface and no memory-writing method.
- These addresses apply only to the exact supported ROM hash.
- The start flag means the session began; it is not a promise that the game is waiting for input at
  that exact frame.
- `wJoyIgnore == 0` means no individual button is masked; it is not a universal player-control bit.
  The game also has scripted movement, door-exit movement, and simulated-input states.
- Coordinates are tile coordinates. At outdoor map connections they can briefly contain a boundary
  value while the map changes.
- A party count of zero is valid before the player chooses a starter.
- Menu and text scratch variables are deliberately excluded because they can remain stale.
- Opponent identity, moves, text identifiers, arbitrary raw memory, and memory mutation remain
  excluded. Only active opponent HP/maximum HP and the map-scoped Viridian Mart script stage are
  exposed for their declared Version-4/Version-5 trainer rewards.

Instrumentation fields should be sampled at controller action boundaries. A future policy
observation schema may select carefully justified fields, but it receives its own version and must
not silently redefine this instrumentation snapshot.

The clean-boot test separately checks the bedroom's no-op map-script state and input-ignore byte as
static readiness evidence. It then requires an actual directional coordinate change as empirical
control proof. Those map-specific assertions are not exposed as planner-declared success.

## Verification source

The symbols were generated from
[`pret/pokered` commit `1e960340`](https://github.com/pret/pokered/tree/1e96034092686d006e863cace09e87273051a3d8).
A local build produced SHA-1 `ea9bcae617fdf159b045185467ae58b2e4a48b9a`, matching the
supported ROM exactly. Primary references are
[`ram/wram.asm`](https://github.com/pret/pokered/blob/1e96034092686d006e863cace09e87273051a3d8/ram/wram.asm),
[`constants/pokemon_data_constants.asm`](https://github.com/pret/pokered/blob/1e96034092686d006e863cace09e87273051a3d8/constants/pokemon_data_constants.asm),
[`constants/ram_constants.asm`](https://github.com/pret/pokered/blob/1e96034092686d006e863cace09e87273051a3d8/constants/ram_constants.asm),
and [`roms.sha1`](https://github.com/pret/pokered/blob/1e96034092686d006e863cace09e87273051a3d8/roms.sha1).

The V11 semantic-state audit independently rebuilt `pret/pokered` commit `405b6246` to the same
supported SHA-1 and used these line-pinned primary references:

- the generated-memory layout in
  [`ram/wram.asm`](https://github.com/pret/pokered/blob/405b6246372d7e5a2cb029cbb65219b13286b8c9/ram/wram.asm#L154-L184);
- the exact supported hashes in
  [`roms.sha1`](https://github.com/pret/pokered/blob/405b6246372d7e5a2cb029cbb65219b13286b8c9/roms.sha1);
- per-button masking in
  [`engine/joypad.asm`](https://github.com/pret/pokered/blob/405b6246372d7e5a2cb029cbb65219b13286b8c9/engine/joypad.asm#L22-L40);
- Pokémon Red's broader game-controlled-movement predicate in
  [`home/npc_movement.asm`](https://github.com/pret/pokered/blob/405b6246372d7e5a2cb029cbb65219b13286b8c9/home/npc_movement.asm#L1-L12); and
- the upstairs-bedroom transition to its no-op script in
  [`scripts/RedsHouse2F.asm`](https://github.com/pret/pokered/blob/405b6246372d7e5a2cb029cbb65219b13286b8c9/scripts/RedsHouse2F.asm#L1-L22).
