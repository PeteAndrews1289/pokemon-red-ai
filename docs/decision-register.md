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

## DR-0038 — Make the first learner prove the whole loop on one route

- **Date:** 2026-07-19
- **Status:** Implemented and unit checked; real-ROM qualification pending
- **Scope:** Visual Apprentice Stage 0
- **Information label:** `PIXEL-ACTOR / SELF-GENERATED-DEMONSTRATION` for cloning;
  `PIXEL-ACTOR / POWER-ON / FIXED-POLICY` for the live gate
- **Decision:** Extract the one certified 419-action Q1 promotion through an immutable store view,
  freeze its 420 processed decision-boundary frames and labels as a hashed private dataset, and
  deliberately overfit one 468,312-parameter CNN-LSTM with direct PyTorch 2.13 on CPU. Require
  exact teacher-forced predictions, exact predicted-previous-action feedback, identical frozen
  reload behavior, and a single clean-power-on emulator attempt within 1,000 actions. Keep data,
  offline, and live statuses separate; Stage 0 passes only when all three pass.
- **Alternatives considered:** Begin recurrent PPO immediately; use Stable-Baselines3 as a
  behavioral-cloning framework; feed route position or checkpoint identity to make memorization
  easy; treat offline action accuracy as emulator success; install a broad imitation-learning
  stack; train with Metal acceleration on the 8 GB host; silently select any of the 162 Q1 cells
  that inherited `left_home`.
- **Observation/evidence:** Only cell `4618cb56f99c95b594534474` is the certified Q1 promotion. It
  has a 419-action lineage, three historical complete power-on certificates, and zero deficits.
  Direct PyTorch supplies the recurrent supervised learner without the environment, rollout, and
  value-loss machinery needed only for later PPO. The implemented synthetic suite checks immutable
  extraction, 419/420 alignment, tamper refusal, parameter count, recurrent reset, and shape
  contracts.
- **Interpretation:** Before spending a two-day budget on interactive learning, the project should
  prove that pixels become labels, labels become stable parameters, and those parameters can drive
  the same emulator. This smoke is intentionally allowed to memorize time and one route; that is
  the limitation being measured, not a hidden generalization claim.
- **Consequence:** Without exact live route equality, the strongest possible Stage-0 sentence is
  “one frozen model exactly fit its single trajectory offline and reached `left_home` once in
  closed loop.” A failed live gate remains evidence of
  compounding error. Stable-Baselines3/sb3-contrib and recurrent PPO remain deferred to recovery
  training. Private arrays and checkpoints are now rejected by the repository publication guard.
- **Revisit when:** The real-ROM extraction, overfit, or clean-power-on gate finishes; any pass then
  triggers independent route and perturbation collection rather than an H2 claim.

## DR-0039 — Pass Stage 0 without calling memorization a robust skill

- **Date:** 2026-07-19
- **Status:** Completed; Stage-0 composite qualification passed
- **Scope:** Visual Apprentice data, offline training, frozen reload, and clean-power-on gate
- **Information label:** `PIXEL-ACTOR / SELF-GENERATED-DEMONSTRATION` during cloning;
  `PIXEL-ACTOR / POWER-ON / FIXED-POLICY` during the live attempt
- **Decision:** Accept the first complete Stage-0 run because two independent captures agreed,
  teacher-forced and predicted-feedback evaluation both reached 419/419, the frozen reload was
  identical, and the policy reached exact `left_home` within the declared 1,000-action ceiling.
  Report exact route equality and retain the single-attempt denominator. Do not promote this result
  to H2.
- **Alternatives considered:** Count offline accuracy alone; omit the second extraction; rerun the
  live attempt until it succeeded; describe one closed-loop success as a learned house-exit skill;
  hide exact action equality because it weakens the apparent result.
- **Observation/evidence:** Training finished after 316 epochs and 99.112 seconds with 419/419
  labels under both feedback modes. The frozen reload produced the same result. On the one planned
  live attempt, the policy reached `game_started` at action 243, `left_bedroom` at 302, and
  `left_home` at 419. All 419 selected actions exactly matched the sole training route. The sealed
  composite bundle SHA-256 is
  `236da389cc2ee18661d0e52ae58525cdd0c42b6068427a5ac34fd5cf662cfdde`.
- **Interpretation:** The full neural pipeline now connects: deterministic pixels become labels,
  labels become durable model parameters, and one frozen model drives the emulator successfully.
  Exact route equality is simultaneously strong integrity evidence and evidence that Stage 0 did
  not test recovery or generalization.
- **Consequence:** Preserve the [complete Stage-0 result](../experiments/visual-apprentice-stage0/README.md).
  Begin a reverse checkpoint curriculum with zero recurrent state at every local start and keep all
  failed attempts visible. The next target is repeated recovery success, not a longer replay of
  the memorized route.
- **Revisit when:** A frozen checkpoint is evaluated on predeclared held-out local starts.
- **Supersedes / superseded by:** Completes DR-0038's pending real-ROM gate; does not supersede
  DR-0035's H2 requirements.

## DR-0040 — Trial reverse-curriculum self-imitation before recurrent PPO

- **Date:** 2026-07-19
- **Status:** Trialing; bounded overnight development run authorized
- **Scope:** First interactive Visual Apprentice learning pilot after Stage 0
- **Information label:** `PIXEL-ACTOR / PRIVILEGED-TRAINING-REFEREE / FIXED-SNAPSHOT` during
  curriculum training; no H2 evaluation label yet
- **Decision:** Reconstruct seven trainer-owned starts with 8, 16, 32, 64, 128, 256, and 419
  demonstration actions remaining. Reset the actor's recurrent state, previous action, and visual
  history at each start. Prime each suffix explicitly from the certified demonstration, sample
  bounded pixel-policy attempts, and apply self-imitation gradients only to attempts that actually
  reach `left_home`. Promote a rung only after 27/30 successes twice. Run one CPU learner for at
  most eight hours, 15 million emulator actions, 1.5 GiB resident memory, or 2 million actions
  without promotion while retaining at least 50 GiB free on the external SSD.
- **Alternatives considered:** Repeat the saturated Stage-0 overfit for eight hours; start recurrent
  PPO from power-on; train on failed sampled actions; use four simultaneous Torch learners; restore
  the demonstration's LSTM state beside each snapshot; call repeated deterministic replays a
  success rate; run until the clock expires even when the curve is flat.
- **Observation/evidence:** Stage 0 already proved exact one-route connection at 419/419, while the
  preceding clean-start evolutionary trials showed that paying the full opening horizon on every
  lifetime prevents useful local learning. Reverse curriculum directly tests the missing recovery
  boundary without adding a value head, reward-weight tuning, or a second deep-learning framework
  on the night of launch.
- **Interpretation:** Success selection makes the interactive update causal: an attempt that reaches
  the declared boundary can reinforce its own action sequence; a failure remains evidence but does
  not teach the policy to fail. Demonstration priming and learner-generated updates must remain
  separate in every status and ledger.
- **Consequence:** First run a short real-ROM canary that exercises ladder reconstruction, weight
  changes, dashboard heartbeat, checkpoint hashing, and stop behavior. If it passes, launch the
  bounded eight-hour development run. Call the result a reverse-curriculum self-imitation pilot,
  not a held-out evaluation or proof that the model learned Pokémon Red. Promotion windows contain
  online updates and are scheduling heuristics, not fixed-policy confidence intervals. A hard-crash
  resume remains diagnostic until append-only post-checkpoint tails can be reconciled without
  duplicate rows.
- **Revisit when:** The overnight run stops, a rung stagnates, or the first learner checkpoint is
  ready for a separately frozen held-out evaluation.
- **Supersedes / superseded by:** Operationalizes DR-0039's next step; recurrent PPO remains deferred
  rather than rejected.

## DR-0041 — Turn the house exit into a frontier, not a terminal goal

- **Date:** 2026-07-20
- **Status:** Trialing; eight-hour full-game development campaign authorized
- **Scope:** Handoff from the Visual Apprentice local curriculum to the Hall-of-Fame expedition
- **Information label:** `PIXEL-ACTOR + SEEDED-EXPLORATION / PRIVILEGED-TRAINING-REFEREE /
  ARCHIVE-RESTORE / HYBRID-SYSTEM`
- **Decision:** Use the completed reverse-curriculum model as one frozen visual action emitter
  inside Archive v2. Reset its recurrent memory after every checkpoint restore. Before the
  verified `left_home` frontier, replace 2% of its argmax actions with seeded exploration; at and
  after that frontier, replace 35%. Continue checkpoint-assisted exploration across the complete
  55-milestone referee until the Hall of Fame or an eight-hour/action/storage boundary. Preserve
  exact local edge verification and three fresh power-on replays for every named promotion.
- **Alternatives considered:** Stop after leaving the house; repeat the completed house curriculum
  for eight hours; claim the frozen network already knows unseen towns and battles; use a purely
  random power-on expedition and ignore the learned opening; update neural weights on arbitrary
  failures without a validated success target; hard-code a walkthrough beyond the house.
- **Observation/evidence:** The full 27/30-twice curriculum completed all seven rungs in 233.9
  seconds. Across 480 adaptive attempts it recorded 451 successful house exits, and the final
  419-action-remaining rung passed two consecutive 29/30 windows. Because `left_home` was coded as
  terminal, the process then stopped normally instead of using the remaining overnight budget.
- **Interpretation:** The narrow skill is no longer the compute bottleneck. The next uncertainty is
  whether a frozen visual prior plus explicit stochastic exploration can create later verified
  frontiers. The network is not claimed to learn unseen game mechanics during this campaign; the
  archive and scheduler are the components that accumulate progress tonight.
- **Consequence:** The dashboard must show the latest gameplay frame, current suffix, best verified
  milestone, next named milestone, active frontier, replay costs, and the hybrid information
  boundary. `left_home` becomes one promotion among many. Only a machine-checked Hall-of-Fame
  promotion can end the run as game completion.
- **Revisit when:** The eight-hour campaign ends, reaches a later named milestone, or shows that the
  frozen house policy prevents useful post-house exploration.
- **Supersedes / superseded by:** Extends DR-0040 beyond its deliberately local terminal boundary.

## DR-0042 — Preserve recurrent continuity with longer archive suffixes

- **Date:** 2026-07-20
- **Status:** Trialing in the eight-hour development campaign
- **Scope:** Archive v2 suffix scheduling for the frozen Visual Apprentice handoff
- **Decision:** Replace the provisional 32-action minimum with a 512-action minimum while retaining
  a 2,048-action maximum and eight attempts per expansion. Restart the overnight clock from a fresh
  power-on and seed after rejecting the first short-fragment launch.
- **Alternatives considered:** Leave the weak launch running because it was technically active;
  disable archive restores; carry hidden recurrent state across restored emulator checkpoints;
  return to fixed 512-action suffixes; reseed repeatedly until one opening happened to look good.
- **Observation/evidence:** The fixed-512 canary reached `left_home` and continued afterward. The
  first overnight launch used a 32-action minimum, made 184 attempts in 11,767 actions, and reached
  `left_bedroom` but not `left_home`. The fresh 512–2,048 launch reached `met_professor_oak` within
  its first 3,135 actions and had 41/41 passing replay checks at that observation.
- **Interpretation:** Resetting the frozen actor's LSTM at every archive restore is the honest state
  boundary, but very short suffixes can deny it enough continuous visual history to reproduce its
  learned opening. Longer suffixes spend more actions per attempt in exchange for coherent local
  behavior. One successful launch is configuration evidence, not a general performance estimate.
- **Consequence:** Keep the rejected launch as failure evidence. Treat the 512-action floor as a
  development setting pending matched suffix-length trials; do not silently carry recurrent state
  across checkpoints that did not save it.
- **Revisit when:** The eight-hour campaign ends or enough milestone/action data exists to compare
  progress efficiency across suffix lengths.
- **Supersedes / superseded by:** Refines DR-0041's campaign configuration without changing its
  information boundary or Hall-of-Fame terminal condition.

## DR-0043 — Make every verified milestone a learning boundary

- **Date:** 2026-07-20
- **Status:** Implemented; mechanism canary passed, Forest qualification pending
- **Scope:** Full-game successor to the frozen apprentice handoff
- **Information label:** `PIXEL-ACTOR / PRIVILEGED-TRAINING-REFEREE / ARCHIVE-RESTORE /
  HYBRID-SYSTEM`; later frozen evaluations remain separate
- **Decision:** Apply one generic ratchet to all 55 milestones. Begin with the completed apprentice
  weights, increase exploration from 35% toward 100% during a plateau, balance frontier selection
  across maps, allow two bounded random loop-escape bursts, and update the policy only from the
  pixel/action suffix of a newly promoted milestone after its exact edge replay and three complete
  power-on replays pass. Preserve bounded earlier-milestone exemplars and an anchor to the initial
  parameters. Record dense trainer rewards now, but defer learning from failed/rewarded steps to a
  matched recurrent-PPO ablation.
- **Alternatives considered:** Increase archive capacity again; let the frozen house policy retain
  65% control forever; train from every random failure; hard-code Viridian Forest or later routes;
  implement late-game milestones as separate runners; adopt PPO before a verify-before-update
  baseline exists; discard checkpoint provenance to make model resume easier.
- **Observation/evidence:** The handoff reached the Pokédex in about 68 minutes and then went more
  than five hours without the next promotion. Visual loops ended 91.9% of measured suffixes, while
  the active archive was well below its 8,192-cell ceiling. The constraint was useful action and
  compute allocation, not table capacity. Exact replay integrity remained perfect at the measured
  interruption. The first learner canary then completed 11,495 actions around an intentional
  stop/resume, promoted five milestones through choosing a starter, learned 763 verified-success
  actions in 38 updates, and passed 49/49 replay checks. Resume matched the checkpointed learner
  file and parameter hashes exactly before further action. A second seed stopped at `left_home`
  after 12,000 actions with 52/52 replay checks; its non-terminal twin also resumed exactly at
  action 8,045 and reached 11,858 actions with 55/55 checks. Both outcomes remain in the record.
- **Interpretation:** Archive memory can retain location but cannot make a frozen local model learn
  unseen navigation, dialogue, or battle behavior. A verified success is the strongest available
  causal teaching event. Using the canonical catalogue makes the mechanism stage-independent while
  preserving the distinction between assisted training and clean-policy evaluation.
- **Consequence:** Frontier Apprentice owns the next Viridian-Forest qualification, but its code
  must already target Hall of Fame. The dashboard and trace expose rewards, updates, exploration,
  loop escapes, milestones, and parameter hashes. Only a separately frozen power-on attempt may
  support H5 language.
- **Revisit when:** The real-ROM canary completes, the Forest gate passes or fails, or recurrent PPO
  is ready for a matched reward/archive comparison.
- **Supersedes / superseded by:** Supersedes DR-0041's frozen post-house actor as the primary
  learning direction; retains DR-0041 and DR-0042 as baseline evidence.

## DR-0044 — Let failures teach through parallel recurrent PPO

- **Date:** 2026-07-20
- **Status:** Implemented; pixels and privileged canaries passed, long pixels trial authorized
- **Scope:** Full-game learner successor and Whidden-inspired comparison lane
- **Information label:** Primary lane is `PIXEL-ACTOR / PRIVILEGED-TRAINING-REFEREE / PPO /
  ARCHIVE-RESTORE`; comparator is `PIXEL+RAM-ACTOR / PPO / ARCHIVE-RESTORE`
- **Decision:** Add a shared recurrent-PPO policy collecting from four simultaneous emulator
  environments. Warm-start the exact Visual/Frontier Apprentice pixel encoder, actor LSTM, and
  action head. Train from every rollout using the existing dense full-game reward ledger, but let
  only one exact parent-edge replay plus three exact power-on replays add a new named-milestone
  curriculum state. Freeze that starting curriculum from one atomic Archive-v2 checkpoint. Keep
  pixels-only and 24-value privileged actor modes separately labeled. Preserve model/optimizer
  resume while disclosing that partially collected environment rollouts restart.
- **Alternatives considered:** Continue verify-only self-imitation indefinitely; replace the
  referee with reward-only milestone claims; run the privileged actor without labeling its RAM;
  start every episode from one hand-selected save; copy another repository wholesale; run six or
  more workers because more windows look more impressive; discard the earlier campaign rather
  than use it as a baseline and verified curriculum source.
- **Observation/evidence:** The frozen handoff selected 18 replay-verified starting niches through
  Route 1. A one-environment pixels canary completed 256 actions and eight PPO updates with a
  hash-matched checkpoint. Two-, four-, and six-environment benchmarks measured 178.06, 419.34,
  and 351.39 combined actions/s while the earlier learner still occupied one core. A privileged
  two-environment canary also completed real optimizer updates. The production-shaped four-worker
  canary used 256-step rollouts, batch size 256, four epochs, and 4,096-action episodes; it
  completed 2,048 actions and two updates at 218.65 actions/s, wrote all worker frames, and
  finalized status correctly. These are mechanism checks, not gameplay-performance evidence.
- **Interpretation:** The Frontier Apprentice's causal teaching rule was auditable but too sparse:
  it ignored almost every failure. PPO is the appropriate next ablation because it changes the
  learning rule while retaining the verified archive, canonical referee, action cadence, initial
  neural prior, and narrative instrumentation. Four workers use the M1 efficiently; six reduce
  throughput once emulator and optimizer contention are included.
- **Consequence:** Finish the active Frontier Apprentice run as a baseline only until the PPO
  replacement passes its production canary, then stop it cleanly and launch the long pixels-only
  PPO campaign with four environments and the unchanged 150-million-action safety ceiling. Keep
  the privileged mode available for a later matched comparator rather than mixing both information
  regimes into one headline run. Report rewards, coverage, updates, and verified promotions as
  different facts.
- **Revisit when:** The first long campaign reaches a later milestone, plateaus at its starting
  frontier, stops unexpectedly, or accumulates enough data for a matched privileged comparator.
- **Supersedes / superseded by:** Does not erase DR-0043; turns its deferred recurrent-PPO ablation
  into the primary long-run learning trial while preserving Frontier Apprentice as the verify-only
  baseline.

## DR-0045 — Do not repay familiar territory after every PPO reset

- **Date:** 2026-07-20
- **Status:** Implemented; reset and production-shape canaries passed
- **Scope:** Parallel PPO dense novelty and checkpoint semantics
- **Information label:** unchanged `PIXEL-ACTOR / PRIVILEGED-TRAINING-REFEREE / PPO /
  ARCHIVE-RESTORE`; novelty remains trainer-only
- **Decision:** Persist full-game reward memory for each emulator worker across episode resets and
  graceful resumes. Prime every restored parent into existing memory before scoring. Content-hash
  each worker's versioned compressed memory and bind all worker files into the PPO checkpoint.
  Restart the long trial from the original Frontier Apprentice weights rather than resume weights
  already optimized against the flawed reward.
- **Alternatives considered:** Let the 24-hour run continue because its optimizer was healthy;
  reduce only the coordinate reward; share a lock-protected novelty set across subprocesses on
  every action; retain contaminated PPO weights; hide the intervention; count episode-local
  novelty as global coverage.
- **Observation/evidence:** Version 1 completed 862,212 actions and 208 episodes without advancing
  beyond Route 1. In a late 238,592-action slice it paid for 1,784 episode-local new positions but
  added only five globally unique positions. Entropy recovered, so simple action collapse was not
  the complete explanation. The one-worker version-2 canary crossed four episode lifetimes and
  persisted 38 positions, four maps, and two warps with matching hashes. The four-worker
  production-shape canary completed 2,048 actions, eight episodes, two rollout updates, four
  distinct memories, and exact model/memory hash checks.
- **Interpretation:** The agent was learning the supplied objective: repeat a familiar profitable
  route after each reset. That is optimizer progress without task progress. Per-worker campaign
  memory removes the cheap repeat while avoiding a synchronization call on every emulator action.
  It still permits the same discovery to pay once per worker, a disclosed compromise for CPU
  throughput.
- **Consequence:** Preserve the full version-1 run as negative evidence, bump the PPO protocol, and
  launch version 2 from the uncontaminated Frontier Apprentice seed. The dashboard must disclose
  `persistent per worker across episodes and resumes`. Any future resume fails closed if a novelty
  file is missing or its hash differs.
- **Revisit when:** Version 2 reaches one hour, promotes a milestone, shows another coverage
  plateau, or demonstrates that four independent novelty memories still overpay shared behavior.
- **Supersedes / superseded by:** Refines DR-0044's reward semantics without changing its actor
  boundary, replay gate, worker count, or Hall-of-Fame claim rule.

## DR-0046 — Reward battle progress, not the closing transition

- **Date:** 2026-07-20
- **Status:** Implemented; unit, real-battle, and graceful-resume canaries passed
- **Scope:** Parallel PPO battle shaping, outcome telemetry, and resume boundary
- **Information label:** unchanged `PIXEL-ACTOR / PRIVILEGED-TRAINING-REFEREE / PPO /
  ARCHIVE-RESTORE`; experience remains trainer-only
- **Decision:** Remove the unconditional reward for any active-to-inactive battle transition. Count
  battle starts, durable successes, no-progress exits, and blackouts separately. Pay a reduced
  success reward only after experience or capture progress occurred in that battle. Pay bounded
  experience shaping only when total party experience exceeds that worker's persistent lifetime
  record. Start version 3 from the uncontaminated Frontier Apprentice seed and reject version-2
  resume files explicitly.
- **Alternatives considered:** Continue version 2 because early coverage improved; infer victory
  from the battle-closing screen; penalize every escape; reward damage to opponent HP; resume the
  version-2 policy under changed rewards; remove battle learning signals entirely.
- **Observation/evidence:** The preserved version-2 run stopped cleanly after 3,649.552 seconds at
  1,064,964 actions, 1,040 updates, 260 episodes, 515 global positions, Route 1, and zero verified
  promotions or verification failures. It paid 10,030 reward for 1,003 battle endings. From the
  358,404-action observation to the final checkpoint, another 706,560 actions added only 26 global
  positions. Current frames had repeatedly shown workers in battles and around Oak's lab. The PPO
  optimizer retained action entropy, so the evidence fit objective exploitation better than a
  broken trainer or frozen policy. The final model and all four novelty hashes matched.
- **Interpretation:** `battle ended` confounded victory, capture, escape, and other exits. It made a
  cheap transition ten times more valuable than the intended version-3 success signal. Experience
  and ownership changes are durable consequences; using them as trainer evidence avoids guessing
  from pixels without giving either value to the pixels-only actor.
- **Consequence:** The live dashboard and hourly chronicle expose successful and no-progress battle
  exits as separate denominators. Experience is decoded from the documented three-byte party
  structure, capped at 500 newly record-setting points per observation, and retained in each
  hash-bound novelty checkpoint. The protocol becomes `parallel-recurrent-ppo-v3`.
- **Qualification evidence:** The first real-ROM canary completed 8,192 actions, 64 PPO updates,
  and eight episodes. It observed one battle start, 24 experience points, and one corresponding
  success; the ledger contained `experience_gain=0.48` and `battle_success=2` with no generic battle
  ending reward. Its final model and novelty hashes matched. A second canary stopped gracefully at
  action 7,607, restored the hash-validated version-3 model and experience memory, and completed its
  original 8,192-action ceiling with 64 total updates.
  A clean-commit, production-shaped canary then ran four workers for 2,048 combined actions and two
  full updates at 376.10 actions/s, wrote all four frames, and matched the model plus all four
  worker-memory hashes.
- **Narrative value:** This is the second clean act break for a future video: the model did not
  disobey its objective; it found the easiest literal interpretation. Place the rising battle
  reward beside a flat verified-milestone line, then reveal that “ending” never meant “winning.”
- **Revisit when:** The version-3 canary classifies real battles, the fresh trial reaches one hour,
  successful battles dominate return again, or sparse victory evidence prevents combat learning.
- **Supersedes / superseded by:** Refines DR-0045 without changing its persistent novelty design,
  four-worker shape, actor input, replay gate, or Hall-of-Fame completion rule.

## DR-0047 — Reward battle-local progress and terminate classified loops

- **Date:** 2026-07-20
- **Status:** Implemented; unit and real-ROM qualification passed
- **Scope:** Parallel PPO Version 4 observation history, battle shaping, episode horizon, and loop
  telemetry
- **Information label:** `PIXEL-ACTOR / PRIVILEGED-TRAINING-REFEREE / PPO / ARCHIVE-RESTORE`;
  enemy HP and loop state remain trainer-only
- **Decision:** Start Version 4 fresh. Give the actor three recent self-actions, extend episodes to
  16,384 actions, pay bounded credit for reducing live opponent HP, and end low-diversity visual
  cycles after 128 stagnant actions or general no-progress episodes after 1,024 stagnant actions.
  Preserve persistent campaign novelty and the replay-verification gate unchanged.
- **Alternatives considered:** Resume Version 3; copy the full PWhiddy Version-2 observation;
  increase the horizon to 163,840 immediately; reward healing; use coordinate frequency alone as a
  loop detector; penalize all battle exits.
- **Observation/evidence:** Version 3 completed 1,147,988 actions and 1,121 updates, but its nine
  successful battles were outnumbered by 110 no-progress exits and it remained at Route 1. The
  reference policy benefits from direct health, badge, event, and visited-map inputs and therefore
  cannot be imported without changing the experiment. Its longer horizon and three-action history
  are compatible with our declared actor boundary. Its coordinate `stuck` term does not classify
  visual menu cycles and its coordinate memory resets per episode.
- **Consequence:** Protocol identifiers become `parallel-recurrent-ppo-v4` and
  `battle-local-credit-and-stagnation-v1`. Version-3 weights are retained but ineligible for resume.
  Dashboard and narrative records expose opponent-damage credit, visual-cycle exits, long
  stagnations, and all ordinary battle outcomes.
- **Qualification evidence:** A 65,536-action stress canary exercised damage credit, durable battle
  outcomes, and both loop classes, but review found that its inherited previous-action weights had
  been placed in the oldest new history slot. It remains prequalification evidence. After remapping
  those weights to the newest slot and adding a tensor test, the corrected four-worker build
  completed 16,384 actions and 16 updates in 57.035 seconds. It recorded three battle starts, 5.412
  damage credit, two durable successes, one blackout, five visual cycles, and one long stagnation.
  No promotion or verification failed, and the model plus all four novelty memories matched their
  checkpoint hashes. Route 1 remained the verified frontier.
- **Narrative value:** The next act is about the missing middle. Version 3 could recognize victory
  after it happened; Version 4 can credit the sequence that makes victory possible and can name the
  loops that previously disappeared into a generic timeout.
- **Revisit when:** The first matched long run reaches its declared boundary, shows another reward
  loophole, or records a verified promotion.
- **Supersedes / superseded by:** Extends DR-0046 while keeping durable success classification and
  explicitly changing the local observation history and episode horizon.

## DR-0048 — Replace passive frontier waiting with an assisted micro-curriculum

- **Date:** 2026-07-20
- **Status:** Implemented; real-ROM engineering canary passed, long lesson trial authorized
- **Scope:** Parallel PPO Version 5 curriculum, observation boundary, local lesson reward, and
  eventual student handoff
- **Information label:** `PIXEL+TRAINER-MAP+GOAL-ACTOR / PPO / ARCHIVE-RESTORE / TEACHER`; this is
  not the pixels-only headline or final evaluation lane
- **Decision:** Preserve Version 4's verified curriculum and begin Version 5 from uncontaminated
  Frontier Apprentice weights. Give the teacher an episode-local visited-position map, the next
  canonical goal, a coarse navigation/interaction/battle hint, and map/goal context. Concentrate
  90 percent of resets at the furthest frontier. Insert `entered_viridian_mart` after Viridian
  City, pay bounded new-best-distance credit toward its doorway, and pay bounded progress through
  its trainer-only dialogue script. Keep exact replay admission unchanged. Treat later
  teacher-to-student distillation and restore-free power-on evaluation as mandatory separate gates.
- **Alternatives considered:** Merely run Version 4 longer; resume Version-4 PPO weights under a
  changed objective; provide the full collision map or a scripted path; expose target buttons;
  jump directly to one end-to-end Hall-of-Fame reward; train independent skill networks now; call
  checkpoint-assisted teacher success autonomous completion.
- **Observation/evidence:** Version 4 finished after 1,776,644 actions, 1,735 updates, and 968
  episodes. Its action-790,900 Viridian City candidate passed the one-edge/three-power-on replay
  gate, creating the first PPO promotion. The final hashes matched, but the run recorded 499 visual
  loops and 469 long stagnations. Its actor had neither episodic spatial memory nor a task identity.
  The Version-5 canary imported all 19 verified entries, ran four workers for 16,384 actions and 16
  updates, exercised 14.5 points of bounded Mart-approach credit, recorded zero verification
  failures, and ended with matching model plus worker-memory hashes. It did not enter the Mart.
- **Interpretation:** Version 4 proved that chance plus PPO can eventually extend the archive, but
  did not show a convincing trend toward reliably composing the remaining game. The missing
  structure is better treated as curriculum and representation design than as a request for more
  identical lottery tickets. An assisted teacher can answer whether explicit memory and task
  decomposition make the local skill learnable, provided its help remains visible and its result
  is not relabeled as pixels-only autonomy.
- **Consequence:** Protocol identifiers become `parallel-recurrent-ppo-v5` and
  `microcurriculum-map-memory-v1`. Version-4 PPO weights cannot resume. A completed Version-4 run
  may seed curriculum only after clean-terminal, hash, canonical-ordinal, entry-integrity, and
  unique-root validation. The dashboard names the current lesson and separates approach/dialogue
  credit from verified promotion. A promotion advances the lesson rather than ending the campaign.
- **Narrative value:** Version 4 supplies the first genuine breakthrough and the next complication:
  it reached the city, but could not remember where it had searched or what it was trying to do.
  Version 5 turns a distant command—“beat Pokémon”—into a visible school syllabus. The later reveal
  is equally important: passing with a map and lesson card is the teacher phase, not graduation.
- **Revisit when:** The teacher verifies entry into Viridian Mart, exhausts the declared long-run
  budget without doing so, exploits either local lesson, or accumulates enough verified teacher
  trajectories to start a pixels-only student ablation.
- **Supersedes / superseded by:** Extends DR-0047. It preserves Version 4 as the pixels-only result
  and explicitly changes the Version-5 actor boundary rather than retroactively redefining it.

## DR-0049 — Treat backtracking as active-goal progress, not failed exploration

- **Date:** 2026-07-20
- **Status:** Implemented; public/private tests, migration audit, and real-ROM engineering canary
  passed; long-run behavioral qualification pending
- **Scope:** Parallel PPO Version 5.1 reward ownership, return curriculum, route representation,
  watchdog semantics, and assisted observation boundary
- **Information label:** `PIXEL+TRAINER-MAP+ACTIVE-GOAL+ROUTE-ACTOR / PPO / ARCHIVE-RESTORE /
  TEACHER`; this remains an assisted curriculum lane
- **Decision:** Stop Version 5 cleanly at Oak's Parcel. Preserve all replay-verified curriculum but
  start fresh PPO weights under a new protocol. Expire local lesson rewards when their owning goal
  is complete. Insert item-qualified Route 1, Pallet Town, and Oak's Lab return milestones. Build
  topological guidance from certified or observed map transitions, allow certified edges to guide
  both directions, disclose the next route map and bounded distance to the assisted actor, pay
  signed potential change, and let distance improvement count as watchdog progress.
- **Alternatives considered:** Run Version 5 longer unchanged; enlarge novelty tables; increase
  reward for new maps or Pokédex discovery; script the Parcel route; add only one delivery reward;
  use positive-only proximity credit; resume Version-5 PPO weights despite changed inputs; begin a
  full learned planner before isolating this failure.
- **Observation/evidence:** Version 5 finished after 1,390,596 actions, 1,358 updates, 723 episodes,
  and three promotions. It entered the Mart at 619,660 and obtained the Parcel at 619,956. Mart-
  approach credit was 923.00 at the Parcel but 2,774.75 at shutdown, demonstrating that an expired
  lesson remained behaviorally relevant. Its model and worker-memory hashes matched. The Version-
  5.1 migration audit retained all 21 entries, canonical Parcel index 10, and three promotions.
  The public suite passed 160 tests; focused regressions prove lesson expiry and exactly zero net
  route credit for an advance/reversal pair. A four-worker real-ROM canary completed 8,192 actions
  and eight updates, recorded +24 net route credit and no expired Mart credit, and ended with
  matching model plus four worker hashes and no verification failure.
- **Interpretation:** Novelty is useful for discovery but cannot serve as the definition of progress
  in a game built around errands and revisits. The model's plateau is partly a task-definition
  failure: the trainer rewarded an obsolete destination more clearly than the current intent.
  A task-conditioned potential makes familiar travel meaningful without paying for oscillation.
- **Consequence:** Protocol identifiers become `parallel-recurrent-ppo-v5.1` and
  `active-goal-bidirectional-navigation-v1`. Later milestones shift by three after Parcel; imports
  fail if any imported ordinal changed. The dashboard adds net active-route credit. Version-5 PPO
  archives remain historical evidence and cannot resume as Version 5.1.
- **Narrative value:** The first fetch quest becomes the reward designer's test. “The AI refused to
  go backward” is replaced with the more honest reveal: “we had taught it that backward could not
  be progress.” The new experiment turns intent into a visible meter and makes success or failure
  on the road home legible.
- **Revisit when:** The return-trip canary fails engineering checks; the long run promotes Route 1,
  Pallet Town, Oak's Lab, or delivery; route credit oscillates without milestone progress; or a
  future one-way transition disproves the current bidirectional scaffold.
- **Supersedes / superseded by:** Extends DR-0048. It preserves Version 5's Mart/Parcel evidence but
  supersedes its always-live local lesson semantics.

## DR-0050 — Teach the first Gym as a chapter, not one distant outcome

- **Date:** 2026-07-20
- **Status:** Accepted and implemented; migration, private-ROM tests, and engineering canary passed;
  long-run behavioral evidence pending
- **Scope:** Parallel PPO Version 5.2 milestone catalogue, first-Gym trainer topology, recovery
  reward, dashboard, and documentation
- **Decision:** Close Version 5.1 after preserving its verified Pokédex lineage and post-Pokédex
  plateau. Add seven named milestones so every map-level transition from Oak's Lab through Pewter
  Gym is visible. Extend the assisted teacher graph only through the first Gym using source-verified
  map IDs. Add +2 navigation-recovery credit only when movement resumes after at least 12 stationary
  actions, disable it during battle, and cap it at three payments per episode. Import the verified
  V5.1 curriculum but start fresh PPO weights under new protocol identifiers.
- **Alternatives considered:** Run V5.1 longer unchanged; increase generic novelty; make Viridian
  Forest one larger reward; supply target coordinates; supply a scripted menu escape button; read a
  text-box RAM flag into the actor; copy a complete walkthrough graph for the whole game; resume
  V5.1 weights despite changing the catalogue and reward objective.
- **Observation/evidence:** V5.1 promoted Pallet Town, Oak's Lab, Parcel delivery, and the Pokédex
  by action 402,320. It then spent 3,035,252 further actions without reaching Forest, adding only
  305 global positions. Its completed denominator was 3,437,572 actions, 3,357 updates, 1,900
  episodes, 1,241 stagnations, 659 visual cycles, six promotions, and zero promotion failures. Its
  model and four novelty-memory hashes matched. V5.2 passed 174 tests with the private ROM. Its
  migration audit verified all 24 V5.1 entries, six promotions, the terminal model, and all four
  worker memories while preserving Pokédex index 15. A four-worker canary completed 8,192 actions,
  eight updates, all live frames, +24 bounded recovery credit, and matching terminal hashes with no
  promotion failure.
- **Interpretation:** V5.1 solved the reward contradiction it targeted, but a solved fetch quest did
  not create an implicit planner. The next objective combined too many map transitions and
  interaction modes for one sparse label to diagnose. Chapter decomposition should expose where
  composition fails while retaining strict replay admission.
- **Consequence:** The catalogue contains 66 outcomes. Protocol identifiers become
  `parallel-recurrent-ppo-v5.2` and `northbound-curriculum-navigation-recovery-v1`. The assisted
  actor may receive next-map context derived from a declared first-Gym topology. It still receives
  no tile, collision map, menu command, battle action, or scripted button. Dashboard and hourly
  narrative output report recovery credit separately. Later ordinals shift by seven after the
  Pokédex; all previously verified ordinals remain unchanged.
- **Narrative value:** The payoff and setback coexist: the agent learns to finish Oak's errand, then
  demonstrates that one taught errand is not the abstraction “quest.” A 3.0-million-action empty
  timeline gives way to a ten-step staircase toward Brock, with hints and verified proof displayed
  separately.
- **Revisit when:** The canary fails migration or checkpoint checks; recovery credit grows without
  exits; V5.2 promotes any northbound milestone; all workers plateau at one step; or the Boulder
  Badge is replay verified and the student-distillation gate becomes active.
- **Supersedes / superseded by:** Extends DR-0049. V5.1 remains the accepted backtracking result;
  V5.2 supersedes only its post-Pokédex task granularity.

## DR-0051 — Separate discovered lineage from one-policy competence

- **Date:** 2026-07-21
- **Status:** Accepted and implemented; private-ROM suite and corrected engineering canary passed;
  production behavioral qualification pending
- **Scope:** Version 6 PPO initialization, episode scheduling, competence gates, checkpoint
  integrity, dashboard, narrative, and claim language
- **Decision:** Retain one clean compatible predecessor PPO policy and optimizer rather than restart
  from the Frontier Apprentice seed. Split episodes into frontier discovery and backward
  consolidation. Count only earlier-start episodes toward a rolling gate. Hold the current verified
  frontier as the target and move the active start one available checkpoint backward after 8/10
  successes in production. Reset the active edge when a new promotion extends the target. Hash-bind
  consolidation state into every model checkpoint.
- **Alternatives considered:** Continue adding permanent micro-milestones; increase the V5.2 runtime;
  treat three deterministic lineage replays as proof that the neural policy learned the sequence;
  restart PPO again; sample the full archive uniformly; count target-start episodes as success;
  immediately add an untested recurrent imitation loss; or require power-on from the first V6
  episode and recreate the original sparse-horizon problem.
- **Observation/evidence:** V5.2 verified leaving Oak's Lab at action 52,728 and Route 1 at 707,472,
  then spent more than four million actions without Viridian progress. The code audit confirmed
  90-percent frontier resets, apprentice-seed PPO initialization for every new protocol, and
  promotion based on replayed stored actions. The V6 private-ROM suite passed 180 tests. The first
  canary exposed a retained-counter budget bug and stopped at 1,024 actions; the corrected canary
  completed 8,192 actions, eight updates, four frames, zero promotion failures, and matching model,
  novelty, and consolidation hashes. One of two earlier-start episodes reached the Pokédex while
  frontier starts were excluded.
- **Interpretation:** The archive has accumulated a valid solution lineage farther than any frozen
  policy has been required to act. Discovery and competence are complementary but non-equivalent.
  A backward-expanding gate preserves local tractability while making composition an explicit
  training obligation.
- **Consequence:** Protocol identifiers become `parallel-recurrent-ppo-v6` and
  `retained-policy-backward-consolidation-v1`. A V6 manifest records the retained source model and
  optimizer. Status and narrative distinguish frontier, consolidation start, target, rolling
  result, and gates passed. “Learned” is reserved for a declared competence gate; replay promotion
  alone is called “discovered” or “verified lineage.”
- **Narrative value:** The assembled lineage becomes a multicolored chain made by several policies.
  V6 replaces it with one continuing line and moves the start left only when one brain can connect
  the larger span. The project can show how far the archive knows and how far the current model can
  remember at the same time.
- **Revisit when:** The production 8/10 gate passes or plateaus; a new promotion changes the target;
  retained weights catastrophically forget earlier behavior; a frozen earlier-start evaluation
  disagrees with the training gate; or the verified-lineage imitation ablation is ready.
- **Supersedes / superseded by:** Extends DR-0050 without rejecting its chapter milestones. It
  supersedes fresh PPO initialization and frontier-dominant sampling as the default successor
  strategy.

## DR-0052 — Restart with self-generated skills instead of another authored lesson

- **Date:** 2026-07-21
- **Status:** Accepted; implementation, private-ROM suite, and first canary passed
- **Scope:** Primary completion learner after the V6 diagnostic
- **Information label:** `SELF-TAUGHT / PIXELS + SELF-DISCOVERED VISUAL GOAL`
- **Decision:** Begin V7 from random neural parameters and the unique clean power-on snapshot. Do
  not import a human playthrough, predecessor actions, predecessor weights, later curriculum
  entries, route graph, coordinates, or semantic target. Admit a skill only when the same run's
  transition passes exact replay; imitate its own verified actions and rehearse the weakest visual
  skill behind an 8/10 rolling gate.
- **Alternatives considered:** Continue patching V6 reward; record a full human Hall-of-Fame
  demonstration; import earlier verified lineages into behavior cloning; use a scripted planner;
  return to pure random or neuroevolution.
- **Observation/evidence:** V6 retained one policy, opened its first Route-1 composition gate at
  0/10, and closed at 5/10 after 1,001,476 actions—below the promised 8/10—with 11 successes across
  206 attempts and no passed gate. The first V7 real-ROM canary
  discarded 25 inherited entries, imported zero actions and parameters, then replay-verified game
  start and the ground floor within 8,192 actions. It created two hashed self-generated skills,
  performed eight direct imitation updates over 2,048 examples, and reproduced one skill once.
- **Interpretation:** The agent needs direct credit and reusable memory, but the solution need not
  come from a human. Separating exploration, replay, self-imitation, and rehearsal keeps assistance
  visible while restoring the original new-player premise.
- **Consequence:** Local obstacle-specific rewards are no longer the default response. A failure of
  skill competence or clean-start composition is an architectural result. Referee watchpoints may
  grade progress but cannot enter policy observation or reward in V7.
- **Narrative value:** The project admits that the host had slowly become the walkthrough, erases
  the inherited answer, and lets the agent keep only memories it earned itself. The first two tiny
  skills become the honest restart rather than another patched obstacle.
- **Revisit when:** A long V7 run shows whether imitation improves rolling competence, whether
  later skills erase earlier ones, and whether a frozen policy composes from power-on.
- **Supersedes / superseded by:** Supersedes V6 as the primary completion strategy while retaining
  V6 as the controlled composition diagnostic. Not yet superseded.

## DR-0053 — Separate the discoverer from a replay-distilled student

- **Date:** 2026-07-21
- **Status:** Accepted and implemented; first real-ROM mechanism, frozen-exam wiring, two clean
  resumes, bounded replay I/O, and a two-skill composition-verifier acceptance passed; deliberate
  hard-crash, production-window, learned multi-skill, and behavioral evidence pending
- **Scope:** Version 8 trajectory processing, policy authority, recurrent imitation, scheduling,
  exams, checkpoint integrity, dashboard, and claim language
- **Information label:** `SELF-TAUGHT / PIXELS + SELF-DISCOVERED TEMPORAL VISUAL GOAL`, with a
  privileged replay verifier and scheduler that never choose live buttons
- **Decision:** Keep V7's ban on demonstrations, imported actions, predecessor weights, route
  graphs, coordinates, and semantic actor goals. Leave its already-running trial unchanged as the
  denominator. Continue four-worker recurrent PPO as a dedicated Explorer, but create a second
  recurrent Student with a separate optimizer. Find the nearest verified self-generated lineage
  prefix, then mechanically propose loop and contiguous-chunk deletion. Admit an edit only when a
  fresh emulator replay from the same source preserves the protected outcome. Train the Student on
  balanced contiguous sequences with loss-free burn-in and short terminal visual clips. Let a
  prerequisite-aware scheduler allocate minimum evaluation, mastery, retention, or frontier
  episodes. Grant or revoke competence only from periodic frozen Student exams, not PPO reward or
  imitation loss. Collect exactly one deterministic grade from each Student checkpoint at a
  16,384-Explorer-action cadence; the 10-wide 8/10 window must span ten Student versions.
- **Alternatives considered:** Let V7 run longer without architectural change; increase V7's
  imitation epochs; lower policy entropy; train the shared Explorer on every raw verified action;
  copy PPO parameters into the Student after each rollout; use one still frame forever; label the
  target with a named milestone; provide a human-optimal action trace; use a scripted planner;
  resume V6's authored micro-curriculum; discard the live V7 trial; or call replay promotion itself
  competence.
- **Observation/evidence:** V6 showed partial local learning but failed its 8/10 composition gate.
  V7's first canary proved that a random policy can generate, verify, and imitate its own opening
  skills. That useful result also exposed the next causal ambiguity: one network receives both
  noisy PPO gradients and direct imitation gradients, while the verified trace can contain every
  accidental loop used before success. A successful replay protects outcome provenance but does
  not certify every recorded action as a good target. The active long V7 denominator has not been
  reconfigured or interpreted as a final result. The first V8 canary then stopped/resumed cleanly
  twice and ended `stop_requested` at 5,248 Explorer actions / 48.038 seconds. It verified one
  `game_started` skill, distilled 256 raw actions to 254 with final replay, trained the separate
  Student for eight updates over 128 examples, and preserved matching Student model, optimizer,
  and ledger hashes. Final NLL was 2.06915 and action accuracy 16.14%. The original runner repeated
  the same deterministic Student and produced 2/2 locally plus 14/14 from power-on, all only for
  `game_started`. The final audit supersedes those duplicates as robustness evidence; they remain
  mechanism history only.
  A later real-ROM integration found a P0 verifier defect: PyBoy's complete game-area hash changed
  across save/load even when the processed visual and every enumerated gameplay RAM field matched.
  Composition now uses that exact save/load-stable visual-plus-RAM signature, while distillation
  keeps the stricter hash because its candidates replay from one snapshot. The corrected verifier
  accepted a stored 230-plus-59-action chain from `power_on` through `game_started` to
  `left_bedroom`, accepted a four-noop save/load regression, and rejected validly encoded wrong
  endpoints. Those stored-action replays qualify mechanism only, not learned Student competence.
  The unchanged V7 snapshot at `2026-07-21T17:29:11Z` was 6,466,564 actions, Route 1, seven
  discoveries, zero competent skills, 19/1,274 rehearsals, and 66,560 imitation examples.
- **Interpretation:** The source of teaching data is no longer the main philosophical problem; all
  positive examples can remain self-generated. The next test is whether noisy discovery and stable
  retention require different parameter streams, and whether replay can convert a successful
  accident into a shorter causal lesson without a human editing the route. The canary confirms
  those parts execute and resume together; because `game_started` is trivial, accuracy is low, and
  no chance or raw-trace control ran, it does not show that Student updates caused success. Ten
  checkpoint-separated grades for 66 outcomes require at least 10,813,440 Explorer actions at the
  frozen cadence, before discovery or composition cost.
- **Consequence:** Protocol identity advances only for V8 runs. Reports must expose separate
  Explorer and Student hashes, optimizers, updates, entropy, and artifacts. Every distilled skill
  keeps raw/compressed counts, bidirectional provenance mappings, accepted and rejected edit
  counts, replay cost, and hashes. Scheduling decisions and competence losses persist. Dashboard
  depth splits into discovered, distilled-library, frozen-local, and restore-free composition.
  A real-ROM canary may qualify wiring but cannot establish learning; only frozen attempt
  denominators support competence language. V8's zero-weight reward path skips authored route
  guidance, active-goal lookup, and Mart calculations; stagnation may use general durable
  consequences but not route distance, milestone index, or the Viridian Mart script. V7 retains
  those historical termination signals for denominator compatibility and is not fully blind at
  that boundary. V8 launch requires a clean named commit including untracked files; checkpoints
  bind source, verified ROM, curriculum, Explorer, Student, Student optimizer, and ledger. V7
  omits V8-only serialized config fields and backfills a missing manifest ROM only on resume
  without changing recorded source. A fresh V8 run may lock a read-only V7 denominator by matching
  its checkpoint to the latest/previous model hash. Only path-free identity, Explorer actions,
  milestone, model/checkpoint hashes, state, and timestamps enter the V8 manifest; resume must reuse
  that seal and cannot re-lock the comparison.
  Hash-matching `previous` artifacts are atomically copied back to `latest` without consuming the
  fallback; a simulated second interrupted rotation is unit-checked, while a process-kill real-ROM
  crash twin remains pending.
  Once a competent chain contains two or more edges, continuous exact power-on replay must verify
  every protected endpoint before bounded goal-switch excerpts may train the Student. Only the
  current deepest verified composition is active; archived ledgers/audits remain hash-bound.
  One replay ticket per constituent skill, uniform per-action loss, deterministic boundary rotation
  through a checkpointed cursor, and admission-time immutable replay shards prevent handoffs from
  disappearing without loading every full skill. Each shard owns a disjoint contiguous range of at
  most 512 loss-bearing examples plus up to the configured burn-in predecessor context. A
  persistent per-skill cursor opens one shard per routine round and covers the full source across
  resume; the original NPZ remains provenance-only during routine training. Routine checkpoints
  may trust unchanged inactive composition seals only when the last atomic `checkpoint.json`
  already commits them; new or active compositions and all new skill shards are validated, and
  resume/full audit validates every artifact. After the final schema tweak, the focused
  replay/Student/PPO/dashboard suite passed 61 tests, and the final supported-ROM suite passed
  245/245 in 24.80 seconds. This is mechanism evidence, not multi-skill behavioral evidence.
  Restore-free composition remains goal-conditioned hierarchical control: one frozen Student
  chooses every button, while a trainer-side RAM referee switches an ordered playlist of the
  run's self-generated target clips at declared milestones. This provides no authored quest
  direction or controller actions, but any Hall-of-Fame claim must name the switching protocol
  rather than imply unaided pixel-only autonomy.
- **Failed/useful decisions preserved:** Pure Monkey established that luck without memory cannot
  accumulate. Neuroevolution established that inheritance can retain a narrow habit without
  extending it. Archive slicing established verifiable progress while hiding composition. V5's
  expired Mart reward showed that a locally sensible reward can become globally wrong. V6 made
  partial composition visible but still depended on authored lessons. V7 restored self-generated
  learning and remains the necessary shared-policy/raw-trace comparison. None is deleted or
  relabeled because V8 exists.
- **Narrative value:** Draw the successful V7 action trace as a tangle. Let replay, rather than the
  host, decide which knots can disappear. Then split one orange Explorer from one blue Student and
  stop the training chart at the exam door. The question becomes whether the Student can pass with
  its weights frozen, not whether another rising score can be narrated as understanding.
- **Revisit when:** Any V8 canary fails the information boundary or atomic resume; compression harms
  frozen success; action accuracy rises without exam progress; old competence is repeatedly lost;
  local exams pass while composition remains flat; V7 closes and permits a matched comparison; or
  a later obstacle still requires a bespoke human lesson.
- **Supersedes / superseded by:** Extends DR-0052's self-generated-data decision. It supersedes V7's
  shared Explorer/imitator as the proposed successor, but V7 remains the live denominator and
  cannot be retroactively changed. Not yet superseded.

## DR-0054 — Train on successful states created by the Student itself

- **Date:** 2026-07-21
- **Status:** Accepted; Version 9 implementation in progress. No V9 automated qualification,
  real-ROM canary, frozen-exam success, or live progress is claimed
- **Scope:** Consecutive edge construction, canonical Student warm start, reverse closed-loop
  practice, success-only aggregation, automatic PPO recovery design, information boundary, frozen
  evaluation, checkpointing, and narrative
- **Information label:** `SELF-TAUGHT / PIXELS + SELF-DISCOVERED TEMPORAL VISUAL GOAL`, with
  trainer-only self-generated practice restores, exact success verification, and scheduling; no
  trainer button authority
- **Decision:** Close V8 as a qualified mechanism with a negative behavioral result, then preserve
  it rather than silently increasing cloning updates. Normalize each self-generated verified
  lineage into exact consecutive source-to-next-target edges. Warm-start the one canonical
  recurrent Student with V8-style bounded sequence behavioral cloning. Then practice each edge in
  closed loop, beginning near its protected target and moving the start backward only after a
  declared success gate. Admit only exact replay-verified successful Student rollouts to the
  aggregated imitation set; retain every failure in the denominator without teaching its actions.
  Predeclare a bounded recurrent PPO recovery trigger for rungs that produce no success, using the
  same canonical Student and actor information boundary. Keep that PPO lane disabled and unclaimed
  during initial qualification until closed-loop plumbing and a matched BC-only ablation pass.
  Continue to grant competence only through strict frozen, checkpoint-separated local exams and
  restore-free composition exams.
- **Alternatives considered:** Run V8 longer unchanged; increase BC epochs or model size without a
  causal comparison; lower the 8/10 exam gate; count reverse-rung success as competence; aggregate
  failed Student trajectories; use recorded suffix actions after the Student deviates; import the
  reference repository's demonstrations; provide an oracle correction for off-trace states; train
  PPO immediately before the closed-loop data path is qualified; let a human decide when to rescue
  a rung; or restore a different disposable expert and copy its actions into the Student.
- **Observation/evidence:** The clean V8 canary at commit `4c3c1fc` ran 3,584 Explorer actions,
  reached `met_professor_oak`, admitted four replay-distilled skills, completed 51 Student rounds
  and 134 optimizer updates, and survived two resumes. Final action NLL was 2.07149 and accuracy
  13.7795%, near the 12.5% uniform eight-action reference. The Student passed 0/7 strict frozen
  exams; zero skills became competent and composition correctly remained ineligible. Bounded shard
  replay and provenance behaved as designed. The final V8 supported-ROM suite passed 245/245 in
  24.80 seconds. These are V8 facts and motivation for V9, not V9 evidence.
- **Interpretation:** V8 taught from successful recorded state distributions but evaluated on
  states produced by the Student's own actions. One wrong prediction could move the emulator to a
  screen absent from the lesson and cause later errors to compound. This exposure-bias hypothesis
  fits the gap between a valid lesson library and 0/7 frozen behavior, but it is not established as
  the sole cause. V9 tests it by collecting new labels only from closed-loop successes produced by
  the Student, while a BC-only matched lane separates self-correction from normalization and extra
  updates.
- **Consequence:** Protocol and artifact identity must distinguish V9 from V8. Reports must expose
  normalized source/target identities, reverse-rung start, all practice attempts and terminal
  reasons, replay-verified Student successes, aggregated examples by edge/rung, Student checkpoint,
  BC-only comparator, practice/verification/exam budgets, and PPO fallback state. Success-only
  refers only to supervised admission; failures remain public evidence, and a future PPO optimizer
  may use complete rollouts. Reverse snapshots are disclosed training assistance. The actor still
  sees only processed pixels, its own recent actions/recurrent state, and a self-generated visual
  goal clip. RAM, coordinates, milestone names, route graphs, edge offsets, and correct-next-action
  labels remain trainer-only or prohibited. The initial qualification must show PPO fallback as
  disabled; enabling it later requires a new predeclared configuration and matched report. The
  implementation-in-progress normalizer uses `self-generated-consecutive-skill-graph-v1`, exact
  replay-local first-hit offsets, stable-state plus private-snapshot hashes, and provenance-derived
  node IDs; it rejects missing intermediate hits, ordinal-only reuse, duplicate concrete states,
  non-monotonic offsets, and incomplete action coverage. The reverse core uses
  `v9-student-closed-loop-reverse-practice-v1`, rung horizons 8/16/32/64 through full edge, two
  consecutive non-overlapping 27/30 promotion windows, deterministic 25% retention, and at most 32
  deterministic-reservoir success records per rung under
  `v9-student-successful-rollout-v1`. Its only actor keys are `pixels`, `action_history`, and
  `target_pixels`; reset protocol `zero-recurrent-sentinel-history-duplicate-frame-v1` excludes
  skill/checkpoint/rung/horizon identities. Pending scheduling choice and attempt seed must survive
  resume exactly. These are implementation declarations, not passed V9 evidence. PPO recovery is
  not implemented in this scope.
- **Failed/useful decisions preserved:** V8 is not relabeled as a success or deleted. Its 0/7
  result is what revealed the difference between building lessons and acting from them. Stage 0's
  exact route memorization and the earlier reverse curriculum remain useful evidence that backward
  practice can make a fixed path tractable, while their supplied route and moving-policy gates
  prevent them from serving as V9 competence evidence. V7 remains the unchanged raw-trace/shared-
  policy denominator.
- **Narrative value:** Open with four perfect lesson cards and seven failed exam tiles. Draw the
  recorded trajectory as a narrow rail; one Student mistake falls off it into an unlabeled state.
  Snap overlapping traces into consecutive edges, move a visibly assisted practice start backward,
  and let only a green replay-verified Student success write the next lesson. Show the automatic PPO
  lever behind glass and leave it disabled. End at the same frozen exam door beside a matched
  BC-only Student.
- **Revisit when:** Consecutive normalization cannot preserve every protected edge; the closed-loop
  actor receives a recorded or trainer-selected action; successful attempts do not replay; reverse
  practice improves only near-target rungs; aggregation grows while frozen success remains flat;
  BC-only matches V9; competence is repeatedly forgotten; a PPO trigger leaks privileged actor
  input or becomes a hidden route reward; checkpoint/resume changes practice history; or later
  quests still require bespoke human corrections.
- **Supersedes / superseded by:** Extends DR-0053 rather than rewriting it. V8 remains the closed
  replay-distilled-BC result and engineering substrate; V9 supersedes behavioral cloning alone as
  the active Student-training hypothesis. Not yet superseded.

## DR-0055 — Close V8 on the longer 1/47 result and advance V9 to engineering-checked

- **Date:** 2026-07-21
- **Status:** Accepted; V8 closed, V9 real-ROM canary pending
- **Scope:** Final V8 evidence, preservation of the clean canary, V9 runner integration, practice
  verification, bounded replay, checkpoint recovery, evidence language, and video narrative
- **Decision:** Treat the stopped longer V8 run as the final V8 behavioral result without erasing
  the earlier clean qualification canary. Advance V9's consecutive graph, closed-loop practice,
  success-only replay, and recovery state from design/integration-in-progress to engineering-
  checked E2. Continue withholding any V9 learned-behavior claim until a V9 real-ROM canary and
  strict frozen evaluation run. Keep recurrent PPO recovery disabled and unimplemented.
- **Alternatives considered:** Continue calling the 3,584-action 0/7 canary V8's final result;
  replace the canary with the longer run and lose its clean-source/resume qualification context;
  treat one success among 47 exams as a competent skill; call 53.0817% imitation accuracy proof of
  learning; count the 283-check suite as a V9 behavioral canary; enable PPO recovery immediately;
  or omit the stopped run because it did not consume the eight-hour ceiling in its name.
- **Observation/evidence:** Run
  `parallel-ppo-v8-distilled-student-8h-20260721-seed20260793` began at
  `2026-07-21T18:52:49.997984Z` and ended `stop_requested` at
  `2026-07-21T20:27:21.139277Z`, after 5,668.623 seconds. It completed 784,386 Explorer actions at
  138.373 actions/second and 1,532 PPO updates. Seven verified promotions reached milestone index
  7, `reached_route_1`. Seven skills compressed 13,011 original actions to 8,582 through 238
  oracle calls and 373,639 replay actions. The Student completed 387 rounds, 2,513 optimizer
  updates, and 137,437 examples. Final action accuracy was 53.0817% and NLL was 1.295676. Frozen
  exams ended 1/47, with zero competent skills and zero composition attempts. The earlier clean
  canary remains separately recorded at 3,584 actions, four skills, 134 Student updates, 13.7795%
  accuracy, NLL 2.07149, and 0/7 frozen exams; its then-current suite passed 245/245 in 24.80
  seconds.
- **Interpretation:** More discovery, more Student updates, and far better teacher-forced action fit
  did not produce reliable checkpoint-separated execution. The isolated 1/47 success prevents the
  stronger statement that the Student could never reach a target, but it remains far below the
  declared 8/10 gate. This strengthens the motivation to test exposure bias while leaving capacity,
  optimization, visual ambiguity, and recurrent-state handling as live alternatives.
- **V9 implementation evidence:** The V9 runner now derives exact consecutive skills under
  `self-generated-consecutive-skill-graph-v1` and hash-binds each graph audit into skill and
  checkpoint validation. Closed-loop practice accepts success only when milestone depth and the
  sealed target signature both match; all attempts enter one of `exact_target`, `timeout`,
  `emulator_stopped`, or `milestone_wrong_state`. Replay-verified successes alone may enter a
  deterministic per-rung reservoir; immutable bounded shards rotate through Student replay.
  Practice checkpoint snapshots preserve the pending choice/seed, 27/30×2 windows, retention
  decisions, terminal denominator, reservoirs, and provenance, and roll live state back to the
  same recovered Student generation. The current engineering suite passes 271 non-integration plus
  12 integration checks, 283 total. This is not a real-ROM V9 canary.
- **Consequence:** Headlines, progress tables, and video material must show both V8 records: 0/7 is
  the clean canary, while 1/47 is the final longer-run result. Fit charts must be paired with frozen
  exam denominators. V9 may be called implemented and engineering-checked, but not behaviorally
  qualified, learned, or live. The next gate is a bounded V9 real-ROM mechanism canary, followed by
  the matched BC-only ablation and strict frozen exams.
- **Narrative value:** The strongest cut now has two reveals. First, four lessons and seven red exam
  tiles prove the measurement catches failure. Then the timeline accelerates to seven lessons,
  2,513 Student updates, and 53.08% fit—only to stop at one green tile among 47 and zero competent
  skills. The audience can see why “it fit the demonstrations” and “it can recover while playing”
  are different claims before V9's closed-loop practice appears.
- **Revisit when:** A V9 real-ROM canary fails the graph, exact-target, aggregation, terminal-count,
  shard-rotation, or rollback contract; the matched BC-only lane explains the same gains; a frozen
  skill crosses 8/10; PPO recovery becomes eligible under a new declaration; or a later V8 artifact
  audit changes one of the terminal counts above.
- **Supersedes / superseded by:** Extends DR-0054 without rewriting its then-current canary evidence
  or implementation status. DR-0054 remains the V9 design decision; this entry records the later V8
  run and engineering integration. Not yet superseded.

## DR-0056 — Qualify V9's campaign boundary before the long run

- **Date:** 2026-07-21
- **Status:** Accepted; mechanism qualification passed, learned competence not demonstrated
- **Scope:** Real-ROM canaries, synchronous cancellation, status/report merging, wall-time
  accounting, practice observability, frozen evidence, and authorization for a longer V9 campaign
- **Decision:** Preserve the first V9 canary as a failed pre-hardening diagnostic, repair the two
  engineering defects it exposed, and make the corrected second canary authoritative. Qualify V9
  only for mechanism, observability, and measured campaign wall-time. Proceed to a declared longer
  V9 run without lowering frozen competence rules or enabling recurrent PPO recovery.
- **Alternatives considered:** Ignore the overrun because useful practice occurred; report 248.801
  seconds as if it were the configured 180; delete the first canary; infer missing diagnostics from
  other files; blame manual STOP for the overwritten panel; accept practice success as competence;
  skip the corrected canary; or enable the future PPO fallback before the self-correcting lane has a
  longer result.
- **Pre-hardening evidence:** Run `parallel-ppo-v9-canary-20260721-seed20260801` was configured for
  180 seconds but synchronous work crossed the boundary. Manual STOP ended it at 248.801 seconds
  and 12,360 Explorer actions. It reached index 3, `left_home` / `Stepped outside`, with three
  promotions, zero promotion failures, and six skills. Practice ended 19/22 exact target with three
  timeouts; frozen exams ended 0/3. Each immediate success-only `record_student_training()` report
  replaced rather than merged the richer periodic Student report, leaving empty/zero dashboard
  diagnostics. STOP exposed that existing merge defect; shutdown did not create it.
- **Hardening:** Commit `e1ea199` (`Keep V9 work inside campaign boundaries`) added cancellation
  checks around synchronous campaign work and report merging that preserves richer periodic
  diagnostics when immediate success-only updates arrive.
- **Authoritative evidence:** Run `parallel-ppo-v9-canary2-20260721-seed20260802` started at
  `2026-07-21T21:31:41.473766Z` and wrote final status at
  `2026-07-21T21:34:08.155927Z`. Those timestamps span 146.682 seconds including roughly 2.6
  seconds of setup/finalization. The campaign clock measured 144.082 seconds against the declared
  144.0-second budget and ended automatically with `duration_limit`. It processed 12,520 Explorer
  actions at 86.895/s, made 12 PPO updates, reached index 2 (`Reached the ground floor`), produced
  two promotions with zero promotion failures, and held three skills. Run storage was 42,336,864
  bytes.
- **Student/practice evidence:** The Student completed 20 rounds, 64 optimizer updates, and 1,400
  examples; final action accuracy was 0.1415313 and NLL was 2.211105. Practice produced 16/22 exact
  targets (72.727%), two `milestone_wrong_state` outcomes, and four timeouts. Sixteen successes were
  retained and caused 32 success-only updates. The last bounded replay round exposed three
  aggregated practice datasets, 39 train examples, and 20,000 bytes. Frozen exams ended 0/3 with
  zero competent skills.
- **Engineering evidence:** The current suite passes 276 non-integration plus 12 integration checks,
  288 total. Together with the corrected real-ROM canary, this supports the narrow mechanism,
  observability, and campaign-clock claim. It does not support useful learning, reverse-rung
  completion, composition, later-game progress, or Hall-of-Fame behavior.
- **Consequence:** Reports must distinguish process timestamp span from measured campaign clock,
  show all terminal reasons, retain both canaries, and pair practice success with frozen exams.
  The longer V9 run may use the corrected boundary, but 0/3 remains its starting behavioral
  evidence. The BC-only ablation remains required before attributing later improvement to
  self-correction. PPO recovery remains disabled.
- **Narrative value:** Let the first canary visibly overrun its timer while its diagnostic panel
  goes blank, then stop the experiment rather than cutting around it. Explain that frequent small
  training reports were replacing the richer report. Apply the fix, rerun the same chapter, and
  show the timer stop within 0.082 seconds of its campaign budget while all 22 outcomes remain
  visible. End on 0/3: trustworthy failure is the qualification victory.
- **Revisit when:** The long V9 run closes; campaign clock exceeds its bound; report merging loses a
  richer field; practice denominators disagree with ledgers; a skill crosses the frozen gate; the
  matched BC-only ablation changes causal interpretation; or PPO recovery becomes eligible under a
  separate declaration.
- **Supersedes / superseded by:** Extends DR-0055 without rewriting its then-current canary-pending
  status. DR-0055 remains the V8 closure and V9 engineering-integration record; this entry records
  the later real-ROM qualification and hardening. Not yet superseded.

## DR-0057 — Freeze and close the long V9 campaign before interpreting it

- **Date:** 2026-07-21
- **Status:** Accepted and closed; terminal audit complete, zero competent skills
- **Scope:** Long-run identity, source boundary, action/time/storage budgets, parallelism, practice
  and exam cadence, operational handoff, first live checkpoint, and change control
- **Decision:** Launch one eight-hour fresh-start V9 campaign under the corrected qualification
  boundary, record its exact protocol before interpreting behavior, and permit no mid-run rule
  changes. Treat dashboard snapshots as E1 live telemetry only. Competence remains defined by the
  unchanged frozen gate, not practice success or a rising training metric.
- **Run identity:** `parallel-ppo-v9-self-correcting-8h-20260721-seed20260809`; source commit
  `d1c0c0d`; seed 20260809; start `2026-07-21T21:43:57.163627Z`.
- **Fresh-start boundary:** The campaign begins from power-on. Its V8 source contributes only the
  root curriculum state. V8 model/optimizer weights, controller actions, distilled skills,
  successful practice records, and learned policy state are excluded. This is an initialization
  dependency, not a transferred solution.
- **Frozen protocol:** Eight-hour campaign limit; 150,000,000-action safety ceiling; four emulator
  environments; 256-step rollouts; reverse-practice promotion at 27/30 exact successes in two
  consecutive non-overlapping windows; practice every four Explorer rollouts with two attempts;
  frozen exam every 16,384 Explorer actions; 100 GiB output cap; 50 GiB free-space floor; dashboard
  port 8774; PPO recovery disabled. The action ceiling is a guard, not a prediction that eight
  hours will approach 150 million actions.
- **Operational decision:** Reject the generic `nohup` handoff and launchd wrapper after both failed
  before run creation. Launchd's service context lacked external-SSD access. Use a detached user
  session that preserves the interactive user's filesystem permissions and adds sleep prevention.
  The failed launchers consumed no experiment actions and created no competing run. Do not publish
  private absolute storage paths.
- **First-boundary observation:** At the first scheduled exam boundary, status reported 161.420
  seconds, 16,388 Explorer actions at 101.524/s, 16 PPO updates, milestone index 2 (`Reached the
  ground floor`), two promotions, and three skills. The Student reported 13 rounds, 60 optimizer
  updates, 0.1396277 action accuracy, and 2.105477 NLL. Practice produced seven exact targets and
  one timeout across eight attempts, retained seven successes, and applied 14 success-only updates.
  The one frozen exam consumed 556 actions and failed 0/1; zero skills were competent and zero
  composition attempts ran.
- **Terminal evidence:** The user intentionally requested stop at
  `2026-07-22T00:36:38.849066Z` to begin the matched-configuration V10 successor. The run ended
  `stop_requested` after 10,359.143 seconds (2h52m39.143s), not the eight-hour ceiling encoded in
  its name. It completed 1,431,556 Explorer actions at 138.1925/s, 1,398 PPO updates, 558 episodes,
  716 unique positions, seven promotions through Route 1, and eight discovered skills. The Student
  completed 797 rounds, 10,692 updates, and 330,505 examples, ending at 68.5919% accuracy and
  0.904136 NLL. Practice reached 558/698 exact targets across 651,629 actions and 882 updates.
  Frozen exams ended 4/87, but no skill became competent and no composition ran. Episode endings
  included 139 visual cycles and 419 stagnations; 146 battle successes were recorded. Final hashes
  verified and the run occupied 57 MiB.
- **Interpretation:** This snapshot proves only that the declared live run exists and the qualified
  machinery continues to emit coherent fields. One failed exam cannot establish stagnation, and
  7/8 assisted practice cannot establish competence. No trend, causal improvement, later-game
  progress, or terminal V9 result was claimed from that early snapshot. The terminal result is now
  authoritative: much better Student fit and four isolated exam successes still yielded zero
  competent skills. V9 closes as a negative reliability/composition result, not as a failed
  engineering pipeline.
- **Alternatives considered:** Warm-start from V8's Student or seven skills; import V8 action
  sequences; shorten the 27/30×2 gate after seeing early results; increase practice frequency
  mid-run; treat the first practice percentage as success; restart after the first 0/1; enable PPO
  recovery; continue trying a service wrapper with different permissions after the campaign had
  already started; or report a live dashboard value as final evidence.
- **Consequence:** Every update must carry the observation timestamp/action count and provisional
  label while live. The complete final report now supersedes those provisional snapshots. The
  desired loop-recovery rule change becomes the separately identified V10 run rather than a V9
  edit. Preserve all frozen attempts, terminal reasons, practice cost, storage, hashes, and source
  boundary.
- **Narrative value:** Show the launch card before the dashboard: commit, seed, fresh-start boundary,
  eight-hour clock, action/storage guards, and exam cadence. Briefly show two launchers fail without
  creating the experiment, then the detached user session succeeds. At 16,388 actions, place 7/8
  assisted practice beside 0/1 frozen evaluation and leave the story unresolved. The discipline is
  refusing to turn an early number into an ending.
- **Revisit when:** A terminal artifact is found inconsistent, the matched V10 comparison closes,
  or the 4/87 frozen-exam interpretation changes under a predeclared aggregate analysis.
- **Supersedes / superseded by:** Extends DR-0056's authorization into an exact active-run contract.
  It does not rewrite the two V9 canaries or V8 history. Not yet superseded.

## DR-0058 — Let the Explorer recover before resetting

- **Date:** 2026-07-21
- **Status:** Completed and superseded as the primary architecture; deterministic E2 qualification,
  direct E3 calibration, and one bounded real-ROM E3 campaign canary passed; the
  matched-configuration run closed with zero competent skills
- **Scope:** Version-10 Explorer loop handling, actor authority, generic recovery feedback,
  telemetry, qualification, and successor narrative
- **Information label:** Explorer receives processed pixels, recent executed actions, and recurrent
  state. The separate Student retains its self-generated visual goal clip. Trainer-only code may
  detect generic ineffective directional action/pixel outcomes only from processed pixels and the policy-submitted action, but
  supplies no direction, route, coordinate, map, action mask, or controller action.
- **Decision:** Add a distinct `self_taught_v10` protocol that preserves V9's fresh power-on,
  separate Explorer/Student, consecutive-skill, success-only practice, and frozen-exam boundaries.
  When repeated generic directional failure activates recovery, defer immediate loop termination
  for a bounded window. Let the PPO policy continue choosing every action, penalize declared
  repeated ineffective attempts, and retain the classified reset if recovery expires. After
  `blocked_repeat`, credit only a policy-chosen directional material visual outcome as `escaped`;
  close a non-directional material change as zero-credit `context_changed`, not an escape or
  success. After `visual_cycle` or pixels-only `progress_stagnation`, a generic material action may
  be credited because the trigger already incurs the -2 loop penalty. Open pixels-only long
  stagnation at 1,024 ineffective outcomes before the legacy hard watchdog can terminate, while
  visually effective backtracking resets that hard timer without clearing the separate
  128-frame/eight-signature cycle detector.
- **Alternatives considered:** Leave V9 unchanged and spend a larger action budget; increase only
  the existing repeated-action penalty; reset immediately on every loop; force a random alternate
  direction; mask the last failed direction; reveal collision or coordinates to the actor; add
  route distance or a Viridian-specific reward; or manually rescue the current run.
- **Observation/evidence:** The declared V9 campaign remains frozen under DR-0057. During live E1
  observation its screens visibly repeated ineffective directional actions with little pixel change while generic
  loop/stagnation detections caused episode restarts from the run's current self-generated verified
  frontier. This is a diagnostic observation, not a terminal V9 result or proof that recovery will
  improve learning. The focused V10/PPO/dashboard suite passed 67 checks; the whole default suite
  passed 293 with 13 private-ROM checks skipped; and all selected ROM-bearing files passed 54/54
  with the private ROM in 19.02 seconds. Ruff, the private-artifact guard, documentation
  links/placeholders, compilation, and diff checks passed. These results qualify deterministic engineering behavior,
  not exploration or competence. Deterministic environment/reporting checks also prove that
  pixels-only stagnation activation suppresses simultaneous legacy termination, exact expiry is
  terminal, the action ceiling stays truncated and abandons an active window, perceptual activity
  leaves short-cycle detection live, active ranks become abandoned on resume, and hourly Markdown
  reports the full denominator. A direct private-ROM integration at the committed 289-action
  ground-floor fixture plus six settling noops then classified Up (0% changed / 0 MAE) and Right
  (0.642% / 0.509) as blocked, Down (20.972% / 23.165) and Left (21.215% / 26.851) as material directional visual outcomes, and
  Start (37.708% / 89.667) as material context change. Up×3 → Start closed as zero-credit
  `context_changed`; a fresh Up×3 → Down closed as credited `escaped`. Both retained
  `submitted == executed`. This is E3 mechanism calibration, not a campaign canary; no V10 campaign
  result existed at that checkpoint.
- **Campaign-canary evidence:** On 2026-07-22 UTC (2026-07-21 local), a one-environment real-ROM
  canary ran from clean commit `a0ec14a5506fe3a0c4bcb15787f68be4d512d764` with seed 20260810.
  It stopped cleanly at `duration_limit` after 144.102 seconds, 6,099 actions at 42.324
  actions/second, and 47 PPO updates. It made two verified promotions, reached the ground floor,
  observed 93 unique map positions, verified its checkpoint hashes, and occupied 40 MiB. All 73
  windows were `blocked_repeat`: 36 credited `escaped`, 32 zero-credit `context_changed`, and five
  expired across 702 recovery actions, yielding 36/73 = 49.315% credited escapes. The five
  expirations matched five `visual_recovery_expired` episodes. Active, abandoned, unresolved, and
  trainer-selected-action counts ended at zero. Visual-cycle and long-stagnation recovery were not
  activated.
- **Matched-configuration launch:** After the user intentionally closed V9, run
  `parallel-ppo-v10-recovery-8h-20260721-seed20260809` started at
  `2026-07-22T00:37:44.442964Z` from clean source commit
  `513afc378d091d18560efb4af4931d882c05000d`. It uses seed 20260809, the same V8 root curriculum
  source, four environments, an eight-hour/150-million-action ceiling, and the same Explorer PPO,
  Student, reverse-practice, exam, and storage configuration as V9. Dashboard port is 8774.
  Recovery is fixed at 32 actions after three blocked outcomes; ineffective means changed pixels
  below 2% **and** MAE below 2, while material escape means changed pixels at least 5% **or** MAE
  at least 5. Repeated-block penalty, credited escape, and expiry penalty are 0.25, 0.25, and 1.0.
- **Live heartbeat only:** At about `2026-07-22T00:42:55Z`, status was running at 310.686 seconds,
  22,532 actions (72.523/s), 22 PPO updates, 30 episodes, five promotions through `chose_starter`,
  286 positions, five skills, and zero competent skills. `checkpoint.json` recorded 20,480 actions,
  beyond the declared 16,384 exam boundary; frozen exams were 0/1. All 366 windows were
  `blocked_repeat`: 165 escaped, 169 context-changed, 30 expired, and two active. Completed windows
  were 364; abandoned, unresolved, and trainer-selected-action counts were zero across 3,475
  recovery actions. Explorer and Student hashes independently matched and dashboard HTTP was 200.
  This proves only that the active run is coherent; it is not an interim result or trend.
- **Matched-configuration terminal evidence:** The user intentionally ended V10 to begin the V11
  architectural pivot. SIGINT closed the run cleanly at 4,503.282 seconds, 534,924 Explorer
  actions, 522 PPO updates, 122 episodes, and seven promotions through Route 1. Frozen exams ended
  3/32 with zero competent skills and no composition. The Student ended at 43.2519% action
  accuracy across 121,194 examples. The recovery ledger closed 1,977 starts as 956 escapes, 910
  context changes, 110 expirations, and one campaign-end abandonment, with zero unresolved windows
  and zero actor-action overrides. DR-0059 records the resulting architecture decision.
- **Comparison boundary:** V9 and V10 share seed, declared runtime/action ceiling, parallelism,
  curriculum source, and PPO/Student practice configuration. Their source commits and wall-clock
  start times differ, so this is a matched-configuration successor rather than a bit-identical
  causal ablation. Report that imperfection with the final denominator.
- **Interpretation:** Immediate reset protects compute but may remove the local off-distribution
  state in which PPO could compare repeated failure with a self-chosen escape. A bounded recovery
  window can test that hypothesis without telling the actor which way to move. Fewer resets alone
  would be an operational difference, not meaningful exploration or competence. The clean canary
  qualifies this bounded mechanism and earns a matched longer V9/V10 comparison; its two promotions,
  93 positions, and 49.315% credited escape rate are not superiority evidence without that match.
- **Reward-audit correction:** Reduced the draft escape credit from 1.0 to 0.25 raw units and
  constrained it not to exceed the 0.25 repeated-block activation penalty. A credited directional
  blocked/escape pair is recovery-reward-neutral before ordinary game consequences. A
  non-directional `context_changed` closure earns zero and retains the -0.25; it cannot manufacture
  escape credit merely by opening a menu.
- **Consequence:** Public status and the dashboard must distinguish loop detections, recovery
  trigger types, activations, credited escapes, zero-credit context changes, expirations, active
  windows, abandonment on resume/episode/campaign end, recovery actions, ineffective-direction
  counts, unresolved inactive windows, and trainer-selected actions. The last two counts must remain
  zero. Active ranks persist so a resume classifies rather than loses them. Old “loops cut short”
  language cannot describe every V10 trigger, and `context_changed` cannot be described as an
  escape/success. Qualification must prove action authority and absence of authored guidance before
  a long run. Later comparisons must report compute, unique positions/maps, verified milestones,
  and frozen exams rather than presenting escape rate as game progress.
- **Narrative value:** Show the wall bounce, loop detection, and reset repeatedly erasing the local
  mistake. Then preserve that same scene inside a bounded recovery timer while every policy action
  remains visible. The chapter question is: “If every mistake ends the lesson, when does it
  practice the recovery?” Keep `TRAINER-SELECTED BUTTONS: 0` on screen; distinguish a green credited
  directional escape from a blue zero-credit context change; and show every expiry, active window,
  and abandonment.
- **Revisit when:** False positives appear in menus, dialogue, or battle; the policy farms recovery
  feedback; recovery consumes a material action fraction; the visual-cycle or long-stagnation paths
  receive campaign evidence; a matched V9/V10 comparison closes; or V10 changes verified discovery
  or frozen Student competence.
- **Supersedes / superseded by:** Extends the architecture after DR-0057 without altering that
  frozen V9 campaign or its eventual result. It superseded immediate termination only for V10 and
  is superseded as the primary completion architecture by DR-0059.

## DR-0059 — Pivot from a flat button learner to a disclosed hierarchical completion agent

- **Date:** 2026-07-21
- **Status:** Accepted; V10 closed, V11 implementation and clean-start canary in progress
- **Scope:** Whole-game completion architecture, V10 closure, external harness provenance,
  information disclosure, clean-start safety, terminal truth, dashboard, and future distillation
- **Information label:** `STRUCTURED-STATE LLM PLANNER + A* NAVIGATOR + CONTROLLER SPECIALISTS /
  ASSISTED MAP + OBJECTIVE + RUN MEMORY`; `POWER-ON`; `HYBRID-SYSTEM`
- **Decision:** End the matched V10 campaign without deleting or relabeling it. Replace the primary
  completion lane with one hierarchical, memory-bearing agent that receives the current
  hand-authored full-game objective, processed maps, structured state, and deterministic same-map
  navigation while executing interactions, menus, battles, puzzles, recovery, and transitions
  through ordinary controller inputs. Pin and adapt `sethkarten/continual-harness` commit
  `bbab97ad73e460b7cd7c08527d10ced30cc03fbe`; run the authenticated Codex CLI locally because the
  Mac has no active Docker daemon or separate model API key. Store runtime data on the external
  SSD. Preserve a separate strict-blind control and use a successful guided journey as future
  behavior-cloning/DAgger data rather than pretending it is a newly trained pixels-only model.
- **V10 terminal evidence:** A SIGINT closed
  `parallel-ppo-v10-recovery-8h-20260721-seed20260809` cleanly after 4,503.282 seconds
  (1h15m03.282s), 534,924 Explorer actions at 118.785/s, 522 PPO updates, 122 episodes, 567 unique
  positions, and seven promotions through Route 1. The Student completed 270 rounds and 3,366
  optimizer updates over 121,194 examples, ending at 43.2519% action accuracy and 1.556849 NLL.
  Frozen exams were 3/32 with zero competent skills and no composition. Of 1,977 recovery windows,
  956 escaped, 910 changed context, 110 expired, and one was abandoned at campaign end; zero actor
  actions were overridden. The final run occupied 51,716,995 bytes and retained matching Explorer
  and Student hashes.
- **Observation:** V8–V10 increasingly improved lesson production, imitation fit, closed-loop
  practice, and local recovery, but none produced one competent skill under the frozen gate. V9
  reached 68.5919% training fit yet only 4/87 frozen success; V10 again stopped at Route 1 with
  3/32. Four parallel V10 environments visibly converged on the same local corner despite separate
  emulator state. Reward and loop changes altered local behavior without supplying a mechanism for
  multi-hour planning, symbolic quest memory, map-scale travel, or specialist control.
- **Safety findings before launch:** The pinned upstream Red wrapper automatically loaded any state
  beside its ROM, and its `CHAMPION` milestone fired on entering the Champion's room. V11 disables
  adjacent-state auto-load by default and requires event bit `0x901` together with map `0x76` (Hall
  of Fame). Its objective sequence gains a final post-battle Hall-of-Fame step, and Red recording
  uses 160×144 rather than the upstream 240×160 GBA writer size. A claimed run imports no upstream
  save, memory, skills, subagents, or evolved Lt. Surge policy.
- **Alternatives considered:** Run V10 longer; increase reward magnitudes or recovery windows;
  expose coordinates to the same flat PPO policy; train another monolithic recurrent model; replay
  a human or reference-repository speedrun; use a fully scripted route; require the external CLI to
  solve navigation from raw buttons as an upstream benchmark; buy API access before testing; or
  call entry into the Champion's room completion.
- **Interpretation:** The recurring failure is architectural, not evidence that another local
  reward coefficient will solve the game. Pokémon Red naturally decomposes into a planner,
  navigation, interactions, battles, puzzles, memory, and a verifier. Giving those roles explicit
  interfaces makes the assistance larger but also makes causal failures understandable. A
  successful V11 result would be **disclosed hierarchical AI completion**, not pixels-only
  self-taught learning and not the existing H5 fixed-policy claim.
- **Consequence:** V11's dashboard and report must separate game state, plan/reasoning, journey
  milestones, and reliability evidence. The supervisor records timestamps, status snapshots,
  milestone/objective changes, important frames, hourly Markdown chapters, source/ROM hashes,
  interventions, and disk limits. No long run begins until a bounded canary proves true power-on,
  local Codex authentication, objective visibility, expert MCP tools, refreshing visuals, strict
  completion monitoring, and clean shutdown. After the first verified completion, distill its
  success and failure states into learned specialists and freeze replacements one component at a
  time.
- **Narrative value:** Open on four V10 screens trapped in the same corner. Instead of adding a
  fifth reward, zoom out and draw the missing hierarchy. The story becomes “we stopped teaching the
  AI one button at a time,” while the adjacent-state and early-Champion bugs provide a concrete
  reminder that a green dashboard is not the same as beating the game.
- **Revisit when:** The V11 canary fails a safety gate; the planner cannot change strategy after a
  stall; direct objectives advance without evidence; the first uninterrupted run reaches a major
  chapter or strict Hall of Fame; or distilled specialists become eligible for a frozen
  power-on evaluation.
- **Supersedes / superseded by:** Supersedes DR-0058 only as the primary completion architecture.
  DR-0058's mechanism and V10 terminal evidence remain valid historical results. Not yet
  superseded.

## DR-0060 — Make state truth server-enforced, not planner-declared

- **Date:** 2026-07-21 local / 2026-07-22 UTC
- **Status:** Accepted and implemented; Canary 4 opening referee qualified, continuous V11 run
  active, Hall of Fame unverified
- **Scope:** V11 semantic-state arbitration, cache isolation, public state and map endpoints,
  planner tools, formatting, opening-objective authority, dashboard truth, and canary evidence
- **Information label:** `STRUCTURED-STATE LLM PLANNER + A* NAVIGATOR + CONTROLLER SPECIALISTS /
  ASSISTED MAP + OBJECTIVE + RUN MEMORY`; `POWER-ON`; `HYBRID-SYSTEM`
- **Decision:** Treat structured state as a server-enforced contract, not a collection of raw bytes
  or a proposition the planner may validate for itself. Deep-copy every cached emulator state
  before a server endpoint or direct tool enriches it. Gate player/world values, map caches,
  `/state`, `/whole_map`, MCP state/map reads, and navigation on the documented game-start bit.
  Make the formatter independently suppress map context while `game_started` is false. Keep the
  first objective locked until an ordinary directional input produces an actual coordinate change
  in the ready upstairs bedroom. Persist that proof only for the current gameplay session and
  invalidate it after a return to pregame.
- **Alternatives considered:** Ask the planner prompt to reconcile the screenshot and RAM; trust
  every nonzero or plausible WRAM field as present-tense state; use a permissive border-byte scan
  as dialogue detection; accept the planner's objective-completion request as evidence; guard only
  the public planner text while leaving dashboard, map, navigation, or cache paths populated; or
  treat `wJoyIgnore == 0` as a universal player-control signal.
- **Observation/evidence:** Canary 3 was the first end-to-end planner/control run, but it exposed a
  semantic instrumentation failure. While Oak's introduction was visible, staged RAM claimed
  `RedsHouse2f (3,6)`, `$3000`, and `overworld`; A* received a bedroom map and the unguarded
  objective endpoint completed `pallet_000`. The operator stopped the run after 251.630 seconds
  and 50 actions and rejected the apparent progress. The source audit found that the old text and
  title addresses were unrelated audio/map buffers and that `0x7f`, previously counted as a box
  border, is the ordinary space tile.
- **Primary-source basis:** The exact supported-ROM audit is anchored to the generated
  [`WRAM layout`](https://github.com/pret/pokered/blob/405b6246372d7e5a2cb029cbb65219b13286b8c9/ram/wram.asm#L154-L184),
  [`ROM hashes`](https://github.com/pret/pokered/blob/405b6246372d7e5a2cb029cbb65219b13286b8c9/roms.sha1),
  [`MESSAGE_BOX` coordinates](https://github.com/pret/pokered/blob/405b6246372d7e5a2cb029cbb65219b13286b8c9/data/text_boxes.asm#L8-L15),
  [`0x79`–`0x7f` character tiles](https://github.com/pret/pokered/blob/405b6246372d7e5a2cb029cbb65219b13286b8c9/constants/charmap.asm#L57-L63),
  the point where
  [`BIT_GAME_TIMER_COUNTING` is set after Oak's speech](https://github.com/pret/pokered/blob/405b6246372d7e5a2cb029cbb65219b13286b8c9/engine/menus/main_menu.asm#L321-L340),
  [`wJoyIgnore` masking semantics](https://github.com/pret/pokered/blob/405b6246372d7e5a2cb029cbb65219b13286b8c9/engine/joypad.asm#L22-L40),
  the broader
  [`game-controlled-movement predicate`](https://github.com/pret/pokered/blob/405b6246372d7e5a2cb029cbb65219b13286b8c9/home/npc_movement.asm#L1-L12),
  and the
  [`RedsHouse2F` no-op script transition](https://github.com/pret/pokered/blob/405b6246372d7e5a2cb029cbb65219b13286b8c9/scripts/RedsHouse2F.asm#L1-L22).
- **Qualification evidence:** Canary 4 retained pre-control suppression and required a movement
  receipt. RIGHT moved RED from `(3,6)` to `(4,6)` at `2026-07-22T03:22:41Z`; only then could
  `pallet_000` complete, at 450.05 seconds / 111 actions. The bounded run ended at 600.521
  supervisor seconds with 136 actions in `RedsHouse2f (0,2)`, story index 1/84, no party, no badges,
  and no Hall-of-Fame result. Its final audit found one residual server-layer pre-game map leak;
  applying the same deep-copy, started-bit, endpoint/tool, and formatter gates closed that path
  before the fresh continuous run.
- **Interpretation:** Memory correctness and semantic currency are different properties. Pokémon
  Red can stage the next world in RAM while a player is still inside an introduction or menu, so
  neither the planner nor a visually plausible dashboard may declare that world current. Static
  bytes establish a candidate phase; structural UI evidence establishes interaction context; an
  observed controller consequence establishes control. Independent layers are necessary because
  any one cache, endpoint, formatter, or objective path can otherwise reintroduce a convincing
  future state.
- **Consequence:** The fresh run `v11-continuous-20260721-233300` is active from power-on under the
  repaired boundary. Its launch and opening qualification are not evidence that V11 can solve
  later objectives or complete the game. Only the strict Champion-rival event together with the
  Hall-of-Fame map can support completion; that condition remains unverified. Regression checks
  must inject hostile pregame states, stale bedroom maps, false `overworld` labels, and reset
  transitions across every public and tool-facing path.
- **Revisit when:** Any endpoint exposes a map or gameplay identity before the start gate; a menu,
  dialogue, battle, reset, or load-state transition violates the phase invariant; the opening proof
  survives a return to pregame; the continuous run encounters a later semantic-state conflict; or
  the strict Hall-of-Fame verifier fires.
- **Supersedes / superseded by:** Refines DR-0059's clean-start and referee requirements without
  changing V11's disclosed assistance label. It supersedes planner self-attestation and permissive
  raw-state exposure as acceptable evidence. Not yet superseded.

## DR-0061 — Close online assisted play as the final premise

- **Date:** 2026-07-22
- **Status:** Completed; V11 retained as a closed assisted control
- **Scope:** V11 continuous run, project premise, information labeling, compute use, and narrative
- **Information label:** `STRUCTURED-STATE LLM PLANNER + A* NAVIGATOR + CONTROLLER SPECIALISTS /
  ONLINE ASSISTED CONTROL`
- **Decision:** Stop `v11-continuous-20260721-233300` and preserve every recorded call and action.
  Do not use an online language model to choose routine gameplay decisions in the final experiment.
- **Observation/evidence:** The clean-start attempt ran for 950.308 seconds, issued 329 controller
  actions and 144 live model calls, and ended without party or badge progress. The more important
  mismatch was conceptual: even a future V11 success would establish an assisted planner's ability
  to use tools, not a local model learning Pokémon Red through experience.
- **Alternatives considered:** Continue V11 without a time limit; call the hierarchy the final AI;
  reduce model-call frequency; use the assisted trajectory as a demonstration; or present V11 and
  a local learner as equivalent completion attempts.
- **Interpretation:** V11 remains valuable as an auditable upper-bound control and as evidence that
  semantic state must be server-enforced. It does not answer the chosen self-learning premise.
- **Consequence:** The final learner must make zero online model/API decisions, import zero V11
  actions or state, and begin with random weights from direct verified power-on.
- **Supersedes / superseded by:** Supersedes DR-0059 only as the primary completion strategy.
  DR-0059 and DR-0060 remain valid records of the assisted system and its safeguards. Superseded as
  final architecture by DR-0062.

## DR-0062 — Freeze V12 as a fixed self-generated hindsight experiment

- **Date:** 2026-07-22
- **Status:** Completed with a negative final result; see DR-0065
- **Scope:** Final learner architecture, information contract, self-generated training, exams,
  terminal evaluation, hardware budget, launch gates, and publication rule
- **Information label:** `PIXELS + RECENT ACTIONS + SELF-GENERATED VISUAL GOAL / RANDOM WEIGHTS /
  POWER-ON / ZERO ONLINE DECISION CALLS`
- **Decision:** Use one recurrent visual actor across four clean emulator workers. Continue PPO on
  game-general consequences, but turn visually meaningful 8–128-action excerpts from the actor's
  own rollouts into bounded future-frame goals. Train the demonstrated actions under their actual
  goal and impose a 0.25-weight, 0.10-margin contrast against a blank goal. Preserve V10's generic
  pixels-only recovery, replay-verify rare milestone discoveries, and grade retained behavior only
  in checkpoint-separated deterministic no-update exams. Freeze a 48-hour run, 150-million-action
  safety ceiling, 8/10 competence rule, and final power-on evaluation before launch.
- **Forbidden inputs:** Online LLM/API decisions, internet gameplay help, walkthroughs, OCR,
  authored routes/coordinates/quest objectives, human or scripted demonstrations, V11 traces,
  predecessor actions/weights/skills/save states, actor-visible RAM/maps, and trainer-selected or
  replaced buttons.
- **Qualification evidence:** C1 processed 20,000 actions in 126.161 seconds, trained 624/624
  hindsight lessons, and replay-verified three discoveries through `left_home`, but passed only
  1/9 exams. C2 showed the loophole: correct-goal advantage was `-0.00018086` despite 176 trained
  lessons. The matched-seed/action-budget C3 added the frozen contrast term, trained 176 lessons
  over 4,968 examples, sustained 133.055 actions/s, and moved the diagnostic to `+0.00353084`.
  Zero skills became competent. Terminal evaluation remained at power-on.
- **Alternatives considered:** Another sparse milestone reward; larger authored curriculum;
  Explorer/Student handoff; model-based world learning too large for the current 8 GB host; offline
  demonstrations; V11-generated teaching data; a success-conditioned replay buffer without a
  goal-use diagnostic; or another open-ended run whose rules change after every stall.
- **Interpretation:** Future-state hindsight makes training opportunities much denser without
  importing answers. Correct-goal contrast closes the most immediate shortcut, but the small
  positive canary value is directional mechanism evidence only. It does not establish competence,
  composition, whole-game scalability, or a causal performance gain.
- **Consequence:** Launch only from committed source, exact ROM, free dashboard port, mounted T7
  with at least 150 GiB free, and the checked fixed configuration. Do not tune mid-run. Publish the
  terminal result, deepest verified milestone, goal-use diagnostic, exam denominator, composition
  depth, and all failure conditions whether the run succeeds or fails.
- **Revisit when:** The fixed 48-hour result has closed. Any successor is a new declared experiment,
  not a repair applied inside V12.
- **Supersedes / superseded by:** Supersedes DR-0061 as the final experiment architecture. It does
  not invalidate any earlier denominator or assisted-control result. Not yet superseded.

## DR-0063 — Make the final run a non-restarting macOS-managed process

- **Date:** 2026-07-22
- **Status:** Accepted and implemented after a zero-action launch failure
- **Scope:** V12 process lifetime, sleep prevention, start receipts, crash semantics, and exact-run
  identity; no learning rule or budget changed
- **Decision:** Register the source-frozen V12 command as a run-specific macOS launch job wrapping
  `caffeinate -imsu`. Set `KeepAlive=false`, write separate stdout/stderr paths plus label/PID
  receipts, and preserve the exact bootout command. Do not rely on an orphaned desktop shell child.
- **Observation/evidence:** After the T7 mounted with 220 GiB free, every declared launch gate
  passed. The first launcher printed PID 20184, then its detached child was reaped when the command
  session ended. Five seconds later there was no process, listener, run directory, or log content.
  It therefore consumed zero training actions and is an orchestration failure, not a V12 result.
- **Alternatives considered:** Pretend PID creation meant the run was active; launch directly in a
  task-bound terminal; use `launchctl submit` with inferred keepalive behavior; manually restart
  after every Codex session; or weaken the clean-source gate to patch while training.
- **Interpretation:** A 48-hour experiment needs an operating-system owner independent of the
  terminal that initiated it. Automatic restart would also corrupt the fixed-attempt denominator,
  so persistence and restart behavior must be separate choices.
- **Consequence:** A clean finish or crash remains terminal and visible. The launch job may outlive
  Codex, while the display may turn off and the Mac and external disk stay awake. Learning code,
  seed, information boundary, reward, budgets, exams, and terminal evaluation remain DR-0062's
  frozen values.
- **Supersedes / superseded by:** Refines only DR-0062's process-launch mechanism. It does not alter
  the experiment's model or claim boundary. Not yet superseded.

## DR-0064 — Let Terminal own the non-restarting final process

- **Date:** 2026-07-22
- **Status:** Accepted and implemented after launchd privacy rejection
- **Scope:** V12 process ownership and macOS privacy only; no learning rule, information boundary,
  seed, budget, or evaluation changed
- **Decision:** Execute the frozen `caffeinate` command as a dedicated foreground process in the
  user's Terminal. Keep that window open for the attempt. Continue writing PID/mode receipts and
  separate stdout/stderr logs on the T7. Do not automatically restart after exit.
- **Observation/evidence:** DR-0063's generated property list was syntactically valid, but
  `launchctl bootstrap` returned input/output error before execution. A minimal diagnostic job
  bootstrapped from `/tmp`, then failed to touch the T7 with `Operation not permitted`; a job whose
  standard output pointed to the T7 exited `EX_CONFIG`. macOS privacy therefore prevented a
  LaunchAgent from accessing both required private locations. It consumed zero V12 actions.
- **Alternatives considered:** Grant a background agent Full Disk Access; move the private ROM or
  run output solely to internal storage; keep the experiment tied to a Codex execution session; or
  enable automatic restart. All either widen permissions, violate storage planning, or weaken run
  identity unnecessarily.
- **Interpretation:** Terminal already has the user's intended file access and can outlive Codex
  without weakening macOS privacy. Foreground ownership is visible: closing the window terminates
  the attempt instead of concealing a daemon.
- **Consequence:** The display may turn off while `caffeinate -imsu` keeps the Mac and disk awake.
  Codex may inspect the dashboard and artifacts but does not own routine gameplay or process
  lifetime. A Terminal close, crash, reboot, duration limit, action ceiling, disk guard, or strict
  completion remains a terminal event and cannot silently create another run.
- **Supersedes / superseded by:** Supersedes DR-0063 only for process ownership. DR-0063's
  zero-action failure and no-auto-restart requirement remain part of the record. Closed by DR-0065.

## DR-0065 — Close V12 and the project on the measured negative result

- **Date:** 2026-07-22
- **Status:** Accepted and final
- **Scope:** V12 interpretation, terminal evidence, public reporting, and project continuation
- **Decision:** End the plateaued V12 attempt at the user's request, publish its last
  integrity-bound checkpoint and last observed status separately, make no Hall-of-Fame or stable-
  competence claim, and close the project rather than begin another post-hoc repair iteration.
- **Observation/evidence:** Run `v12-final-48h-20260722-005136-seed20260722`, clean source commit
  `804ffe810fce5002afb03406f65dfac2ca5be214`, observed 35,696.136 seconds and 8,236,144 training
  actions. It made 4,021 PPO updates, replay-verified seven promotions through Route 1, observed
  694 unique positions, and generated/trained 64,336 hindsight lessons over 3,518,624 action
  examples. Frozen evaluation ended at 55/502, zero competent skills, no composition attempt, and
  no Hall-of-Fame completion. The first skill passed 55/160, lost competence twice, and ended 1/10;
  the ground-floor skill passed 0/342. The correct-goal advantage ended effectively zero.
- **Terminal limitation:** The user-requested interrupt reached the persistent terminal wrapper as
  a broken pipe before the normal finalizer wrote `terminal-evaluation.json` or changed the stale
  `running` status. The last sealed checkpoint is 8,224,768 actions / 35,634.036 seconds. Its model,
  curriculum, and self-skill hashes still match. Its V12 hindsight-state hash does not match the
  current file, so an exact resume correctly failed closed. The remaining 11,376 observed actions
  are reported but not represented as a sealed checkpoint. No substitute terminal result is
  invented.
- **Alternatives considered:** Continue toward the 48-hour ceiling despite a nine-hour plateau;
  bypass checkpoint validation to force finalization; reconstruct or edit private state until the
  resume passed; run a post-hoc evaluator under changed source and present it as the declared
  terminal exam; or begin V13 immediately. Each would either spend compute without addressing the
  observed forgetting, weaken integrity, or turn a fixed experiment back into an open-ended repair
  loop.
- **Interpretation:** Parameter updates and transient behavior occurred, but stable cumulative
  learning did not. V12 discovered trajectories much faster than it retained them. Millions of
  dense hindsight examples did not prevent goal neglect or catastrophic forgetting, and the
  competence gate correctly prevented seven archive milestones from being called one learned
  journey.
- **Consequence:** The public repository receives a redistribution-safe result record, final
  retrospective, milestone and exam tables, and explicit shutdown limitation. The video plan is
  retained as historical planning material but shelved. Any future attempt must be a separate,
  newly declared project with a materially different representation, anti-forgetting, temporal-
  abstraction, or compute strategy.
- **Revisit when:** Never within this project's V12 protocol. A successor may cite this denominator
  but must not rewrite it.
- **Supersedes / superseded by:** Closes DR-0062's final experiment and DR-0064's process-lifetime
  plan. No project decision supersedes this entry.

## Archived unresolved questions

These questions remain useful for a future, separately declared successor. They are not active
commitments in this closed project.

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
