# Version 5.2: from one solved errand to the road to Brock

## Why this version exists

Version 5.1 answered its main question. Active-goal backtracking was not merely plausible: the run
reached Pallet Town with Oak's Parcel, entered the Lab, delivered the Parcel, and received the
Pokédex. All six new promotions passed one exact parent-edge replay and three complete power-on
replays. The verified lineage grew from 9,238 to 10,819 actions.

Then the system stopped advancing. For more than three million combined actions after receiving the
Pokédex, every worker repeatedly restored into Oak's Lab and ended in visual cycles or long
stagnation. The experiment had made the return trip legible, but the next chapter was still one
large jump called “reach Viridian Forest.”

That produces the next testable idea:

> If a long objective is decomposed into visible map-to-map lessons, can recurrent PPO compose a
> route beyond the opening errand instead of waiting for one lucky full traversal?

Version 5.2 is the first curriculum explicitly designed around a complete game chapter rather than
one local bug. Its bounded chapter is the journey from the Pokédex through Viridian Forest and into
Pewter Gym. Brock remains the evidence gate at the end.

## The completed Version-5.1 result

Version 5.1 ran from 5:11:21 PM to 9:23:02 PM EDT on 2026-07-20 and stopped cleanly when requested.
It completed 3,437,572 combined actions, 3,357 PPO updates, and 1,900 episodes in 15,101.119 seconds.

| Verified event | Combined action | Local time (EDT) | Complete lineage depth |
| --- | ---: | --- | ---: |
| Returned to Pallet Town with Oak's Parcel | 105,760 | 5:19:54 PM | inherited and extended |
| Entered Oak's Lab with Oak's Parcel | 123,068 | 5:21:44 PM | inherited and extended |
| Received the Pokédex | 402,320 | 5:43:08 PM | 10,819 actions |

The final result contained six verified promotions and zero promotion failures. It retained 1,076
unique positions. All 1,900 episodes were classified failures: 1,241 ended in long stagnation and
659 in visual cycles. The terminal PPO model and all four worker novelty memories matched their
checkpoint hashes. The final model SHA-256 was
`f586d6805067d443f9c32471d57be0d127671f2e7d05a43be7ac2131c4b60a13`.

The most important denominator begins at the Pokédex promotion. The run then spent 3,035,252 more
actions without reaching Viridian Forest and added only 305 globally new positions. That is not
evidence that PPO can never solve the route. It is evidence that this curriculum did not provide a
useful enough gradient for the post-Pokédex chapter.

## What the failure means

Version 5.1 did not fail at its own hypothesis. It taught the intended backtracking behavior and
converted it into replay-verified lineage. Its failure was one level higher: solving one fetch
quest did not automatically create a general planner.

The next target combined several different skills:

- leave an interior after dialogue or menu interaction;
- retrace familiar maps north;
- enter Route 2 through Viridian City;
- recognize and use the Forest south gate;
- navigate a large encounter-filled map;
- exit through a different gate;
- cross the north portion of Route 2;
- enter Pewter City and then the Gym; and
- fight Brock successfully.

Calling that entire chain one milestone hides where learning stops. More runtime under the same
label would produce a larger denominator but little diagnosis.

## The 66-step canonical curriculum

Version 5.2 inserts seven new replay-verifiable milestones without renumbering any curriculum entry
already verified through the Pokédex:

1. `left_oaks_lab_with_pokedex`
2. `returned_to_route_1_with_pokedex`
3. `returned_to_viridian_city_with_pokedex`
4. `reached_route_2_with_pokedex`
5. `entered_viridian_forest_south_gate`
6. `crossed_viridian_forest`
7. `entered_pewter_gym`

The pre-existing `reached_viridian_forest`, `reached_pewter_city`, and `boulder_badge` milestones
remain part of the sequence. The complete first-Gym chapter is therefore:

```mermaid
flowchart LR
    D["Pokédex<br/>Oak's Lab"] --> P["Pallet Town"]
    P --> R1["Route 1"]
    R1 --> V["Viridian City"]
    V --> R2S["Route 2 south"]
    R2S --> SG["Forest south gate"]
    SG --> F["Viridian Forest"]
    F --> NG["Forest north gate"]
    NG --> R2N["Route 2 north"]
    R2N --> C["Pewter City"]
    C --> G["Pewter Gym"]
    G --> B["Boulder Badge"]
```

Map milestones are observations, not scripted movement. A candidate is admitted only after the
same exact replay checks used by earlier versions. Merely receiving shaped route reward is not
named progress.

## Source-derived topology and its disclosure

The assisted trainer now knows seven additional map transitions through Pewter Gym. Their map IDs
come from the supported Pokémon Red disassembly:

| Map | ID |
| --- | ---: |
| Route 2 | `0x0D` |
| Viridian Forest north gate | `0x2F` |
| Viridian Forest south gate | `0x32` |
| Viridian Forest | `0x33` |
| Pewter Gym | `0x36` |

The trainer is allowed to tell the assisted actor the next map and bounded distance on this graph.
It does **not** supply a target coordinate, collision map, door tile, menu command, battle action,
or button sequence. Route 2 has one map ID on both sides of the Forest, so the north-gate-to-Pewter
route correctly passes through Route 2 before Pewter.

This is `ASSISTED-TRAINING`, not strict blindness. The assistance is intentionally public because
the project's goal is to distinguish what was learned from what was designed.

## Bounded navigation recovery

V5.1's post-Pokédex footage repeatedly froze on nearly unchanged screens inside Oak's Lab. Those
episodes can represent a menu, text box, wall, or other interaction trap. Giving the actor a direct
RAM flag saying “press B now” would turn the teacher into a controller. Version 5.2 instead uses a
general outcome signal:

- a landmark-navigation goal must be active;
- the player position must remain unchanged for at least 12 actions;
- battle must be inactive; and
- credit is paid only when movement actually resumes.

The recovery is worth +2 raw reward and is capped at three payments per episode. Waiting alone earns
nothing. The cap prevents a policy from manufacturing unlimited reward by deliberately stopping
and restarting. Because the policy is recurrent, the eventual movement reward can assign credit to
the preceding sequence that escaped the trap without the trainer naming a button.

This mechanism is deliberately modest. Its purpose is to make successful recovery learnable, not
to outweigh a named milestone or replace the existing visual-loop penalty.

## Reward and evidence boundaries

| Signal | Who can receive it? | What it proves |
| --- | --- | --- |
| Pixels, three recent actions, episodic map, active goal, next map/distance | Assisted actor | Declared training input only |
| Signed change in map distance | PPO trainer | Directional learning signal; not completion |
| Bounded recovery after resumed movement | PPO trainer | A trap was escaped; not why or how |
| New map, warp, position, event, item, species, battle progress | PPO trainer | Dense behavioral evidence |
| Named milestone | Replay referee | Candidate only until replay succeeds |
| One edge replay plus three power-on replays | Promotion gate | Checkpoint-assisted verified curriculum progress |
| Frozen restore-free power-on run | Future evaluator | Required for a one-policy gameplay claim |

The protocol identifiers are `parallel-recurrent-ppo-v5.2` and
`northbound-curriculum-navigation-recovery-v1`. V5.2 may import a cleanly finished, hash-valid V4,
V5, or V5.1 curriculum. It starts fresh PPO parameters because its milestone catalogue, objective,
and actor lesson space changed.

## Migration and test evidence

The implementation passed 174 tests with the private supported ROM enabled. The checks cover:

- all nine map-to-map goals between the Pokédex and Pewter Gym;
- canonical milestone ordinals and Pokédex-qualified early northbound steps;
- signed route guidance through both portions of Route 2;
- navigation recovery requiring resumed movement;
- the three-payment episode cap;
- recovery being disabled during battle;
- dashboard disclosure of recovery credit; and
- all existing emulator, privacy, checkpoint, replay, and reward regressions.

An import audit against the completed V5.1 archive verified the terminal model, four novelty
memories, and all 24 curriculum entries. It retained Pokédex as canonical index 15, six verified
promotions, and the 10,819-action complete lineage. This is an engineering qualification, not a
V5.2 behavioral result.

## Engineering canary

The first four-worker real-ROM canary completed its exact 8,192-action ceiling in 31.978 seconds,
or 256.18 combined actions per second. It completed eight PPO updates, imported all 24 verified
V5.1 curriculum entries, preserved six promotions and Pokédex index 15, and ended with zero
promotion failures.

All four live gameplay frames and the dashboard were written. The terminal PPO model and all four
novelty memories matched their checkpoint hashes. The ledger recorded 114 globally unique
positions, +24 navigation-recovery credit, and -8 net route credit. Exactly +24 recovery credit is
consistent with the three-payment cap being exercised by all four workers; it is wiring evidence,
not proof that the recovery behavior will lead to a milestone. No episode reached its 16,384-action
limit during this shorter canary, so no episode-end classification was expected.

The canary qualifies the production-shaped observation, reward, optimizer, dashboard, artifact,
and shutdown path. It does not qualify the northbound curriculum behavior because no new milestone
was expected or claimed in 8,192 actions.

## Falsifiable long-run questions

The next run should answer these in order:

1. Does a worker leave Oak's Lab with the Pokédex?
2. Does each map lesson promote independently through Route 2 and the Forest gates?
3. Does navigation-recovery credit precede successful exits, or merely appear in failed loops?
4. Do signed route rewards remain approximately balanced when workers reverse direction?
5. Can any Forest candidate survive exact edge replay and three complete power-on replays?
6. Does curriculum depth reduce actions-to-next-promotion after each accepted step?
7. If the Forest is crossed, does the policy enter Pewter Gym before the run budget expires?
8. If it reaches Brock but cannot win, is the limiting evidence battle damage, party strength,
   blackout rate, or menu selection?

## Stop, continue, and redesign rules

Continue the run while optimizer updates advance, artifacts remain healthy, and at least one of
the following changes: verified frontier, global positions, maps/warps, battle outcomes, or recovery
behavior. Stop and redesign if all workers spend a sustained interval at one frontier with only
loop/stagnation exits and no meaningful growth.

Do not call V5.2 successful because reward rises. A chapter success requires a replay-verified
Boulder Badge lineage. Do not call that a complete learned player: it remains checkpoint-assisted
teacher evidence. The eventual student must remove the route and goal aids, freeze its weights,
start at power-on, and reproduce the behavior without restores.

## Narrative and video beat

Version 5.1's story was “progress sometimes points backward.” Version 5.2's story is the next
surprise:

> We taught it to finish one errand. That did not teach it what an errand is.

The visual should begin with the rapid V5.1 promotion sequence—Pallet, Lab, Pokédex—then stretch the
next 3.0 million actions across an empty timeline. Replace the single “Viridian Forest” box with the
ten-step northbound staircase. Show two separate meters: *training hint* and *verified progress*.
The first can move continuously; the second moves only when replay passes.

The honest ending is useful either way. A Brock result would demonstrate that chapter-scale
curriculum can compose several skills. Another plateau would identify the exact map, gate, menu, or
battle where the abstraction still fails. The project is no longer waiting for Shakespeare from
random keystrokes; it is learning how much structure is required before useful behavior can build
on itself.
