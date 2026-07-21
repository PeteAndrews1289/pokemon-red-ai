# Progress and evidence

> **Current research direction:** Parallel PPO Version 4 produced the first replay-verified PPO
> promotion, from Route 1 into Viridian City. Version 5 verified the Viridian Mart and Oak's Parcel.
> Version 5.1 then verified the return to Pallet Town, Oak's Lab, and the Pokédex before plateauing
> for 3,035,252 additional actions. Version 5.2 decomposes the road through Viridian Forest and
> Pewter Gym into explicit chapter steps and verified Route 1. Version 6 now retains that PPO policy
> and moves its training start backward only after rolling competence, separating discovered lineage
> from one-policy composition. The eventual pixels-only, restore-free power-on evaluation remains a
> separate and harder claim.

- **Current stage:** Version 5.2 closed cleanly as the predecessor denominator; the first declared
  Version 6 retained-policy consolidation run is active from its exact terminal policy and optimizer
- **Status date:** 2026-07-21

**Most important caveat:** Q1 verified one replayable house-exit lineage, but the acting suffix
emitter was uniformly random and only one of two seeds reached the target. This is expedition
milestone evidence, not a learned-policy result or an Oak's Parcel result.

The project can now launch the exact supported game revision, issue deterministic controller
inputs, observe a small documented state, and reproduce the start of a clean game. That is useful
infrastructure. It is not evidence that an agent can play Pokémon yet.

## Status legend

| Marker | Meaning |
| --- | --- |
| ✅ Verified | Implemented and exercised by an automated check or repeatable local run |
| 🟨 In progress | Active milestone with an incomplete definition of done |
| ⬜ Planned | Specified, but not yet demonstrated |
| 🧭 Later | Directional idea whose exact design may change |

## Evidence ladder

Each claim receives the strongest level it has actually reached.

| Level | Name | Required evidence | What it does **not** prove |
| ---: | --- | --- | --- |
| E0 | Proposed | A written design or roadmap item | That code exists |
| E1 | Implemented | Code and a documented interface | That it behaves correctly in the emulator |
| E2 | Checked | Automated unit, integration, lint, or safety check | Robust performance across varied runs |
| E3 | Repeated | Reproducible run artifacts with matching declared outcomes | Generalization or task mastery |
| E4 | Evaluated | Frozen policy, fixed budget, all attempts reported, aggregate metrics | Fairness beyond the declared protocol |

Evidence levels describe support for a particular claim, not the overall quality of the project.
For example, a deterministic script can reach E3 without being intelligent, and a newly trained
policy should not be called successful until it reaches E4.

```mermaid
flowchart LR
    E0["E0<br/>Proposed"] --> E1["E1<br/>Implemented"] --> E2["E2<br/>Checked"]
    E2 --> E3["E3<br/>Repeated"] --> E4["E4<br/>Evaluated"]
```

## Current evidence board

| Claim | Status | Evidence | Scope and limitation |
| --- | --- | ---: | --- |
| The harness rejects unsupported ROM revisions | ✅ Verified | E2 | Exact size, title, SHA-1, and SHA-256 are checked before emulation |
| Pokémon Red boots headlessly | ✅ Verified | E2 | Verified against the one supported US Rev. 0 fingerprint |
| Controller timing is explicit | ✅ Verified | E2 | Inputs have fixed hold and release frames; broader timing tolerances are not yet characterized |
| In-memory snapshots replay deterministically | ✅ Verified | E3 | Repeated in the smoke/bootstrap workflow; snapshots are private and never committed |
| A clean scripted boot reaches RED's bedroom | ✅ Verified | E3 | Two fresh attempts match at logical frame 9,804; this is a frozen script, not an agent |
| One-tile movement works at the bedroom start | ✅ Verified | E2 | DOWN moves one tile and snapshot restore returns to the initial state |
| Named state instrumentation is read-only | ✅ Verified | E2 | The sealed referee tracks maps, party, Pokédex, events, items, moves, badges, and blackouts; Conventional alone receives its disclosed coarse subset |
| Current smoke/bootstrap traces avoid ROM paths and bytes | ✅ Verified | E2 | Current writers and guards cover known private artifact forms; every future trace still requires review |
| A trace becomes a readable local run report | ✅ Verified | E2 | Standalone HTML escapes trace data, redacts absolute paths, and embeds no gameplay assets |
| Clean bootstrap has reviewed public evidence | ✅ Verified | E3 | Sanitized trace, two-attempt ledger, exact fingerprints, limitations, and generated report are committed |
| Pure Monkey is a non-learning random baseline | ✅ Verified | E2 | Its seeded uniform action distribution has no policy update or success-dependent state; it remains reproducible but is retired |
| The evolutionary successor has a frozen design | ✅ Verified | E1 | Genome, archive, selection, lineage, compute, and evidence rules are documented and implemented |
| A population neuroevolution runner exists | ✅ Verified | E2 | Deterministic genomes, mutation, archive replacement, genealogy, checkpointing, and a ROM-backed runner are tested |
| The population inherited game-start behavior | ✅ Verified in its development scope | E2 | One 90-minute run found strong parent/child retention; the behavior did not extend past one map and is not a held-out policy result |
| The selection × mutation fork completed | ✅ Verified | E3 | Six lanes each completed 128 children and 1,536,000 actions; every lane stayed on one map with no party member |
| Named milestones reach Hall of Fame | ✅ Verified | E2 | Fifty-five ordered outcomes include mandatory keys/HMs; completion requires both the Champion event and Hall-of-Fame map |
| Frontier evidence is integrity-bound | ✅ Verified | E2 | Cells bind ROM/version snapshots, action segments, frames, ancestry, semantic descriptors, full metadata, and a hash-chained audit log |
| False semantic replay is rejected | ✅ Verified | E2 | A real-ROM regression reproduces exact hashes for a deliberately false Hall-of-Fame cell and fails its canonical milestone check |
| Milestone frontiers require replay | ✅ Verified | E2 | Every v2 non-root cell requires one exact edge replay; a named promotion additionally requires three fresh complete power-on replays before active selection |
| A resumable expedition runner exists | ✅ Verified | E3 engineering | Bounded real-ROM qualification retained an explicit stop/resume and exact final budget; Q1 performance is reported separately |
| Replay bookkeeping is indexed and streamed | ✅ Verified | E2 | Replay counts rebuild from the authoritative event hash chain, lineage actions stream by segment, and ancestry validates topologically; the private-ROM suite passed |
| Disk monitoring is bounded between exact reconciliations | ✅ Verified | E2 | Known writes are counted incrementally, exact tree scans occur only at declared boundaries, and free-space/output limits remain enforced |
| Archive v2 bounds local verification and frontier arrivals | ✅ Qualified | E3 engineering | Three 4,096-action real-ROM trials passed continuous, graceful-resume, and hard-crash gates; edge replay stayed at or below 0.111× and the crash twin matched deterministic terminal state exactly |
| Visual Apprentice Stage 0 connects end to end | ✅ Qualified in its one-route scope | E3 pipeline | Two independent captures matched; one 468,312-parameter CNN-LSTM reached 419/419 offline and after reload, then selected the exact 419-action route to `left_home` once from clean power-on; no recovery, generalization, or H2 claim |
| Recurrent PPO can extend the verified curriculum | ✅ Verified once | E3 checkpoint-assisted | Version 4 promoted Route 1 to Viridian City at action 790,900; the suffix passed one edge and three complete power-on replays, but one policy has not reproduced that lineage from power-on |
| Version 5 assisted-teacher wiring is real-ROM checked | ✅ Qualified engineering | E3 pipeline | Four workers imported 19 verified entries, completed 16,384 actions and 16 PPO updates, exercised bounded Mart guidance, and ended with matching hashes; the Mart lesson itself remains unpassed |
| Version 5 reached Oak's Parcel | ✅ Replay verified | E3 checkpoint-assisted | The stopped run completed 1,390,596 actions and three verified promotions; Mart entry at 619,660 and Parcel at 619,956 each survived exact replay admission |
| Version 5.1 taught active-goal backtracking | ✅ Replay verified | E3 checkpoint-assisted | The run promoted Pallet Town, Oak's Lab, Parcel delivery, and Pokédex by action 402,320; its 10,819-action lineage passed exact replay admission |
| Version 5.1 exposed the post-Pokédex plateau | ✅ Preserved negative result | E3 training | It ran 3,035,252 more actions without Forest progress; all 1,900 episodes ended in 1,241 stagnations or 659 visual cycles |
| Version 5.2 represents the road to Brock as a chapter curriculum | ✅ Implemented and checked | E2 | Seven new milestones create ten visible steps through Route 2, both Forest gates, Pewter, and its Gym; 174 private-ROM tests and the V5.1 migration audit pass |
| Version 5.2 production path runs on the real ROM | ✅ Qualified engineering | E3 pipeline | Four workers completed 8,192 actions and eight updates at 256.18 actions/s, wrote all frames, exercised the recovery cap, and ended with matching model plus four novelty hashes |
| Version 5.2 reached Route 1 with the Pokédex | ✅ Replay verified | E3 checkpoint-assisted | Oak's Lab exit promoted at action 52,728 and Route 1 at 707,472; the run closed cleanly at 5,354,500 actions and 5,229 updates with eight promotions, zero replay failures, and matching terminal hashes, but spent more than four million later actions without Viridian progress |
| Version 6 retains one PPO policy across lessons | ✅ Qualified engineering | E2 / E3 pipeline | A compatible predecessor policy and optimizer load with hash and shape checks; the corrected canary completed eight updates under a fresh action budget |
| Version 6 measures backward composition | ✅ Qualified engineering | E2 / E3 pipeline | Frontier episodes are excluded; one of two earlier-start canary attempts reached Pokédex, the shortened 3/4 rolling gate stayed closed, and scheduler state matched its checkpoint hash |
| Version 6 long consolidation run is active | 🟨 In progress | E3 training | Four workers began from V5.2's exact 5,354,500-action policy and optimizer with a 50/50 episode split and 8/10 gate; initial telemetry confirmed new PPO updates, all four frames, and separate failed consolidation attempts |
| One retained model composes the route from power-on | ⬜ Not demonstrated | E0 | Backward training and frozen evaluation gates must expand to power-on before this claim exists |
| Reverse curriculum reaches the complete opening horizon | ✅ Completed in development scope | E3 development | Seven adaptive rungs completed in 480 attempts with 451 successes; the final full-horizon rung passed 29/30 twice, but weights changed between attempts and no held-out H2 evaluation exists |
| The apprentice-guided expedition continues beyond `left_home` | 🟨 Active | E1 | Frozen pixel-policy actions and seeded exploration now feed Archive v2's full 66-milestone search; no later verified milestone is claimed before run evidence exists |
| Frontier Apprentice learns only replay-verified promotions | ✅ Checked | E2 / E3 engineering | A real-ROM canary learned five promotions through `chose_starter`, made 38 updates, passed 49/49 replay checks, and resumed at the exact learner hash after an intentional stop; Forest performance remains untested |
| Parallel recurrent PPO updates from every rollout | ✅ Checked | E2 / E3 engineering | Pixels-only and privileged canaries completed optimizer updates and hash-bound checkpoints; a production-shaped four-worker run completed two full updates and wrote all dashboard frames |
| Four emulator workers fit the current M1 host | ✅ Checked | E2 local benchmark | Under the prior learner's one-core load, 2/4/6 workers measured 178.06/419.34/351.39 actions/s; the four-worker production shape measured 218.65 actions/s with four optimizer epochs |
| Parallel PPO advances beyond its frozen curriculum | 🟨 Active | E2 | Version 3 ended at 1,147,988 actions and Route 1. Version 4's 65,536-action stress canary exposed a warm-start history mapping error; the corrected build passed a fresh 16,384-action real-ROM qualification with HP credit, two successes, classified loop exits, matching artifacts, and no promotion. |
| The Q0 discovery baseline reached a playable milestone | ⬜ Not demonstrated | E0 | It reached Oak's introduction visually but the referee correctly remained at `power_on` |
| The expedition reached `left_home` | ✅ Verified in one development seed | E3 / H3 | A 419-action lineage passed three promotion replays; the two-seed Q1 result was 1/2 and the emitter was random |
| The Q1 robustness gate passed | ⬜ Failed | E3 | Seed `20260730` stopped at the ground floor; seed `20260731` stepped outside; both exhausted the frozen 20,000-action budget |
| The current expedition is marathon-scale | ⬜ Not yet claimed | E3 engineering | Archive v2 passed its bounded scaling gate, but extreme-depth eligibility/retention and the learned emitter still precede a multi-day headline run |
| Long random action sequences remain stable | ⬜ Planned | E0 | Extended stability run has not been reported |
| A human Oak's Parcel baseline exists | ⬜ Planned | E0 | No baseline action count or completion time is available yet |
| A trained policy leaves the bedroom and house on its one training route | ✅ Verified once | E3 pipeline | The Stage-0 frozen model exactly reproduced its sole demonstration; this is memorization evidence, not a held-out local-skill evaluation |
| An agent completes Oak's Parcel | ⬜ Planned | E0 | No autonomous evaluation attempts exist |
| An agent defeats Brock | 🧭 Later | E0 | This is a future milestone, not a current result |

## Phase view

Project phases deliberately use task-level status instead of a percentage. A percentage would
suggest precision that does not exist before the training design and difficulty are known.

| Phase | Deliverable | Current state | Exit signal |
| --- | --- | --- | --- |
| Q0 — Completion foundation | Reproducible checkpoint runner plus truthful completion referee | **Passed** | Runner, replay, resume, privacy, and corruption checks recorded |
| 1 — Expedition opening | Replay-verified bedroom, house, starter, and Parcel frontiers | **Q1 concluded 1/2; Archive v2 qualified** | A materially different learned or optimized emitter reaches `left_home` under a frozen matched gate |
| 2 — Brock | Reusable skills plus planner, memory, and watchdog | **Not started** | Frozen clean-start evaluation defeats Brock under budget |
| Later — Comparisons | Language-model, RL, and hybrid ablations | **Not started** | Same referee and declared budgets used for all configurations |

## What the current deterministic milestone proves

```mermaid
sequenceDiagram
    participant H as Harness
    participant G as Pokémon Red
    participant O as Read-only observer
    participant R as Recorder

    H->>G: Clean boot
    H->>G: Frozen RED/BLUE input sequence
    G-->>O: Bedroom state
    O-->>R: Map, position, party, battle state
    H->>G: Move DOWN one tile
    H->>G: Restore in-memory snapshot
    O-->>R: Initial state restored
    Note over H,R: Performed twice; hashes and final frame matched
```

It proves that future experiments can begin from a repeatable playable point and that the harness
can measure a basic movement outcome. It does not prove visual understanding, planning,
exploration, battle skill, or learning.

## Metrics for future learning runs

Every chart should be reconstructable from reviewed run data. At minimum, future reports should
include the following fields.

### Task outcome

| Metric | Definition |
| --- | --- |
| Success rate | Successful frozen evaluation attempts / all frozen evaluation attempts |
| Furthest milestone reached | Highest predeclared task milestone reached in each attempt |
| Actions to success | Controller decisions used by successful attempts, with median and spread |
| Evaluation budget used | Actions, emulator frames, and wall-clock time consumed before stop |
| Failure reason | Timeout, loop, blackout, invalid state, crash, or other declared category |

### Learning process

| Metric | Definition |
| --- | --- |
| Training steps | Total environment decisions used to update a policy |
| Emulator-hours | Aggregate emulated game time; reported separately from wall-clock time |
| Training seeds | Every random seed used, not only the strongest run |
| Task return | Declared shaped return, labeled as a diagnostic rather than completion |
| Evaluation checkpoints | Frozen checkpoints evaluated on the same attempt set and budget |

### Behavior and reliability

| Metric | Definition |
| --- | --- |
| Unique map/position coverage | Distinct observed locations under the declared observation schema |
| Loop rate | Attempts terminated by the watchdog / all attempts |
| Blackout rate | Attempts ending in a loss transition / all attempts |
| Intervention count | Human actions that alter a run, including manual inputs and resets |
| Determinism check | Whether replay under the declared seed/config reproduces the recorded result |

If a language model is introduced, calls, input/output tokens, model identifier, latency, and cost
belong beside the training and evaluation budgets. They must not be hidden inside a single
"runtime" number.

## Standard milestone update

Each meaningful progress update should answer the same five questions:

1. **What changed?** Name the capability, not just the code file.
2. **What evidence exists?** Link the test, run summary, or aggregate evaluation.
3. **What was the exact starting condition?** Clean boot, private training state, or held-out state.
4. **What failed?** Include unsuccessful official attempts and known blind spots.
5. **What claim is now justified?** Assign its evidence level and avoid stronger wording.

A compact future update can use this table:

| Field | Value |
| --- | --- |
| Milestone | _Name the bounded task_ |
| Status | _Verified / in progress / planned_ |
| Evidence level | _E0–E4_ |
| Configuration | _Commit, policy/checkpoint, observation version, action version_ |
| Budget | _Training steps and/or evaluation action limit_ |
| Attempts | _All official attempts, with successes and failures_ |
| Interventions | _Count and explanation_ |
| Result | _Task outcome plus uncertainty; never reward alone_ |
| Artifacts | _Reviewed summary, metrics, trace, and generated visuals_ |

## Next evidence targets

The immediate goal is not a flashy success clip. It is a trustworthy first remembered step.

1. Run Version 5 from Version 4's frozen, hash-validated Viridian curriculum with the
   150-million-action safety ceiling, hourly narrative entries, live frames, and storage guards.
2. Require `entered_viridian_mart` and every later milestone to pass the unchanged replay gate;
   reward, PPO updates, and proximity alone remain diagnostics.
3. Preserve the Version-5 teacher trajectory and failure denominator for later skill distillation.
4. Add micro-lessons only when a measured frontier plateau identifies a missing behavior; record
   every intervention and reject any renewable reward loop before resuming.
5. Distill verified teacher behavior into a pixels-plus-action-history student, remove training
   aids, and evaluate frozen policies from power-on before making an autonomous-play claim.

See [Roadmap](roadmap.md) for acceptance gates and [Visual storytelling](visual-storytelling.md) for
how those results should be shown.
