# Progress and evidence

> **Current research direction:** the completed
> [six-lane mechanism lab](selection-mutation-lab.md) failed its second-map gate in every condition.
> The clean-start mutation population remains the historical inheritance control. Primary work has
> moved to the [Hall of Fame completion program](completion-program.md): a named semantic referee,
> integrity-bound frontier checkpoints, complete action lineages, and mandatory power-on replay
> before any checkpoint may become a verified milestone.

- **Current stage:** Q1 concluded at 1/2; Archive v2 passed staged qualification; the Visual
  Apprentice data and overfit pipeline are next
- **Status date:** 2026-07-19

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
| Visual Apprentice v1 has a frozen development design | ✅ Specified | E0 | Pixel inputs, recurrent model, self-generated data, curriculum, hardware bounds, ablations, and evaluation gates are documented; no model has been trained |
| The Q0 discovery baseline reached a playable milestone | ⬜ Not demonstrated | E0 | It reached Oak's introduction visually but the referee correctly remained at `power_on` |
| The expedition reached `left_home` | ✅ Verified in one development seed | E3 / H3 | A 419-action lineage passed three promotion replays; the two-seed Q1 result was 1/2 and the emitter was random |
| The Q1 robustness gate passed | ⬜ Failed | E3 | Seed `20260730` stopped at the ground floor; seed `20260731` stepped outside; both exhausted the frozen 20,000-action budget |
| The current expedition is marathon-scale | ⬜ Not yet claimed | E3 engineering | Archive v2 passed its bounded scaling gate, but extreme-depth eligibility/retention and the learned emitter still precede a multi-day headline run |
| Long random action sequences remain stable | ⬜ Planned | E0 | Extended stability run has not been reported |
| A human Oak's Parcel baseline exists | ⬜ Planned | E0 | No baseline action count or completion time is available yet |
| A trained policy leaves the bedroom | ⬜ Planned | E0 | Development learners have wandered beyond it, but no frozen task evaluation has been run |
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

1. Preserve the [complete 1/2 Q1 result](../experiments/q1-left-home/README.md) as the random
   checkpoint-search baseline.
2. Implement streaming replay, replay indexes, topological validation, selective local-cell
   verification, and bounded private-payload retention.
3. Prevent a growing queue of one-use visual cells from starving newly advanced frontiers.
4. Compare an optimized action-sequence emitter and learned visual emitter under the unchanged
   two-seed, 20,000-action `left_home` gate.
5. Advance toward Oak and the starter only after one materially different emitter passes that gate.

See [Roadmap](roadmap.md) for acceptance gates and [Visual storytelling](visual-storytelling.md) for
how those results should be shown.
