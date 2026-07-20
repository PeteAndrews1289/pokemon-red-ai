# Append-only research decision register

> **Purpose:** preserve not only what the project chose, but what it rejected, retired, deferred,
> or tried without success. Failed ideas are evidence. They may be superseded; they are never
> silently deleted or rewritten into a success story.

The [development log](devlog.md) records what was built chronologically. This register records why
a research direction changed and what evidence justified the change. The
[Hall of Fame completion program](completion-program.md) is the current operational plan.

## Append-only rules

1. Give every material research choice a permanent `DR-####` identifier.
2. Append a new entry when a choice changes. Do not edit the conclusion of an earlier entry to make
   it match current thinking.
3. A factual typo or broken link may be corrected in place, but the correction must not change the
   recorded decision or its historical interpretation.
4. Link evidence by committed file, reviewed public artifact, or content hash. Never put a private
   ROM, snapshot, save, username, or absolute local path in this file.
5. Separate the observation from the interpretation. “No lane reached a second map” is an
   observation; “the horizon is the dominant bottleneck” is an interpretation.
6. Record who or what can see privileged state, even when the actor cannot.
7. Record alternatives that were seriously considered, including the reason they were not chosen.
8. `Failed to qualify` means a method missed its declared gate under a declared budget. It does not
   mean a mathematical proof that the method can never work.

## Status vocabulary

| Status | Meaning |
| --- | --- |
| `Accepted` | Current decision to implement or continue. |
| `Trialing` | A bounded experiment is authorized; evidence is not yet sufficient to adopt it. |
| `Completed` | The declared decision or experiment was carried out; its conclusion remains recorded. |
| `Deferred` | Plausible, but intentionally postponed until a dependency or evidence gate. |
| `Rejected` | Considered and deliberately not selected for the stated scope. |
| `Retired` | Was useful, answered its question, and no longer receives primary compute. |
| `Superseded` | Replaced by a later decision; historical results remain valid in their original scope. |
| `Failed to qualify` | Missed its declared evidence gate under the tested conditions. |

## Entry template

```markdown
## DR-#### — Short title

- Date:
- Status:
- Scope:
- Information label:
- Decision:
- Alternatives considered:
- Observation/evidence:
- Interpretation:
- Consequence:
- Revisit when:
- Supersedes / superseded by:
```

Fields that genuinely do not apply should say `Not applicable` rather than disappear.

## Register

## DR-0001 — Pin one exact Pokémon Red revision

- **Date:** 2026-07-18
- **Status:** Accepted
- **Scope:** Harness and every experiment
- **Decision:** Support the verified US Rev. 0 ROM fingerprint and bind snapshots/replays to it.
- **Alternatives considered:** Accept multiple Red revisions; begin with a later generation.
- **Observation/evidence:** The supplied private ROM matched the pinned title, size, SHA-1, and
  SHA-256, and the harness could reject mismatches before emulation.
- **Interpretation:** One exact game removes an avoidable source of state-address, timing, and replay
  ambiguity while the learning system is changing quickly.
- **Consequence:** Claims apply only to that declared revision unless another revision is separately
  qualified. The ROM remains private and outside Git.
- **Revisit when:** A second revision or game becomes an explicit replication target.

## DR-0002 — Establish deterministic, privacy-safe infrastructure before training claims

- **Date:** 2026-07-18
- **Status:** Accepted
- **Scope:** Harness, artifacts, and publication
- **Decision:** Require explicit controller timing, snapshot integrity, sanitized traces, private
  artifact boundaries, and repeatable bootstrap tests before judging an agent.
- **Alternatives considered:** Begin training immediately and repair reproducibility later.
- **Observation/evidence:** Repeated scripted boots reached the same bedroom state and frame; a
  neutral-boundary snapshot restored the same state; guards rejected known private artifact forms.
- **Interpretation:** A learning curve is not interpretable if the starting state, controller, or
  recorder cannot be trusted.
- **Consequence:** Infrastructure accomplishments are reported separately from learning outcomes.

## DR-0003 — Begin with a strict-blind philosophical track

- **Date:** 2026-07-19
- **Status:** Superseded by DR-0015 as the sole completion strategy; retained as a control
- **Scope:** Pure curiosity experiments
- **Information label:** `PIXEL-ACTOR / STRICT-BLIND`
- **Decision:** Ask how far pixels, action history, and visual novelty can go without semantic game
  state causally influencing reward, selection, resets, curriculum, or checkpoint choice.
- **Alternatives considered:** Give the actor coordinates, map IDs, milestones, or a walkthrough at
  the start.
- **Observation/evidence:** The boundary is defined in
  [Blind curiosity](blind-curiosity.md) and exercised by the early Monkey/Archivist work.
- **Interpretation:** The strict condition creates a meaningful control and a clear audience
  question, even if it is not the most sample-efficient route to completion.
- **Consequence:** Strict-blind results remain separate from privileged-training results.

## DR-0004 — Retire Pure Monkey from the headline lane

- **Date:** 2026-07-19
- **Status:** Retired
- **Scope:** Primary multi-day training allocation
- **Decision:** Preserve the uniform random policy and all its artifacts as a baseline, but stop
  allocating a principal lane to it.
- **Alternatives considered:** Run true randomness indefinitely under the
  “monkeys with typewriters” premise.
- **Observation/evidence:** The policy samples each action from a fixed distribution; a lucky result
  never changes a later action probability.
- **Interpretation:** It can demonstrate luck but cannot accumulate knowledge. More samples improve
  the chance of another accident, not the policy.
- **Consequence:** Neuroevolution replaced Monkey in the live arena. Monkey remains reproducible.
- **Revisit when:** A bounded random denominator is needed for a new observation/action schema.

## DR-0005 — Treat visual novelty as a useful probe, not proof of progress

- **Date:** 2026-07-19
- **Status:** Superseded as the primary objective
- **Scope:** Archivist and visually curious agents
- **Decision:** Keep visual novelty as a capped diversity signal and diagnostic; do not let it define
  whole-game success or dominate required outcomes.
- **Alternatives considered:** Optimize only the count of visually novel screen cells.
- **Observation/evidence:** A 5,000-action calibration found 591 coarse visual cells and reached the
  name-entry interface, showing that novelty reacts strongly to text, menus, and animation. Later
  pixels-only learners accumulated activity without story completion.
- **Interpretation:** Screen diversity is valuable before semantics are available, but it confuses
  animation and menu variation with purposeful progression.
- **Consequence:** Future completion training uses named outcomes above bounded novelty.

## DR-0006 — Expanding tabular capacity alone is not the long-horizon solution

- **Date:** 2026-07-19
- **Status:** Failed to qualify as a completion strategy
- **Scope:** Online Q-learning pretrials
- **Decision:** Stop treating larger state/action tables by themselves as the next decisive upgrade.
- **Alternatives considered:** Continue dramatically increasing table capacity and run duration.
- **Observation/evidence:** Three online learners completed roughly 2.2–2.56 million actions each,
  observed six maps, and reached party levels 27–29, yet plateaued in the Pallet Town/Route 1
  region. Levels and actions did not correspond to story milestones.
- **Interpretation:** Capacity did not supply hierarchical memory, a milestone curriculum, robust
  loop handling, or reusable menu/battle/navigation skills.
- **Consequence:** The tables remain historical comparators. Richer representations and a staged
  curriculum may later replace them.

## DR-0007 — Use semantic outcome rewards carefully

- **Date:** 2026-07-19
- **Status:** Accepted with limits
- **Scope:** Privileged-training comparators and completion referee
- **Information label:** `PIXEL-ACTOR / PRIVILEGED-TRAINING-REFEREE` unless actor state says otherwise
- **Decision:** Permit the sealed training referee to reward new required milestones, named events,
  captures, Pokédex discoveries, and capabilities, while capping secondary signals.
- **Alternatives considered:** Visual novelty only; unlimited level, capture, event-flag, or
  coordinate rewards.
- **Observation/evidence:** Outcome-rewarded agents showed more game activity but still plateaued
  locally. Captures and Pokédex discovery were proposed as possible gentler nudges.
- **Interpretation:** These outcomes can make sparse learning less hopeless, but collection or
  grinding can become a local optimum if allowed to outrank required story transitions.
- **Consequence:** Reward is computed as delta from the starting frontier and ordered below the next
  required goal-graph transition.

## DR-0008 — Choose fixed-topology, mutation-only neuroevolution for the first inheritance test

- **Date:** 2026-07-19
- **Status:** Superseded as the primary architecture; retained as a historical control
- **Scope:** Evolutionary Explorer version 1
- **Decision:** Use a deterministic 13,096-parameter recurrent pixel policy, one-parent mutation,
  immutable ancestry, and no within-lifetime weight updates.
- **Alternatives considered:** NEAT topology growth, crossover, a large deep-learning stack, and
  evolution strategies.
- **Observation/evidence:** The simpler representation made genome round trips, changed-parameter
  counts, parent/child retention, and family trees directly inspectable.
- **Interpretation:** The mechanism was appropriate for the first causal question: can a useful
  accident become hereditary?
- **Consequence:** Topology evolution and crossover are deferred experiments, not silently mixed
  into the baseline.

## DR-0009 — Preserve diverse elites instead of one global winner

- **Date:** 2026-07-19
- **Status:** Accepted
- **Scope:** Evolutionary archive
- **Decision:** Use quality-diversity preservation so local exploration, interactions, battles, and
  progress lineages do not collapse into one scalar-score dynasty.
- **Alternatives considered:** Breed only the single highest-scoring policy.
- **Observation/evidence:** Pokémon contains deceptive local optima: repeated battles or
  coordinates can numerically exceed a rare but important transition.
- **Interpretation:** Multiple stepping stones are useful, but diversity descriptors must describe
  useful behavioral/state distinctions.
- **Consequence:** MAP-Elites-style preservation continues, with milestone-reserved,
  quality-aware archive admission planned for the expedition.

## DR-0010 — Add an action-profile descriptor to prevent immediate archive collapse

- **Date:** 2026-07-19
- **Status:** Superseded for completion selection; retained as a diagnostic
- **Scope:** Early Evolutionary Explorer qualification
- **Decision:** Add a bounded dominant-action profile to distinguish non-progressing founders that
  otherwise occupied one archive cell.
- **Alternatives considered:** Let all pre-game policies compete in one identical cell.
- **Observation/evidence:** The repeat qualification preserved both founders in separate cells, but
  the full pretrial later gave many non-starting button-habit niches reproductive opportunity.
- **Interpretation:** The patch preserved raw diversity but not necessarily useful diversity.
- **Consequence:** Button profile remains useful in charts. Expedition cells prioritize milestone,
  state transition, interaction mode, and spatial/visual identity.

## DR-0011 — Diagnose uniform selection and broad mutation with a 2 × 3 lab

- **Date:** 2026-07-19
- **Status:** Completed
- **Scope:** Inherited-archive engineering fork
- **Decision:** Cross uniform/frontier parent selection with broad/gentle/multiscale mutation under
  equal 128-child, 1,536,000-action lane budgets.
- **Alternatives considered:** Pick a favorite mechanism from the 90-minute run; change several
  unmeasured components at once.
- **Observation/evidence:** The preceding run associated game-starting parents with much higher
  game-start retention, while uniform selection still spent roughly 64% of children on
  non-starting parents and broad mutation often erased the best four-position behavior. See
  [Selection × mutation lab](selection-mutation-lab.md).
- **Interpretation:** A factorial fork was the smallest clear test of the two suspected causes.
- **Consequence:** The source archive, clean starts, policy, and lifetime stayed fixed across lanes.

## DR-0012 — Selection and mutation changes alone failed the next-map gate

- **Date:** 2026-07-19
- **Status:** Failed to qualify
- **Scope:** Full 2 × 3 mechanism lab
- **Decision:** Do not choose any of the six lanes as a whole-game configuration or run the exact
  matrix for multiple days unchanged.
- **Alternatives considered:** Declare frontier–broad the winner from its seven-position local best;
  assume more time will necessarily create story progression.
- **Observation/evidence:** All six lanes finished exactly 128 evaluations and 1,536,000 actions,
  totaling 9,216,000 actions in 3,523.886 seconds. Every best lineage remained at tier 1, one map,
  party count zero, and Pokédex zero. Best position counts ranged from four to seven. The private
  final comparison summary is identified by SHA-256
  `a13137e6ecad9a01e43e52c1b35299847583aff8be7b1e4c3309517fc4a8ee2b`.
- **Interpretation:** Selection and mutation affected local archive behavior but did not address the
  dominant horizon/state-retention problem.
- **Consequence:** Preserve this run as the clean-start mutation control and implement expedition
  memory before another large campaign.
- **Revisit when:** A later clean-start learner has materially different perception, memory,
  learning, or curriculum and needs this matrix as an ablation.

## DR-0013 — Replace whole-game clean-start lifetimes with a checkpoint expedition

- **Date:** 2026-07-19
- **Status:** Accepted
- **Scope:** Primary discovery program
- **Information label:** `PIXEL-ACTOR / PRIVILEGED-TRAINING-REFEREE / ARCHIVE-RESTORE / POPULATION`
- **Decision:** Preserve verified frontier snapshots, exact action segments, and complete ancestry;
  restore a selected cell before exploring a short suffix.
- **Alternatives considered:** Continue restarting every child at power-on; teleport through RAM;
  manually place the agent after each milestone.
- **Observation/evidence:** The existing lifetime resets all game progress after every child. The
  six-lane lab made no next-map progress despite millions of actions and changed selection/mutation.
- **Interpretation:** Long-horizon exploration needs a memory of stepping stones. Snapshot restore
  is trainer infrastructure, not an actor action, and must remain explicitly labeled.
- **Consequence:** Every major promoted state requires full power-on action-lineage replay. No
  emulator-memory writes or human rescues are permitted.

## DR-0014 — Separate discovered lineage from one learned policy

- **Date:** 2026-07-19
- **Status:** Accepted
- **Scope:** Claims, dashboard, video, and evaluation
- **Decision:** Use separate H4 and H5 claims for a replayable checkpoint-assisted action lineage
  and one frozen policy completing from power-on.
- **Alternatives considered:** Call any checkpoint-assisted Hall-of-Fame result “the model beat
  Pokémon.”
- **Observation/evidence:** An expedition can combine action segments generated by many policies and
  private training restores. One network may not reproduce that route independently.
- **Interpretation:** Both results are meaningful, but they answer different questions.
- **Consequence:** The dashboard, result card, and narration must name the evaluated object.

## DR-0015 — Keep a strict-blind control beside a privileged-referee completion track

- **Date:** 2026-07-19
- **Status:** Accepted
- **Scope:** Long-term experimental portfolio
- **Decision:** Preserve occasional `STRICT-BLIND` runs for the original philosophical question,
  while allowing named RAM-derived outcomes to guide the primary expedition outside the actor.
- **Alternatives considered:** Abandon blindness entirely; forbid all privileged training influence
  even if it makes completion impractical.
- **Observation/evidence:** Semantic guidance helped measure and select outcomes but did not need to
  enter the pixel actor. Existing documents previously used “pixels-only” without always naming
  this training-side influence.
- **Interpretation:** Actor perception and training information are separate experimental axes.
- **Consequence:** Every run publishes both labels. No privileged-referee result is described as
  strict blind.

## DR-0016 — Make Hall of Fame the machine-checked north star

- **Date:** 2026-07-19
- **Status:** Accepted
- **Scope:** Completion program
- **Decision:** Build a named prerequisite graph ending in an independently tested Hall-of-Fame
  terminal condition. Use milestone deltas for training and the terminal condition for success.
- **Alternatives considered:** Define completion by badges, Champion battle entry, reward total,
  map coverage, or a visually selected final frame.
- **Observation/evidence:** The current referee has broad semantic fields but no dedicated
  Hall-of-Fame success rule. Its arbitrary event-flag count can rank unrelated state changes.
- **Interpretation:** A machine-checkable outcome independent of reward prevents an attractive
  training score from becoming a completion claim.
- **Consequence:** Named-event and Hall-of-Fame detection are Q0 work, before a long campaign.

## DR-0017 — Use a goal graph, not a scripted walkthrough

- **Date:** 2026-07-19
- **Status:** Accepted
- **Scope:** Curriculum and scoring
- **Decision:** Represent required outcomes and prerequisites while allowing valid alternative
  ordering and discovered routes. Do not provide expected coordinates or button sequences to the
  actor.
- **Alternatives considered:** Hard-code the known optimal route; use one total ordered list of
  map coordinates; reward arbitrary event-flag count.
- **Observation/evidence:** Pokémon contains partially flexible progression, menus, battles, and
  state-dependent route choices. Coordinate count already produced local activity without story
  advancement.
- **Interpretation:** Outcome structure supplies a gentle semantic nudge without scripting how the
  model must act.
- **Consequence:** Human/test-driver runs validate the referee and horizons only; they are not
  demonstrations unless explicitly relabeled.

## DR-0018 — Add delta scoring, loop termination, and adaptive suffix budgets

- **Date:** 2026-07-19
- **Status:** Accepted
- **Scope:** Expedition efficiency
- **Decision:** Score only progress added beyond the restored frontier, terminate classified loops
  without rescue, and allocate branch length by stage/mode instead of one 12,000-action lifetime.
- **Alternatives considered:** Pay every descendant again for inherited progress; use one fixed
  whole-game horizon; let known loops consume the full ceiling.
- **Observation/evidence:** Earlier learners repeatedly farmed local movement, battles, menus, and
  levels. Fixed full lifetimes made every failed suffix equally expensive.
- **Interpretation:** The referee should reward contribution, while the watchdog should turn wasted
  compute into explicit failure evidence.
- **Consequence:** Initial 256–4,096-action suffix ranges require calibration and may change through
  a later register entry.

## DR-0019 — Do not launch a multi-day expedition before the first replay gate

- **Date:** 2026-07-19
- **Status:** Accepted
- **Scope:** Compute allocation
- **Decision:** Require the checkpoint system to discover and replay the staircase/house-exit
  frontier from power-on three times before a multi-day campaign.
- **Alternatives considered:** Implement the full architecture and immediately consume the maximum
  action/storage budget.
- **Observation/evidence:** The lightweight six-lane harness is operationally stable, but the
  learning mechanism failed its first meaningful transition gate.
- **Interpretation:** Long runtime amplifies both a useful engine and a broken objective. A small
  frontier test distinguishes them cheaply.
- **Consequence:** Q1 is the next go/no-go gate.

## DR-0020 — Distill the expedition into one learned visual policy

- **Date:** 2026-07-19
- **Status:** Deferred until useful expedition data exists
- **Scope:** H5/H6 model
- **Decision:** Use self-generated successful and recovery trajectories plus a checkpoint
  curriculum to train a richer visual recurrent policy, then evaluate it from power-on without
  snapshots.
- **Alternatives considered:** Stop after one open-loop action lineage; use a human walkthrough as
  the primary demonstration set; keep mutating the 13,096-parameter RNN indefinitely.
- **Observation/evidence:** The small RNN inherited a narrow title behavior but did not progress
  across maps. A checkpoint lineage can discover a route but is not reactive knowledge in one
  model.
- **Interpretation:** Discovery and robust learning should be sequential objectives. The
  expedition supplies an automatically generated curriculum without requiring human play data.
- **Consequence:** Candidate visual encoders, recurrent memory, skill heads, imitation, and
  recurrent RL are tested first on bounded stage evaluations.

## DR-0021 — Preserve every serious failure as a first-class narrative artifact

- **Date:** 2026-07-19
- **Status:** Accepted
- **Scope:** Documentation, dashboards, and video production
- **Decision:** Retain failed branches, invalid attempts, interventions, protocol changes, rejected
  ideas, and their evidence alongside successes.
- **Alternatives considered:** Keep only champion footage and retrospectively present the final
  design as inevitable.
- **Observation/evidence:** The most useful design changes so far came from visible failures:
  non-learning randomness, novelty without purpose, local reward loops, destructive mutation,
  unproductive archive niches, and the clean-start horizon.
- **Interpretation:** The failed hypotheses are both scientific evidence and the central narrative
  of how the system learned to learn.
- **Consequence:** This file is append-only; periodic summaries link back to immutable run evidence.

## DR-0022 — Implement the completion referee and private frontier foundation before another run

- **Date:** 2026-07-19
- **Status:** Completed at the unit/integration-foundation level; expedition qualification pending
- **Scope:** Q0 completion harness
- **Information label:** `PIXEL-ACTOR / PRIVILEGED-TRAINING-REFEREE`
- **Decision:** Define 46 named outcomes through a strict Hall-of-Fame condition and store each
  frontier as an integrity-bound private snapshot, exact parent action segment, complete lineage,
  and append-only audit event.
- **Alternatives considered:** Continue using badge count and arbitrary event totals; bolt snapshots
  directly onto version-1 genome elites; postpone provenance until after a successful run.
- **Observation/evidence:** Automated tests cover catalog ordering, event/map conditions, corrupt
  payloads, cell/lineage tampering, orphan-index recovery, archive capacity, exact frame accounting,
  and checkpoint persistence. Private-ROM integration replays a fresh power-on root exactly.
- **Interpretation:** A completion search cannot be trusted unless “where did this state come from?”
  and “what outcome is this?” have independent, machine-checked answers.
- **Consequence:** No state may become an active milestone frontier merely because its reward or
  snapshot hash looks impressive.

## DR-0023 — Reject hash-only replay after it produced a false Hall-of-Fame pass

- **Date:** 2026-07-19
- **Status:** Failed design found during audit; superseded and regression-tested
- **Scope:** Replay verifier and H3/H4 claims
- **Decision:** Make canonical semantic verification mandatory inside the replay verifier. Exact
  snapshot and screen hashes remain necessary but are never sufficient for a milestone claim.
- **Alternatives considered:** Keep a caller-optional milestone predicate; trust the descriptor
  written when a cell was discovered.
- **Observation/evidence:** An adversarial real-ROM check created a cell whose descriptor claimed
  Hall of Fame while its exact replay remained at pre-game power-on. The first verifier returned a
  pass because both hashes matched. The same audit also showed that edited descriptor metadata was
  accepted under an unchanged cell ID.
- **Interpretation:** Determinism proves that the same state was reproduced; it does not prove that
  the state was named truthfully. Content addressing also means little unless every claimed field
  participates in the identity hash and is recomputed on open.
- **Consequence:** Replay now accumulates milestone state from actual RAM observations, rejects the
  false completion, binds complete cell metadata and lineage to hashes, and records every mismatch.
  The initial verifier is preserved here as a useful failed decision, not hidden from the story.

## DR-0024 — Quarantine discoveries and enforce one authoritative archive writer

- **Date:** 2026-07-19
- **Status:** Accepted; quarantine implemented, coordinator integration in progress
- **Scope:** Long-run archive validity and multi-worker safety
- **Decision:** A local cell requires at least one exact semantic power-on replay; a newly advanced
  milestone requires three. Until then it is retained as evidence but cannot parent the verified
  frontier. One coordinator owns archive writes, active membership, selection counts, and random
  state even if several emulator workers are added later.
- **Alternatives considered:** Let unverified states reproduce immediately; let every process write
  the shared index; repair conflicting archives after a long run.
- **Observation/evidence:** The first archive API admitted unchecked cells, forgot its active set on
  reopen, and used whole-index rewrites that could lose concurrent submissions.
- **Interpretation:** A fast population built on one corrupt state creates more convincing-looking
  bad evidence. Verification and serialized ownership must precede scale.
- **Consequence:** The first official expedition remains single-process. Parallel exploration is
  deferred until workers submit immutable candidates through the coordinator.

## DR-0025 — Treat the completion-foundation audit as experiment data

- **Date:** 2026-07-19
- **Status:** Failed designs found, fixed, and regression-tested before Q1
- **Scope:** Archive integrity, replay truth, resume, crash recovery, and privacy
- **Information label:** Infrastructure; no actor result
- **Decision:** Block the first long run until every high-confidence audit failure either fails
  closed in a regression or is declared as a scaling gate.
- **Alternatives considered:** Rely on the coordinator's intended call order; call passing unit tests
  sufficient; defer recovery/privacy problems until a real campaign fails.
- **Observation/evidence:** The audit reproduced five consequential failures: selected-cell counts
  could make an evicted archive impossible to resume; an unchecked milestone could be laundered
  through a same-stage child; an exact replay accepted forged niche/quality fields; a torn final
  audit write made the store unopenable; and resume deleted the earlier graceful-stop event from
  the narrative trace. The artifact scanner also skipped force-added files below `runs/`.
- **Interpretation:** Content hashes protect bytes, not the authority or meaning of every field.
  “The normal runner would not do that” is not an integrity boundary.
- **Consequence:** Active checkpoints now retain only active selection counts; every ancestral
  boundary must pass its own replay gate; descriptor and canonical summary are recomputed; torn
  tails are privately preserved while complete corrupt lines fail; stop/resume events remain in
  the trace; and tracked files are scanned even below ignored run directories.
- **Revisit when:** Concurrency, store schemas, or replay authority changes.

## DR-0026 — Expand the milestone ladder to include mandatory progression gates

- **Date:** 2026-07-19
- **Status:** Completed for the current catalog; further omissions remain auditable
- **Scope:** Sealed completion referee and archive quality
- **Decision:** Expand the ordered catalog from 46 to 55 outcomes by naming Rocket Hideout, Lift
  Key, Silph Scope, Pokémon Tower, Silph Co., Card Key, Safari Zone, Gold Teeth, and HM04 Strength.
- **Alternatives considered:** Reward only badges and large story events; rely on arbitrary item or
  event counts; assume a shorter state in the same niche is always preferable.
- **Observation/evidence:** The first catalog omitted items that are mandatory to unlock later
  routes. A key-bearing state could therefore lose a same-niche quality comparison to a shorter
  state without the required key. IDs and Hall-of-Fame semantics were checked against the pinned
  `pret/pokered` revision.
- **Interpretation:** A goal graph cannot guide composition if it is blind to required capabilities.
- **Consequence:** Key acquisitions now create named, testable progress. The catalog's full
  conditions receive a semantic hash in every frontier manifest so changed truth cannot silently
  reopen an old store.
- **Revisit when:** Q2 exposes another required gate or a route-order ambiguity.

## DR-0027 — Trial a seeded-random suffix emitter for the first Q1 gate

- **Date:** 2026-07-19
- **Status:** Trialing; implemented defaults are not an adopted whole-game mechanism
- **Scope:** Q0/Q1 discovery runner
- **Information label:** `RANDOM-ACTION-EMITTER / PRIVILEGED-TRAINING-REFEREE / ARCHIVE-RESTORE / ACTION-LINEAGE`
- **Decision:** Begin with a seeded uniform action emitter, 32-action suffixes that double to 1,024,
  75% frontier selection, 10% low-tier rehearsal, one replay for local cells, and three for a new
  milestone. Freeze Q1 as the exact `left_home` milestone: two fresh seeds, at most 20,000
  exploration actions, one hour, and 2 GiB per seed.
- **Alternatives considered:** Immediately mutate recurrent policies; use the previously proposed
  256–4,096 range; call either the stairs or house exit a pass; launch an open-ended run.
- **Observation/evidence:** The simple emitter isolates archive/replay mechanics and creates a
  reproducible denominator. It receives neither pixels nor RAM, so calling it a pixel model would
  be false.
- **Interpretation:** The trainer can learn which stepping stones deserve compute while the current
  button emitter itself does not learn. This is a discovery baseline for choosing the next emitter.
- **Consequence:** For Q0/Q1, this entry supersedes DR-0013's proposed `PIXEL-ACTOR / POPULATION`
  label while retaining its checkpoint, ancestry, and replay architecture. Q2 must compare
  random/action-sequence, recurrent-policy, and hybrid emitters under matched budgets. Failure at
  `left_home` changes the emitter; it does not expand the budget silently.
- **Revisit when:** Both Q1 seeds finish or either exposes a safety/scaling blocker.

## DR-0028 — Refuse a multi-day campaign until replay and storage scale

- **Date:** 2026-07-19
- **Status:** Accepted blocker
- **Scope:** Performance and SSD retention
- **Decision:** Do not extrapolate the Q0 runner to 150 million actions. Stream action lineages,
  index replay counts, validate ancestry topologically, bound verification backlog, and define
  private-payload retention before Q2 or a multi-day campaign.
- **Alternatives considered:** Let the 150-million ceiling and 223 GiB of currently free SSD space
  serve as the only safeguards; delete all rejected failures; replay only at the final milestone.
- **Observation/evidence:** A 1,024-exploration-action real-ROM qualification admitted 75 cells and
  spent another 9,280 actions on exact replay—about 9.1 replay actions per exploration action—while
  remaining at `power_on`. The current implementation also materializes full lineages, rescans the
  audit ledger, can repeat ancestry validation, and retains rejected private payloads.
- **Interpretation:** More free disk does not fix superlinear verification work. Public failure
  records and private emulator payload retention are separable responsibilities.
- **Consequence:** Q1 may run under its small fixed bounds. A marathon is not authorized merely
  because Q1 code exists.
- **Revisit when:** Profiling demonstrates bounded resume, replay, and storage growth at a staged
  scale qualification.

## DR-0029 — Pass Q0 without pretending it was gameplay progress

- **Date:** 2026-07-19
- **Status:** Completed
- **Scope:** Real-ROM checkpoint-runner qualification
- **Information label:** `RANDOM-ACTION-EMITTER / PRIVILEGED-TRAINING-REFEREE / DEVELOPMENT`
- **Decision:** Mark the completion harness H0/Q0-ready, but leave H1 and Q1 open.
- **Alternatives considered:** Count Oak's introduction as game start; describe every archived
  visual niche as progress; begin the multi-day run after one clean smoke.
- **Observation/evidence:** The first 512-action run created 42 active cells; 42 of 42 exact replays
  passed, consuming 4,392 replay actions. Its latest frame reached Oak's introduction, while the
  referee correctly remained at `power_on`. A later run stopped cleanly at action 384, resumed to
  512 with its archive/RNG/counters intact, retained `stop_requested` and `run_resumed` in the
  trace, and passed 42 of 42 replays. Reviewed status hashes are
  `a53deba4242d80389eecfce1795131980114ad75b0981d4a01ea21ef3fbc98a3` and
  `161bf37477955774fd4a242b8ea60c2d41a31cdac7d73f5e3362b4762cc2e735`.
- **Interpretation:** The runner can remember honestly; it has not yet shown that its search can
  reach one useful playable transition.
- **Consequence:** The next claim opportunity is the predeclared two-seed `left_home` Q1 gate.
- **Revisit when:** Q1 finishes.

## DR-0030 — Accept H3 while failing the two-seed Q1 gate

- **Date:** 2026-07-19
- **Status:** Concluded; H3 accepted, Q1 robustness gate failed
- **Scope:** Two-seed `left_home` development trial
- **Information label:** `RANDOM-ACTION-EMITTER / PRIVILEGED-TRAINING-REFEREE / ARCHIVE-RESTORE / ACTION-LINEAGE`
- **Decision:** Report the complete result as one success in two seeds. Accept the narrow claim that
  the expedition reached and replayed `left_home`; do not describe Q1 as passed and do not rerun the
  unchanged random emitter with a larger budget.
- **Alternatives considered:** Call any one verified discovery a Q1 pass; discard the failed seed;
  extend seed `20260730` until it leaves the house; run more random seeds before changing design.
- **Observation/evidence:** Both seeds exhausted exactly 20,000 exploration actions with zero human
  interventions. Seed `20260730` stopped at `left_bedroom`. Seed `20260731` discovered `left_home`
  at action 17,832, preserved a shortest 419-action lineage, and passed all three promotion replays.
  The two runs passed 2,984 of 2,984 total replays. Their reviewed status hashes are
  `255fa5ee920fa20b0a239d04c499033c7877e397f81e2e5c3cadeaeedde2cd04` and
  `cc0898a011f87f2073365afb5852b22346f3b228956daefe00a8315ffd64ecc1`.
- **Interpretation:** Checkpoint memory can turn random action suffixes into cumulative, verified
  progress, but one success does not meet a two-seed reliability rule. The archive learned where to
  continue searching; the observation-free emitter learned nothing.
- **Consequence:** Preserve Q1 as the random checkpoint-search baseline. The next experiment changes
  the emitter and scheduler under the same target, seeds-per-condition, and exploration budget.
  H3 language is permitted; H1/H2 learned-policy language is not.
- **Revisit when:** A materially different emitter completes its matched `left_home` comparison.

## DR-0031 — Preserve both exact and stable milestone frames

- **Date:** 2026-07-19
- **Status:** Accepted recording requirement; implementation pending
- **Scope:** Narrative evidence without rewriting causal evidence
- **Decision:** Keep the exact frame captured when a semantic milestone fires, then separately record
  the first stable post-transition frame with its additional emulator frames and label. Never
  replace the exact frame with the prettier one.
- **Alternatives considered:** Use only the exact frame; delay all milestone detection until the
  screen looks stable; manually choose a later screenshot without recording the selection rule.
- **Observation/evidence:** The first `left_home` semantic state and all hashes replayed exactly, but
  its image was a dark transition frame. A later ordinary frame clearly showed Red outside.
- **Interpretation:** Machine-valid evidence and audience-readable evidence can require different
  frames. Keeping both makes the distinction visible instead of editing around it.
- **Consequence:** The next runner revision must account for stable-frame capture separately in the
  trace and action/frame budget. The Q1 exact frame remains the authority for the milestone event.
- **Revisit when:** The dual-frame recorder passes a transition-event integration check.

## DR-0032 — Repair the CI import boundary before extending the experiment

- **Date:** 2026-07-19
- **Status:** Completed
- **Scope:** GitHub Actions and contributor test entrypoint
- **Information label:** Infrastructure; no actor result
- **Decision:** Add the repository root to pytest's declared import path, rerun the exact failing
  command locally, and require both push- and pull-request-triggered jobs to pass before resuming
  experiment changes.
- **Alternatives considered:** Ignore the duplicate red checks because the package itself imported;
  change only the GitHub command to `python -m pytest`; remove the new artifact-guard regression.
- **Observation/evidence:** Both GitHub checks stopped during collection because
  `tests/test_artifact_guard.py` imported the repository's standalone `scripts` namespace, which
  was not on the console entrypoint's path. The artifact guard, documentation checker, and Ruff
  had already passed. With the explicit pytest path, 92 non-integration tests passed locally and
  both independent GitHub jobs returned success.
- **Interpretation:** This was a test-discovery configuration error, not evidence that the
  expedition or its safety guard failed. Keeping the regression matters because force-added
  private files below ignored run directories must remain detectable.
- **Consequence:** CI is green on the same branch before Archive v2 work begins. The fix is isolated
  from experiment behavior in its own commit.
- **Revisit when:** The repository layout or test runner changes.

## DR-0033 — Remove repeated ledger scans and per-action tree walks first

- **Date:** 2026-07-19
- **Status:** Completed and real-ROM tested
- **Scope:** First marathon-scaling foundation
- **Information label:** Infrastructure; no actor result
- **Decision:** Rebuild successful replay counts once from the validated hash-chained event log,
  update the in-memory index only after durable append, stream lineage actions segment by segment,
  validate ancestry topologically, and replace recursive per-action disk scans with bounded
  incremental monitoring plus periodic exact reconciliation.
- **Alternatives considered:** Add more SSD space; scan `events.jsonl` and the entire run tree on
  every query; weaken the event hash chain; wait to optimize until a multi-day run becomes slow.
- **Observation/evidence:** Q1 produced 1,300 cells in the successful store and 1,528 replay passes.
  After this change the reviewed store reopened in about 1.38 seconds and all replay counts were
  queried in about 0.00013 seconds. The full private-ROM suite passed 109 tests. Both GitHub jobs
  passed after publication.
- **Interpretation:** These changes make bookkeeping bounded without weakening replay truth. They
  do not yet reduce the number or length of emulator replays, so they are necessary but not
  sufficient for a two-day campaign.
- **Consequence:** The next scaling work may focus on verification policy and scheduling rather
  than repeatedly paying avoidable filesystem and ledger costs.
- **Revisit when:** A staged 100,000-action qualification exposes another superlinear operation.

## DR-0034 — Trial edge verification and bounded primary niches in Archive v2

- **Date:** 2026-07-19
- **Status:** Accepted and qualified under the bounded staged gate
- **Scope:** Q2 checkpoint search and training-curriculum generation
- **Information label:** `RANDOM-ACTION-EMITTER / PRIVILEGED-TRAINING-REFEREE / ARCHIVE-RESTORE / ACTION-LINEAGE`
- **Decision:** Make ordinary cells training-eligible after an exact parent-snapshot-to-child edge
  replay, while retaining three fresh complete power-on replays for every named milestone
  promotion. Group active cells by milestone, map, coarse position, and battle mode; treat visual
  class as a bounded alternative rather than an unlimited primary niche. Persist and verify at
  most one ordinary candidate per suffix, and give new milestone frontiers immediate bounded
  scheduling attention.
- **Alternatives considered:** Continue one full power-on replay for every eight-action capture;
  remove replay from local cells entirely; keep every 16-bit visual class as an independent arm;
  enlarge the archive until the backlog fits; allow a sampled local audit to support H3 language.
- **Observation/evidence:** Q1 admitted about 1.8 selectable cells per suffix opportunity and spent
  954,704 replay actions on 40,000 exploration actions. A scheduler that revisits one parent while
  admitting more than one new zero-visit arm cannot clear its own backlog. The successful named
  lineage itself contained only 419 actions.
- **Interpretation:** Search eligibility and public claim eligibility need different certificates.
  Exact edge composition can safely support training restores; H3/H4 authority remains with full
  power-on promotion replay.
- **Consequence:** Archive v2 reports edge and promotion costs separately; sampled composition
  auditing remains a follow-up. The first real-ROM qualification must demonstrate an ordinary
  edge-replay ratio no greater than 1.0, exact resume, bounded variants, and unchanged three-pass
  named promotion semantics before a long run is authorized.
- **Revisit when:** A deeper run exceeds the measured replay/file envelope or variant starvation
  appears despite the four-cell primary-niche cap.

## DR-0035 — Build Visual Apprentice v1 from self-generated routes

- **Date:** 2026-07-19
- **Status:** Accepted development design; no trained result yet
- **Scope:** First H2 learned-policy candidate
- **Information label:** `PIXEL-ACTOR / PRIVILEGED-TRAINING-REFEREE / ARCHIVE-RESTORE` during
  training; `PIXEL-ACTOR / POWER-ON / FIXED-POLICY` for the strongest evaluation
- **Decision:** Warm-start a small recurrent convolutional policy from replayed self-generated
  visual/action trajectories, then train recovery with recurrent PPO in a curriculum that expands
  backward from the house exit to power-on. Reset recurrent state at every curriculum and
  evaluation start.
- **Alternatives considered:** Expand the hashed Q table again; call the 419-action button list a
  learned model; use a human walkthrough as the primary teacher; train end-to-end sparse-reward PPO
  from power-on; run a thousand resident neural models on the 8 GB machine.
- **Observation/evidence:** Q1 now supplies one exact successful trajectory, which is sufficient for
  an intentional overfit pipeline smoke but not a generalization claim. The earlier table learners
  plateaued locally, the small evolutionary RNN collapsed into fragile action habits, and an
  open-loop lineage cannot recover after one changed state.
- **Interpretation:** The project's strongest story and experiment are the same question: can blind
  search turn one lucky accident into reusable visual knowledge? Demonstration, reverse curriculum,
  and learner-induced recovery states address different parts of that question.
- **Consequence:** Follow [Visual Apprentice v1](visual-apprentice.md). The first H2 claim requires
  one frozen policy to pass at least 45 of 50 branch-grouped held-out local starts; the later
  power-on composition gate requires at least 18 of 20 declared attempts. Until then the model is
  described only as implemented, training, or developmental.
- **Revisit when:** The overfit smoke, multi-lineage dataset gate, or first frozen evaluation fails.

## DR-0036 — Keep Q1 historical and make Archive v2 fail closed

- **Date:** 2026-07-19
- **Status:** Implemented, private-ROM checked, and staged qualification passed
- **Scope:** Archive v2 trust, restart, interruption, and private-file boundaries
- **Information label:** Infrastructure for `RANDOM-ACTION-EMITTER / PRIVILEGED-TRAINING-REFEREE`
- **Decision:** Stamp new expedition stores as v2 and keep v1 stores under their original
  full-power-on reporting semantics while making them ineligible for v2 resume, mutable archive
  selection, or edge certificates. Count a v2 replay certificate only when its complete envelope
  matches the stored cell. Bind each runner checkpoint to the exact durable event sequence and hash
  head, event byte boundary, ordered cell set, and immutable embedded frame. Preserve every
  recognized post-checkpoint transaction tail—including orphan cell metadata and a torn final
  event—in a content-addressed private recovery bundle before exact rollback. Make that rollback
  an idempotent transaction tied to the full checkpoint hash and revalidate the checkpoint view
  before applying even a pending rollback. Reject certainly uncompetitive ordinary candidates
  before persistence, and allow long promotion replays to stop for explicit requests or disk
  emergencies.
- **Alternatives considered:** Silently treat a v1 full replay as a v2 edge certificate; accept a
  passing milestone ID without checking hashes and descriptor; resume an old RNG/archive checkpoint
  atop a newer event ledger; write every suffix candidate and rely on the 4 GiB limit; ignore STOP
  until all full-lineage promotion replays finish.
- **Observation/evidence:** Review found that each alternative could preserve a misleading claim or
  turn the 150-million-action ceiling into millions of private files. Both Q1 stores reopen with
  zero historical deficits and are refused by the mutable v2 archive. The complete private-ROM
  suite passes 121 tests after the boundary changes. Simulated crashes after selection, cell
  metadata, complete or partial event append, cell index update, event-log rollback, and index
  rollback preserve the abandoned tail and return to the exact checkpoint. A divergent live
  dashboard frame resumes from the embedded checkpoint frame; behind or tampered prefixes and
  invalid checkpoints, frames, or bound pending transactions fail closed.
- **Interpretation:** Backward compatibility means preserving what old evidence proved, not granting
  it new authority. Exact resume and bounded storage arrivals are scientific controls as well as
  operational safeguards.
- **Consequence:** Archive v2 may support the bounded Visual Apprentice data and curriculum pilot.
  A multi-day headline run still requires an actual learned/optimized emitter plus explicit
  extreme-depth eligibility and private-payload retention decisions.
- **Revisit when:** A measured recovery contradicts the simulated and staged crash evidence.

## DR-0037 — Pass Archive v2 and move the active gate to learning

- **Date:** 2026-07-19
- **Status:** Passed; bounded engineering qualification complete
- **Scope:** Archive v2 go/no-go decision and next experiment
- **Information label:** `RANDOM-ACTION-EMITTER / PRIVILEGED-TRAINING-REFEREE / ARCHIVE-RESTORE / ACTION-LINEAGE`
- **Decision:** Accept Archive v2 as the substrate for the next bounded Visual Apprentice pilot
  after one continuous, one graceful-stop/resume, and one guarded hard-crash real-ROM run reach
  exact 4,096-action limits and pass the post-run invariant audit. Preserve the failed 2,048-action
  stop-timing attempt in the denominator instead of calling it resume evidence.
- **Alternatives considered:** Start a two-day random run immediately; omit the hard crash because
  simulated tests passed; treat a stop request that arrived after the budget as a resume trial;
  compare only screenshots; discard the recovery tail after rollback.
- **Observation/evidence:** The continuous and crash twins each finished with 78 attempts, 18
  stored cells, 14 active cells, four primary niches, 453 edge-replay actions, 831 promotion-replay
  actions, and `game_started`. Their complete deterministic terminal state matched after excluding
  elapsed/timestamp and recovery-ledger identity. The crash bundle preserved one 396-byte selection
  event. The graceful trial stopped at action 1,023 and resumed to 4,096. Every replay passed,
  ordinary edge ratio stayed at or below 0.111, exact disk totals reconciled, and reviewed public
  files exposed no ROM filename or private path.
- **Interpretation:** The project removed the observed Q1 replay explosion without weakening named
  promotion evidence, and it can now distinguish interruption recovery from an edited highlight.
  This qualifies memory and verification—not the random button emitter.
- **Consequence:** Begin the Visual Apprentice data extraction and deliberate overfit smoke. Do
  not spend the newly available compute budget on a longer copy of the failed random-emitter gate.
  Retain the [complete result](../experiments/archive-v2-qualification/README.md) as the engineering
  denominator for later learned-emitter comparisons.
- **Revisit when:** The overfit smoke finishes, or the learner needs a store behavior that the
  bounded qualification did not exercise.

## Unresolved decisions

These are questions, not hidden commitments. Each becomes a numbered entry when evidence supports
a choice.

- Which emitter wins the Q2 matched comparison after the random-suffix Q1 denominator?
- Whether Archive v2's provisional three visual alternatives per primary niche survive the staged
  scaling qualification; the key structure itself is trialing under DR-0034.
- Which milestone-tier reservations and private-payload retention policy preserve failures without
  making the SSD the archive-capacity limit?
- What suffix-length scheduler beats the provisional 32–1,024 rule on verified progress per action?
- Should the richer learned controller be one network with several heads or a learned router among
  navigation, dialogue, menu, and battle policies?
- Whether behavioral cloning plus recurrent PPO beats its cloning-only ablation under the frozen
  Visual Apprentice protocol in DR-0035.
- What held-out perturbations and success threshold justify H6 reliability?
