# Parallel recurrent PPO

> **Status:** implemented and exercised in pixels-only and privileged-input canaries on
> 2026-07-20. The first long pixels-only development campaign is the next evidence step. A canary
> proves that the machinery updates; it does not prove that the policy has learned Pokémon Red.

## Why this lane exists

Frontier Apprentice taught only from a rare kind of event: a new named milestone that survived
exact replay. That made every update easy to audit, but most of the agent's experience disappeared.
Walking into a new tile, discovering a map, entering a battle, gaining a level, or finding an item
could help the archive choose where to search, yet none of those events changed the network unless
the same suffix ended in a verified named promotion.

Parallel recurrent PPO changes that rule. Four emulator workers collect trajectories for one
shared CNN-LSTM policy. Every completed rollout contributes to an optimizer update. Dense trainer
rewards can therefore make a failed expedition informative while the existing replay referee still
decides whether a named milestone becomes part of the curriculum.

The audience-readable turn is simple:

> The earlier learner remembered victories. This learner can also learn from the road to them.

That sentence describes the update mechanism, not the result. Whether the mechanism produces
better behavior remains an empirical question.

## Influence and deliberate differences

This lane was prompted by Peter Whidden's
[Pokémon Red experiments](https://github.com/PWhiddy/PokemonRedExperiments) and the accompanying
[video](https://youtu.be/DcYLT37ImBY). That project demonstrated the practical value of recurrent
PPO, several simultaneous emulator environments, pixels plus structured game state, checkpointed
starting states, and visual progress reporting.

This implementation borrows the broad pattern and keeps this project's existing evidence rules:

| Design question | Whidden-inspired lesson | This project’s implementation |
| --- | --- | --- |
| How do failures teach? | Optimize from rollout batches | Recurrent PPO updates from every vector rollout |
| How is CPU time used? | Run many environments | Benchmark 2, 4, and 6; select four on the 8 GB M1 |
| What does the actor see? | Pixels plus useful state can accelerate learning | Primary lane is pixels plus previous action; a separately labeled privileged comparator adds 24 state values |
| Where do episodes begin? | Useful checkpoint starts shorten the horizon | Starts come only from a frozen, replay-verified Archive-v2 curriculum |
| What counts as progress? | Reward and map coverage make learning visible | Reward is diagnostic; only exact edge replay plus three power-on replays admit a new named milestone |
| Is this game completion? | Early-game progress can still be informative | Only a verified Hall-of-Fame promotion ends training as completion, and only frozen power-on evaluation can support an autonomous-policy claim |

This is an influence record, not a claim that the implementations or results are identical.

## Information boundaries

The code supports two actors so the project can measure the value of privileged state without
quietly mixing it into the pixels-only claim.

| Lane | Actor receives | Trainer/referee may inspect | Honest label |
| --- | --- | --- | --- |
| Pixels | Two 72 × 80 grayscale frames and previous action | Documented RAM for reward, termination, curriculum, and replay | `PIXEL-ACTOR / PRIVILEGED-TRAINING-REFEREE / PPO / ARCHIVE-RESTORE` |
| Privileged comparator | The pixel input above plus 24 normalized state values | The same referee fields | `PIXEL+RAM-ACTOR / PPO / ARCHIVE-RESTORE / COMPARATOR` |

The 24-value comparator vector contains game-start state, map and coordinates, party size, battle
kind, individual badge bits, maximum party level, Pokédex counts, event count, bag count, Pokédex
ownership state, and party diversity. It is intentionally small, versioned by the PPO protocol,
and never described as pixels-only.

Neither actor receives a milestone name, checkpoint identity, target action, walkthrough, reward
component, or replay result. Trainer-owned RAM can change learning signals and starting-state
selection; it cannot directly choose a button.

## The shared recurrent policy

```mermaid
flowchart LR
    E1["Environment 1"] --> R["Shared rollout"]
    E2["Environment 2"] --> R
    E3["Environment 3"] --> R
    E4["Environment 4"] --> R
    R --> PPO["Recurrent PPO update"]
    PPO --> P["One shared CNN-LSTM policy"]
    P --> E1
    P --> E2
    P --> E3
    P --> E4
    E1 & E2 & E3 & E4 --> V["Sealed reward + replay referee"]
    V --> R
```

The visual encoder matches the Visual Apprentice network: three convolution layers followed by a
256-unit representation. The previous action is appended before a 128-unit LSTM. The eight-way
policy head chooses Up, Down, Left, Right, A, B, Start, or No-op. The PPO value function is trained
alongside the policy.

The initial convolution, actor LSTM, and action-head weights are copied exactly from the current
Frontier Apprentice checkpoint. In the privileged comparator, the additional LSTM input columns
start at zero, so the warm start initially behaves like its pixels-only ancestor and can learn to
use the new state later. The value head begins new because Frontier Apprentice did not have one.

## Frozen verified curriculum

PPO never reads the active expedition store directly. At launch, the runner opens one atomic
Archive-v2 checkpoint boundary, rejects unverified cells, and copies one representative for each
available milestone/map niche into a private curriculum directory. Every entry contains:

- the exact frozen emulator snapshot;
- its canonical milestone key, index, and label;
- its complete action lineage from power-on; and
- a content hash bound in the curriculum manifest.

Seventy percent of episode resets sample the furthest verified milestone; the remainder sample the
broader curriculum. This makes the newest frontier common without erasing rehearsal of earlier
game states. Emulator state, recurrent state, pixel history, prior action, reward memory, and local
episode history all reset together. Hidden recurrent state is never smuggled across a checkpoint.

## What reward means

The reward ledger reuses the full-game shaping catalog:

- named milestone advancement;
- first visit to a map, coordinate, or warp during that worker's campaign;
- newly observed event flags, badges, party members, levels, moves, species, and items;
- worker-lifetime record experience, capped per observation;
- battles ending only after durable experience or capture progress;
- blackouts, repeated actions, and later loop signals as penalties.

Each restored parent is primed before scoring, so PPO is not paid merely for loading a good
checkpoint. Version 1 then reset its novelty memory at every episode. The first long run exposed
why that was unsafe: during one 238,592-action slice it recorded 1,784 episode-local position
rewards while adding only five globally unique positions. Familiar routes could therefore pay
again after every reset.

Version 2 keeps map, coordinate, warp, event, party, item, move, species, badge, level, and best
milestone memory for each worker's complete campaign. A reset absorbs its restored parent into that
memory before the first scored action. Four workers may each discover the same fact once, but no
worker can farm it on every episode. Every worker's compressed novelty memory is immutable,
content-hashed, and bound into each PPO checkpoint, so a graceful resume cannot reset the reward
history. The complete component totals are written to status and hourly narrative records.

Version 2 then exposed a second loophole. At 724,996 actions and 41 minutes it remained at Route 1:
the preceding 366,592-action interval added only 24 global positions while paying 2,930 reward for
293 more battle endings. An optimizer can learn to enter and leave frequent Route 1 encounters
without learning to win them. Version 3 therefore removes unconditional `battle_ended` reward.
A battle now earns a reduced `battle_success` value of 2 only if that same battle produced durable
experience or a newly owned species. Leaving without either produces no reward and is counted as
`ended_without_progress` on the dashboard. New party experience pays 0.02 per point only above the
worker's lifetime record, with at most 500 points rewarded at one observation. A reset can therefore
absorb an inherited experience total but cannot repay it. Blackouts retain their explicit penalty.

This is not a claim that RAM tells the actor how to battle. The pixels-only policy still receives
only two frames and its previous action. The trainer reads the documented three-byte experience
field to decide whether an outcome deserves training credit. The protocol is bumped to
`parallel-recurrent-ppo-v3`; version-2 PPO weights are not resumed under the new objective.

Reward remains a training diagnostic. A high return does not mean the agent completed a quest,
defeated a Gym Leader, or reached the Hall of Fame.

## Promotion remains harder than reward

When a worker observes a named milestone beyond the curriculum's current best, it writes a private
candidate containing the parent, local actions, terminal snapshot, screen hash, and referee
summary. The central trainer pauses admission and performs:

1. one exact replay of the candidate suffix from its parent snapshot; and
2. three exact replays of the parent's complete lineage plus the suffix from the unique power-on
   root.

Snapshot hash, screen hash, canonical milestone, and referee summary must all match. Only then does
the trainer atomically add the checkpoint to the curriculum and record a verified promotion. A
failed verification stays in the failure ledger and never becomes a training start.

This keeps two ideas separate:

- **PPO update:** the policy learned from a rollout batch; and
- **verified promotion:** the experiment proved a new durable game outcome.

### Version-3 battle-credit canaries

The first real-ROM version-3 canary completed 8,192 actions, 64 optimizer updates, and eight
episodes. It recorded one battle start, then 24 experience points, then one successful battle. Its
reward ledger contained `experience_gain=0.48` and `battle_success=2.0`; `battle_ended` was absent.
The final model archive and compressed worker memory matched their checkpoint hashes, and the worker
memory retained total party experience 159.

A separate canary requested a graceful stop at action 7,607. Version 3 restored the hash-checked
model, optimizer, and worker reward memory, then reached the original 8,192-action ceiling and 64
total updates. These checks establish wiring, classification, and restart behavior. One successful
wild encounter does not establish robust battle skill or later-game advancement.

## Checkpoints and interruption semantics

The latest and previous PPO archives are retained. A checkpoint binds the model file hash, total
actions, elapsed time, full configuration, and best milestone. Resume refuses a mismatched model or
configuration.

Stable-Baselines3 preserves model parameters, optimizer state, schedules, and timestep count. The
emulator processes and partially collected rollout restart. Every status and manifest therefore
uses the exact phrase:

`exact model/optimizer; fresh environment rollouts`

That is strong enough for an interrupted development campaign, but it is not a bit-identical
continuation of every worker's hidden emulator and LSTM state.

The runner stops cleanly for wall time, action ceiling, explicit stop request, low disk space,
output limit, or a replay-verified Hall of Fame. Disk tree scans happen on the reporting cadence,
not every action.

## Mac worker benchmark

The 2026-07-20 setup benchmark ran while the prior Frontier Apprentice baseline still occupied one
CPU core. Every candidate completed two real PPO updates.

| Environments | Combined actions | Measured actions/s | Interpretation |
| ---: | ---: | ---: | --- |
| 2 | 256 | 178.06 | Leaves CPU capacity unused |
| 4 | 512 | 419.34 | Fastest tested collection rate |
| 6 | 768 | 351.39 | Emulator and training contention begins |

The production-shaped four-environment canary then used 256-step rollouts, batch size 256, four
optimizer epochs, and the full 4,096-action episode horizon. It completed 2,048 actions and two PPO
updates at 218.65 actions/s, wrote all four gameplay frames, saved a hash-matched checkpoint, and
ended with the dashboard correctly marked `finished`.

Microbenchmarks are not learning results. Their purpose is to choose four workers and avoid wasting
the long-run window on an oversubscribed machine.

## Live dashboard and narrative evidence

The live page refreshes every five seconds and shows:

- combined controller actions and actions per second;
- environment count and current run state;
- best replay-verified milestone;
- PPO update and verified-promotion counts;
- episodes and unique map positions;
- successful versus no-progress battle exits; and
- the latest rendered frame from every emulator worker.

TensorBoard receives optimizer metrics. `status.json` supplies machine-readable counters.
`NARRATIVE.md` appends an hourly chapter with the best milestone, actions, updates, promotions,
episodes, and coverage. Named promotions also create immediate chapters and preserve their exact
frame. These artifacts are private by default because gameplay frames, snapshots, curriculum
entries, and model weights must not enter Git.

## First long-run interpretation rules

### Launch record

The first 24-hour command was detached from its terminal with a generic shell wrapper. The Codex
app cleaned up that process group after four actions, before any PPO checkpoint existed. Its
private directory was preserved as a failed launch. The replacement uses the managed long-running
session that supported the earlier campaigns. It was not accepted as healthy merely because its
dashboard opened: the launch gate required all four worker frames, several complete PPO rollouts,
zero verification failures, and a model archive whose SHA-256 matched its checkpoint record.

The managed version-1 run passed that launch gate at 21,508 observed actions with 21 PPO updates,
278 unique positions, and its first hash-matched checkpoint at action 16,384. It was deliberately
stopped after 862,212 actions, 208 episodes, and 469 globally unique positions when the episodic
novelty loophole became clear. It never promoted beyond Route 1. This operational and reward-design
failure belongs in the narrative because a visible dashboard and active optimizer do not prove
that the chosen reward drives new behavior.

Version 2 passed a 512-action one-worker reset canary with four episode lifetimes, eight PPO
updates, and a hash-matched novelty record. A production-shaped four-worker canary then completed
2,048 actions, eight episode lifetimes, and two rollout updates at 375.69 actions/s. All four
worker memories and the model matched their checkpoint hashes. These checks authorize a fresh
version-2 run; they are not gameplay-progress evidence.

The first campaign is a development trial, not a frozen policy evaluation. Its useful outcomes are:

| Outcome | What it would support | What it would not support |
| --- | --- | --- |
| More PPO updates but no new milestone | The machinery learned from batches but failed to convert reward into named progress | That PPO is generally useless |
| Better coverage and reward, same milestone | Dense shaping changed behavior diagnostically | That the agent advanced the story |
| One verified later milestone | PPO-assisted training extended the curriculum once | Autonomous completion or robustness |
| Several verified promotions | The shared-policy/curriculum loop accumulated real progress | One frozen clean-start policy can reproduce it |
| Verified Hall of Fame | The archive-assisted training system found and replayed a complete lineage | H5/H6 autonomous-policy mastery until frozen power-on evaluation passes |

The pixels lane is primary. The privileged lane is a comparator to answer how much direct state
helps, not a fallback whose stronger information label can be hidden if it wins.

## Reproduction outline

Install the explicitly optional learning stack:

```bash
python -m pip install -e ".[dev,apprentice,rl]"
```

Then point the runner to private, ignored artifacts:

```bash
pokemon-red-ai ppo-run \
  --rom "/private/path/Pokemon Red.gb" \
  --output "/external/private/path/parallel-ppo-run" \
  --curriculum-source "/external/private/path/verified-expedition" \
  --learner "/external/private/path/verified-expedition/frontier-learner.pt" \
  --mode pixels \
  --environments 4 \
  --hours 8 \
  --max-actions 150000000 \
  --port 8772
```

Use `pokemon-red-ai ppo-status RUN_DIRECTORY` for a concise heartbeat and
`pokemon-red-ai ppo-stop RUN_DIRECTORY` for an atomic checkpoint request. Never publish the output
directory without a separate review and sanitization step.

## Questions deliberately left open

- Is per-worker campaign novelty sufficient, or does later scale require a shared count model?
- Will 4,096 actions let the recurrent policy learn sufficiently long local skills?
- Does the current entropy setting preserve exploration after the warm-started action prior?
- Should verified curriculum sampling become milestone-balanced after later maps accumulate?
- Does pixels-only PPO beat verify-only self-imitation at the Viridian Forest gate?
- How much of any privileged comparator advantage comes from coordinates rather than game state?
- When should a frozen power-on evaluation interrupt training without consuming the training RNG?

Those are experiment questions. They should be answered with matched runs and retained failures,
not tuned away silently during the first long campaign.
