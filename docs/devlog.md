# Development log

## 2026-07-20 — Parallel PPO turns failures into training data

- Reviewed Peter Whidden's Pokémon Red PPO project and video as an influence, then documented the
  parts adopted and the evidence rules deliberately retained here.
- Added one shared recurrent-PPO learner over several PyBoy environments, with pixels-only and
  separately labeled 24-value privileged actor modes.
- Reused the Visual/Frontier Apprentice convolution, actor LSTM, and action-head weights; the PPO
  value head starts new, and privileged-only LSTM columns start at zero.
- Froze 18 replay-verified curriculum starts from one atomic Archive-v2 checkpoint instead of
  reading a changing live store or choosing an undocumented save state.
- Kept named progress stricter than reward: a candidate needs an exact parent-edge replay and three
  exact complete power-on replays before admission.
- Added atomic latest/previous model archives, hash-bound checkpoint validation, stop requests,
  bounded storage checks, hourly Markdown chapters, TensorBoard metrics, and a multi-frame live
  dashboard.
- Preserved the honest resume boundary: model and optimizer state resume exactly, while partial
  emulator rollouts restart.
- Ran pixels-only canaries at 1, 2, 4, and 6 environments plus a privileged-input canary. All
  completed real PPO updates. Four workers produced the best measured collection rate on the 8 GB
  M1: 419.34 actions/s, versus 178.06 with two and 351.39 with six.
- Ran the production-shaped four-worker canary with 256-step rollouts, batch size 256, four epochs,
  and 4,096-action episodes. It completed 2,048 actions, two updates, all four live frames, and a
  hash-matched final checkpoint at 218.65 actions/s.
- Retained the still-running Frontier Apprentice as the baseline until the PPO replacement passed
  this gate. The benchmark and canaries are mechanism evidence, not later-game progress.

## 2026-07-20 — From a frozen handoff to a full-game learning ratchet

- At the 6-hour-41-minute interruption observation, the apprentice-guided expedition had reached
  the Pokédex after roughly 68 minutes, taken 3.24 million actions, retained 2,336 active archive
  cells, and passed 12,442/12,442 replay checks. It had not promoted Viridian Forest during the
  following five-plus hours. The app update interruption was resumed from the exact checkpoint.
- Measured the plateau rather than guessing: 22,888 of 24,918 completed suffixes ended in visual
  loops; post-Pokédex attempts averaged about 130 actions; and only about 7% of post-Pokédex starts
  came from Route 2 while larger earlier maps absorbed much more scheduler attention.
- Implemented the Frontier Apprentice foundation for the complete milestone catalogue: generic
  non-repeatable trainer rewards, map-balanced frontier selection, adaptive exploration up to
  100% during stagnation, bounded exploratory loop escapes, and pixel/action self-imitation only
  after edge and power-on promotion replays pass.
- Added atomic latest/previous learner files whose hashes, update counts, reward memory, and tensor
  identities enter the runner checkpoint. A restart cannot silently load parameters from the wrong
  side of a crash boundary.
- Kept recurrent PPO as a controlled next ablation. Version 1 first tests the simpler causal claim
  that a verified success can become a retained local policy skill without teaching from failures.
- Passed the first real-ROM mechanism canary: 11,495 actions, five verified promotions through
  choosing a starter, 763 successful actions learned, 38 optimizer updates, and 49/49 replay
  checks. Stopped at action 8,467 and resumed with the exact learner file/tensor hashes, reward
  memory, archive, and counters before advancing another 3,028 actions. This verifies the learning
  and restart plumbing, not Viridian-Forest performance or game completion.
- Preserved the less successful second seed too: it learned three promotions but ended its
  12,000-action budget at `left_home` with 52/52 replay checks. A non-terminal twin on the final
  build stopped at action 8,045, resumed with unchanged model and parameter hashes plus the same
  19 updates, then reached action 11,858 with 55/55 replay checks. The canaries establish mechanism
  reliability and seed variance; neither is a Forest qualification.
- Gracefully concluded the frozen eight-hour handoff when the Frontier Apprentice was ready. It
  retained 3,535,933 actions, 13,136/13,136 passing replay checks, and `obtained_pokedex` as its
  best milestone after 26,930 seconds. Since the Pokédex had arrived near minute 68, the final
  record contains more than six hours without a Viridian-Forest promotion rather than silently
  allowing the obsolete actor to compete for compute.
- Launched the first fresh eight-hour Frontier Apprentice campaign from power-on at commit
  `6c49cc4`, seed `20260751`, with an 8,192-cell archive, 150-million-action safety ceiling, and
  50-GiB free-space floor. In its first 13 seconds it reached `left_home`, learned three verified
  promotions from 616 successful actions in 42 optimizer updates, and passed 14/14 replay checks.
  This is a launch health observation; the Forest gate and later game remain open outcomes.

## 2026-07-20 — Leaving home becomes the beginning

- Completed the full reverse-curriculum development gate in 233.9 seconds rather than eight hours:
  480 adaptive attempts, 451 successful exits, 451 self-imitation updates, and two final 29/30
  windows from the complete 419-action horizon. The run stopped normally at
  `curriculum_complete`; its vanished live server was restored as a read-only dashboard.
- Identified the scope error plainly: `left_home` was still a terminal condition even though the
  project goal is the Hall of Fame. Preserved the result rather than stretching a completed local
  curriculum into eight hours of redundant episodes.
- Added a hybrid full-game expedition emitter. It loads the completed private apprentice model by
  file and tensor hash, keeps the weights frozen, resets recurrent memory at every archive restore,
  and mixes seeded random actions with pixel-policy argmax decisions. The trainer raises that
  exploration rate from 2% to 35% only after the verified house-exit frontier.
- Retained Archive v2's complete Hall-of-Fame milestone catalogue, semantic referee, bounded
  primary niches, local edge proofs, three fresh power-on promotion replays, crash-tail recovery,
  disk limits, and continuously refreshed gameplay dashboard. The frozen network does not receive
  RAM, milestone identity, coordinates, snapshots, or route position.
- Classified this as a hybrid development campaign: the model supplies a learned opening prior,
  seeded exploration proposes unfamiliar actions, and the archive/scheduler accumulate progress.
  Neural weights do not update on unseen-game failures in this run.

### Real-ROM handoff and overnight launch

- Ran a 2,279-action real-ROM handoff canary. It promoted `game_started`, `left_bedroom`, and
  `left_home`, retained 24 active frontier cells, and continued acting after the house exit. At the
  live acceptance observation, all 23 attempted replays had passed; the canary was then stopped
  intentionally rather than mistaken for the overnight experiment.
- Rejected the first overnight launch after 11,767 actions. Its provisional 32-action minimum
  produced 184 short restore cycles and reached the ground floor, but not the house exit. Because
  the frozen LSTM starts with zero recurrent state after every restore, this was evidence that the
  scheduler could fragment the learned opening more aggressively than the successful canary.
- Restarted the eight-hour clock from a fresh power-on and seed with a 512-action minimum and
  2,048-action maximum. That run passed `left_home`, followed Professor Oak into the lab, and kept
  running toward `chose_starter`; the first live observation recorded 3,135 actions, 25 archive
  cells, and 41/41 replay checks. These are development observations, not evidence that the frozen
  policy can already complete the game.

## 2026-07-19 — From one lucky route toward a learned visual skill

### Restore the publication baseline

- Diagnosed two red GitHub checks as duplicate push/PR executions of one pytest collection error,
  not two independent experiment failures. The safety guard, documentation check, and Ruff had
  already passed.
- Declared the repository root in pytest's import path so the artifact-guard regression can import
  the standalone check script under the same command contributors and CI use.
- Re-ran 92 non-integration tests locally and required both GitHub jobs to pass before adding
  scaling changes.

### Remove bookkeeping that grows with the archive

- Rebuilt successful replay counts once from the validated event hash chain and update the index
  only after an audit append reaches durable storage. Replay-count lookup is now constant-time.
- Stream action lineages segment by segment instead of joining every ancestral action into one
  large tuple. Replaced repeated ancestry walks with one iterative topological validation pass.
- Replaced recursive run-directory scans on every controller action with incremental file
  accounting, periodic exact reconciliation, and timed free-space checks. Disk limit observations
  latch rather than disappearing after a later estimate.
- Ran the complete private-ROM suite: 109 tests passed. The 1,300-cell successful Q1 store opened
  in about 1.38 seconds, and all 1,528 successful replay counts were queried in about 0.00013
  seconds. These are development-machine measurements, not portable performance promises.

### Freeze the next learning design before training

- Selected Archive v2 for bounded qualification: one primary semantic/spatial niche with a few
  visual alternatives, at most one ordinary candidate per suffix, exact parent-to-child edge
  verification for training eligibility, and three complete power-on replays for named promotion
  claims.
- Wrote [Visual Apprentice v1](visual-apprentice.md): a small recurrent pixel policy warm-started
  from self-generated action lineages, then trained on recovery states in a backward checkpoint
  curriculum. The first 419-action route is enough for an intentional overfit smoke, not a
  generalization claim.
- Declared the first frozen local-skill gate as at least 45/50 branch-grouped held-out successes,
  followed later by at least 18/20 snapshot-free power-on attempts. No model result exists yet.

### Implement Archive v2 without rewriting Q1

- Stamped fresh stores and runner checkpoints as v2 while retaining schema-v1 Q1 stores as
  readable historical evidence. Legacy stores preserve their original full-replay reporting rule,
  but cannot enter a mutable v2 archive or mint a local edge certificate.
- Required successful promotion evidence to bind the complete replay envelope: planned and
  executed action counts, snapshot and screen hashes, descriptor, milestone identity, and the
  deterministic referee-summary projection. A passing milestone label alone no longer increments
  the promotion ledger.
- Bound each semantic/spatial primary niche to one representative plus three visual alternatives.
  Each suffix may persist at most one ordinary candidate, and a side-effect-free preflight rejects
  certainly uncompetitive candidates before their snapshots or segments are written.
- Bound ordinary verification to the exact parent-to-child segment. Cumulative edge-replay actions
  cannot exceed cumulative exploration actions by construction; named promotions still require
  three complete fresh power-on replays.
- Bound resume to the exact store event sequence and hash-chain head, moved the single-writer lease
  ahead of every resume mutation, made long promotion replays cancellable for explicit or disk
  safety stops, and made the finished dashboard's disk measurement exact.
- Bound every runner checkpoint to the store event byte offset, ordered cell IDs, and an immutable
  embedded RGB frame; the separately mutable dashboard image can no longer invalidate resume. A
  post-checkpoint crash tail is copied into a content-addressed private recovery bundle before
  rollback, including orphan cell metadata and incomplete final event bytes. A durable
  checkpoint-hash-bound transaction marker makes rollback repeatable after another power loss.
  Simulated interruptions after cell metadata, event append, index update, event-log rollback, and
  index rollback all resumed exactly. Behind, tampered, corrupt-frame, and invalid checkpoint or
  pending-recovery states refused without mutating the store, trace, or stop marker.
- Reopened both Q1 stores under the read-only compatibility path with zero historical deficits and
  verified that neither can enter a v2 archive. The complete private-ROM suite passed 121 tests.
  These checks authorize staged qualification, not a multi-day run or a learning claim.

### Pass the staged Archive v2 qualification

- Published the complete Archive v2 implementation at Git commit `e4e50b1` and required both
  GitHub Actions jobs to pass before opening any real-ROM result.
- Completed a 4,096-action continuous seed with 453 edge-replay actions, 831 named-promotion
  replay actions, 18 stored cells, 14 active cells, four primary niches, and `game_started` as the
  best named milestone.
- Preserved a failed stop-timing attempt: the 2,048-action run finished before the separate stop
  command arrived, so it was not counted as resume evidence. Repeated with a 4,096-action ceiling,
  stopped at action 1,023, resumed identically, and finished at the exact action limit.
- Deliberately killed the continuous seed's twin with one `frontier_selected` event beyond its
  stable checkpoint. Resume preserved all 396 tail bytes in one hashed private recovery bundle,
  completed at 4,096 actions, and matched the uninterrupted trial's complete non-time counters,
  RNG, archive, parent attempts, milestones, ordered cell IDs, and checkpoint-frame hash.
- Reopened all three stores and checked replay certificates, suffix admission bounds, archive
  grouping, event/checkpoint identity, exact final disk bytes, and public-file privacy. The full
  gate passed. Published the complete denominator and visual summary in
  [Archive v2 qualification](../experiments/archive-v2-qualification/README.md).
- Authorized Archive v2 for the next bounded Visual Apprentice pipeline. Did not relabel the
  random emitter as learned or authorize an unbounded multi-day random search.

### Implement the first end-to-end learning smoke

- Selected the one actual Q1 `left_home` promotion rather than any of its 161 descendants that
  inherited the same milestone. Bound extraction to its explicit cell ID, 419-action lineage hash,
  three historical power-on certificates, and zero verification deficits.
- Added a read-only extractor that captures 420 processed decision-boundary frames without
  auditing or repairing the historical store. Dataset arrays, action alignment, source prefix,
  terminal snapshot/screen/descriptor, and manifest receive independent integrity checks.
- Froze a 468,312-parameter two-frame CNN-LSTM with previous action and recurrent state as its only
  non-pixel inputs. Chose direct PyTorch 2.13 on CPU for Stage 0; deferred sb3-contrib and recurrent
  PPO until recovery learning actually needs them.
- Added a bounded full-sequence cloning run, teacher-forced and predicted-feedback 419/419 gates,
  container-independent parameter hash, safe frozen reload, live status page, and model metadata.
- Added one clean-power-on evaluator with zero restored recurrent state, snapshots, reward,
  updates, retries, or interventions. Its RAM reader is referee-only and can stop the attempt at
  exact `left_home`; no semantic value enters the actor.
- Extended publication safety to reject dataset and model payload extensions. The Stage-0 data,
  model, sealing, live-rollout, and composite suite passes 15 automated checks; the real-ROM result
  remains pending and no trained-policy
  claim has been made.

### Pass Stage 0 on the real ROM

- Captured the certified route twice through independent emulator instances. Both results contained
  419 labels and 420 decision-boundary frames and produced logical dataset SHA-256
  `a8b03101d6f145e9d19831bc7d75caae90ca9f41b0c6518adf52e89eaa730aec`.
- Trained the 468,312-parameter CPU model for 316 epochs and 99.112 seconds. Teacher-forced and
  predicted-feedback evaluation both reached 419/419, and the frozen reload was identical.
- Ran the one planned clean-power-on attempt. With zero recurrent state and no snapshots, rewards,
  updates, retries, or interventions, the model reached `left_home` after 419 actions. Its complete
  selected sequence exactly matched its one training route.
- Sealed data, training, evaluation, and composite bundles; published their reviewed aggregate and
  full denominator in [Visual Apprentice Stage 0](../experiments/visual-apprentice-stage0/README.md).
  Recorded the result as a connected learning pipeline, not H2, recovery, or generalization.

### Build the first interactive recovery learner

- Rejected an eight-hour repeat of the already saturated one-route overfit and deferred recurrent
  PPO from power-on. Chose a smaller reverse-curriculum self-imitation pilot so the next run asks a
  new question: can the model succeed when it begins partway through the route with zero memory?
- Added seven backward starts at 8, 16, 32, 64, 128, 256, and 419 actions remaining. Each start
  duplicates its first visible frame, sets previous action to the sentinel, and resets the LSTM;
  checkpoint identity and route position remain trainer-only.
- Separated demonstration priming from learner-generated updates. Every failed attempt is logged
  and receives no gradient. Only an actual `left_home` rollout can enter the self-imitation half of
  an update.
- Froze promotion at 27/30 successes in two consecutive non-overlapping windows. Added atomic model,
  optimizer, random-stream, counter, and gate checkpoints; hash-checked resume; status and event
  ledgers; a local dashboard; and STOP, time, action, stagnation, process-memory, and free-disk
  boundaries.
- Capped the first development run at eight hours, 15 million emulator actions, two million actions
  without a rung promotion, 1.5 GiB process memory, and a 50 GiB free-space floor. The three-minute
  canary uses a visibly relaxed 2/3 gate once and cannot become qualification evidence.
- Recorded one prelaunch audit limitation: a hard-crash resume restores the last hash-checked
  learner state but does not yet reconcile append-only rows written after that checkpoint. Such a
  run may contain duplicate diagnostic episode/update IDs and cannot become formal evidence. The
  process therefore runs under macOS sleep prevention, and later qualification must add the same
  explicit crash-tail reconciliation already proved for Archive v2.

## 2026-07-19 — Q1 steps outside once, but fails its two-seed gate

### Complete denominator

- Ran both predeclared seeds sequentially against the real ROM with identical one-hour,
  20,000-exploration-action, 2 GiB, suffix, selection, and replay limits. Both stopped normally at
  exactly 20,000 actions with zero human interventions.
- Seed `20260730` reached `game_started` at exploration action 6,407 and `left_bedroom` at 8,766,
  then exhausted its budget without stepping outside.
- Seed `20260731` reached `game_started` at 6,231, `left_bedroom` at 7,941, and `left_home` at
  17,832. Its shortest accepted house-exit lineage contained 419 actions and replayed from power-on
  three of three times with matching hashes and canonical semantics.
- Reported the target as 1/2. Accepted the H3 claim that the expedition reached a verified named
  milestone, but failed Q1's requirement that both fresh seeds reach it.

### Cost and new failure vocabulary

- Spent 954,704 replay actions to verify 40,000 exploration actions—23.87 replay actions per new
  exploration action. All 2,984 replay attempts passed.
- Stored 2,502 evidence cells and admitted 2,317, leaving 2,284 active frontier cells. Archive
  breadth grew faster than useful new frontiers could be revisited, exposing selection starvation
  alongside the already known full-lineage replay cost.
- Preserved seed one's miss instead of extending it or reporting only the successful seed. The
  random emitter remains a baseline; it did not learn from either result.
- Found a narrative-recording limitation: the exact verified `left_home` image was a transition
  frame, while a later frame clearly showed Red outside. Future runners must keep both the exact
  causal frame and a separately labeled stable narrative frame.

### Decision

- Do not increase the random emitter's budget and do not begin a multi-day run.
- First stream/index replay work, bound local verification, repair frontier starvation, and compare
  optimized action-sequence and learned visual emitters under the unchanged Q1 protocol.
- Published the full result, integrity anchors, failed seed, and interpretation in
  [`experiments/q1-left-home`](../experiments/q1-left-home/README.md).

## 2026-07-19 — Hall-of-Fame completion foundation passes Q0

### The goal and the evidence ladder

- Made the long-term target explicit: first discover a complete, power-on-replayable lineage through
  the Hall of Fame; then use that record as curriculum for a single frozen policy. Only the latter
  supports the claim that one learned model knows enough to complete the game.
- Defined seven claim levels, H0 through H6, so a reliable emulator, an archived discovery, an exact
  lineage replay, and one-policy completion cannot be described with the same word.
- Replaced loose progress counts with 55 ordered named outcomes. The catalogue includes mandatory
  keys and HMs as well as story events, and Hall of Fame requires the Champion event and Hall-of-Fame
  map at the same time.

### Failed designs found before they became results

- Rejected the first hash-only replay verifier after an adversarial real-ROM audit reproduced the
  correct snapshot and screen hashes for a cell falsely labeled Hall of Fame. The independently
  recomputed state was still `power_on`. Exact replay is now necessary but never sufficient for a
  semantic claim.
- Bound every descriptor, quality field, lineage boundary, and referee summary into content identity
  after the same audit showed that edited metadata could survive under an unchanged cell ID.
- Prevented “replay laundering,” where a replayed child could promote through an ancestor that had
  never passed its own gate. Every non-root ancestor must now satisfy its own required replay count.
- Fixed resume accounting so evicted archive members no longer consume the selection allowance of
  their replacements, and so active-cell counts reconstruct exactly after restart.
- Changed audit recovery after a torn final write: preserve the damaged bytes privately, resume from
  the valid prefix, and append a recovery event. A complete corrupt record still fails closed.
- Fixed the runner ledger after a first resume implementation replaced the prior `stop_requested`
  ending. The trace now retains `stop_requested`, appends `run_resumed`, and later records the true
  terminal reason.
- Strengthened the publication guard so a private artifact cannot bypass review merely by being
  force-added beneath an ignored run directory.

### What Q0 proved—and did not prove

- Implemented a single-writer checkpoint expedition with private content-addressed snapshots,
  exact action segments, complete ancestry, quarantine, replay promotion, reproducible random state,
  bounded disk/time/action limits, clean stop/resume, and a localhost-only dashboard that cannot
  serve frontier payloads.
- Qualified the runner against the real ROM. A 512-exploration-action run created 42 active cells;
  all 42 exact replays passed and consumed another 4,392 actions. Its latest image reached Oak's
  introduction, while the semantic referee correctly remained at `power_on`.
- Repeated the check with a deliberate stop at 384 actions and an exact resume to 512. Archive,
  counters, selection state, random state, and the intervention ledger remained intact.
- Labeled the current branch generator truthfully as
  `RANDOM-ACTION-EMITTER / PRIVILEGED-TRAINING-REFEREE`. The archive can learn where to spend search
  effort; the button emitter receives neither pixels nor RAM and does not learn.

### Frozen next gate and deliberate blocker

- Froze Q1 before running it: the exact target is `left_home`; two fresh seeds receive at most
  20,000 exploration actions, one hour, and 2 GiB each. A milestone advance requires three complete
  power-on replays. Failure changes the emitter comparison rather than silently enlarging the budget.
- Refused to launch the requested multi-day campaign yet. A 1,024-action qualification spent 9,280
  additional actions on replay—about 9.1 replay actions per exploration action—and remained at
  `power_on`. Full lineage materialization, repeated ledger scans, ancestry validation, verification
  backlog, and rejected-payload retention must be bounded before marathon scale.
- Recorded the SSD's available capacity separately from computational readiness: free space is not
  evidence that replay growth is safe.

## 2026-07-19 — Six-lane lab concludes without a winner

- Completed all six selection × mutation treatments at exactly 128 children and 1,536,000 actions
  per lane, or 9,216,000 actions total.
- Frontier selection retained game start in 300 of 384 children (78.1%), versus 152 of 384 (39.6%)
  under uniform selection. This supports the narrow claim that selection changed inheritance.
- Every lane nevertheless remained at tier 1, one map, zero warps, zero party members, and zero
  badges. Frontier–Broad's seven positions did not pass the predeclared second-map gate and was not
  relabeled as a winner.
- Found a deeper failure signal: the median longest repeated-action streak in every treatment was
  roughly 11,800 of 12,000 actions. The deterministic argmax policy had mostly become a
  constant-action controller.
- Concluded that improved parent choice and gentler mutation preserve existing behavior without
  solving behavior composition or the clean-start horizon. Preserved the matrix as negative
  evidence and moved the primary completion track to verified checkpoint search.

## 2026-07-19 — Six-lane mechanism lab qualifies

- Implemented the generic N-lane orchestrator and the paired 2 × 3 preset: uniform/frontier parent
  selection crossed with broad/gentle/multiscale mutation.
- Imported the sealed 33-elite predecessor archive without carrying over emulator state, recurrent
  memory, the interrupted child, or any private filesystem path.
- Ran all six treatments concurrently against the real ROM for one exact 12,000-action child each;
  all six wrote genealogy, checkpoint, status, and dashboard artifacts and returned successfully.
- Interrupted a separate archive-seeded lane after 2,040 actions, resumed it against the same
  predecessor hash, and verified that it crossed the 12,000-action child boundary with one intact
  genealogy record before a second graceful stop.
- Repeated recovery at the orchestrator level: stopped all six lanes mid-child, relaunched against
  the identical manifest, and required all six to finish at exactly 12,000 actions before setting
  `comparison_complete`.
- Confirmed the paired first births chose matching parents within each selection row. Broad changed
  1,311 of 13,096 parameters while gentle changed 272, verifying the intended intervention.
- Added a responsive combined dashboard, safe local-only serving boundary, synchronized JSONL
  comparisons, and an append-only Markdown chronicle for later charts and video scripting.
- Added ten-minute synchronized six-frame sets, dashboard hashes, and exact first-milestone images;
  the accelerated recovery rehearsal preserved 19 complete frame sets and three game-start frames.
- Held the full lab to 128 children and 1,536,000 actions per lane, with wall time serving only as a
  safety ceiling. This qualification is engineering evidence, not a result for the six hypotheses.

## 2026-07-19 — First inheritance found; six-lane branch begins

### The 90-minute pretrial concluded

- Stopped the four-lane successor run deliberately after roughly 90 minutes and preserved every
  final checkpoint. All four runners returned cleanly with zero supervisor restarts.
- Evolutionary Explorer completed 2,838,873 actions and 236 fixed-policy evaluations. The nominal
  generation counter reached 14; the final archive contained 33 elites, 38 insertions, milestone
  tier 1, one map, four positions, and 71 evaluations that reached the game-start state.
- Visually Curious completed 2,557,662 actions, Outcome-Rewarded 2,262,634, and Conventional
  2,223,674. All three observed six maps and reached maximum party levels 27–29, but plateaued in
  the Pallet Town/Route 1 region.
- Classified these as development observations, not official success rates or a common-agent
  leaderboard. Different reward and information channels make raw score and level comparisons
  misleading.

### The evidence changed the mechanism

- Found that children of game-starting parents repeated the behavior about 79% of the time in this
  run, versus about 4.7% for children of non-starting parents. This is evidence that a narrow useful
  accident became inheritable, not that one policy learned during its lifetime.
- Found that archive-wide uniform selection still chose non-starting parents for roughly 64% of
  child evaluations.
- Found that broad mutation often erased fragile behavior: one of 23 observed children of the best
  four-position parent retained all four positions.
- Froze the 33-elite archive and its provenance rather than continuing a mechanism whose two main
  bottlenecks were already visible.

### The 2 × 3 decision

- Chose a six-lane factorial engineering fork: uniform versus 80/20 frontier selection crossed with
  broad-control, gentle, and multiscale mutation.
- Fixed each lane to 128 children × 12,000 actions = 1,536,000 actions, all starting Pokémon from
  power-on and all importing the same neural archive.
- Defined frontier selection as 80% from the highest milestone tier through a three-candidate
  lexicographic tournament and 20% from the whole archive for diversity.
- Defined gentle mutation as `p=0.02`, sigma `0.01`; defined multiscale mutation as 80% micro
  (`p=0.01`, sigma `0.02`), 15% broad (`p=0.10`, sigma `0.05`), and 5% macro (`p=0.10`, sigma
  `0.20`). The broad lane preserves the existing mutation mechanism as a control.
- Labeled the design an inherited-archive engineering fork. The selected mechanism must later
  restart from unrelated random founders across multiple seeds before any general learning claim.
- Made the 2 × 3 dashboard the central narrative visual: equal action fuel, visible family trees,
  parent tiers, mutation channels, retention, improvements, failures, and infrastructure health.

## 2026-07-19 — Evolutionary Explorer implemented; pretrial begins

### Mechanism built

- Implemented a deterministic 13,096-parameter recurrent neural policy that receives only the
  frozen coarse pixel grid and its previous action.
- Implemented clean-start 12,000-action child evaluations, a 16-genome founding population,
  mutation-only descendants, a bounded quality-diversity archive, genealogy, recovery checkpoints,
  storage guards, and a living family-tree dashboard.
- Replaced the retired Monkey lane with Evolutionary Explorer while retaining Monkey's command and
  artifacts as the historical baseline.

### Qualification changed the design

- Two full child lifetimes completed 24,000 actions in 26.2 seconds when run alone.
- The first version placed both non-progressing founders in one archive cell. That would have erased
  behavioral variety before useful milestones became reachable.
- Added a bounded action-profile component to the behavior descriptor. Repeating the exact
  qualification preserved both founders in separate cells.
- Kept every child at a clean power-on start for this pretrial. Checkpoint-assisted expeditions are
  explicitly deferred until the clean-start evidence is trustworthy.

### Current question

Can any lineage turn an initially meaningless pixel-to-button habit into a useful inherited
accident while three online learners run beside it under the same machine conditions?

## 2026-07-19 — Random baseline retired; Evolutionary Explorer designed

### Evidence changed the plan

- Concluded that Pure Monkey had answered its question: a fixed uniform action distribution can
  create lucky game progress, but it cannot retain or amplify that success.
- Retired Monkey from future headline arenas while preserving its command, artifacts, and role as
  the reproducible random baseline.
- Gracefully ended the active four-lane pretrial rather than spend the remaining budget on an
  obsolete comparison. All four final checkpoints and narrative artifacts were preserved.

### Evolutionary decision

- Chose fixed-topology, mutation-only neuroevolution for version 1 rather than starting with NEAT
  topology growth and crossover.
- Chose MAP-Elites-style quality diversity instead of allowing one scalar-score dynasty to erase
  behaviorally different champions.
- Split evidence into clean-start policy evolution and checkpoint-assisted expedition modes.
- Required every promoted checkpoint-assisted milestone to replay its full ancestral action lineage
  from power-on.
- Specified a small recurrent pixel policy, four-worker evaluation queue, immutable genealogy,
  milestone-first selection, dashboard family tree, and bounded calibration sequence.

### Next

1. Implement deterministic recurrent inference and genome round trips.
2. Implement mutation, archive replacement, genealogy, and resume tests.
3. Qualify 16-candidate and 128-candidate populations before changing the living arena.

## 2026-07-19 — Game-naive direction and first curiosity runner

### Decisions

- Made pixels-only curiosity the primary experimental track.
- Defined Monkey, Curious, and Archivist arms so random luck, learned novelty seeking, and
  snapshot-assisted archive search can be compared instead of conflated.
- Started every strict run at clean power-on; the scripted bedroom bootstrap remains calibration.
- Prohibited RAM, tile data, OCR, semantic rewards, walkthroughs, demonstrations, and language-model
  calls from the action/reward loop.
- Chose a non-neural visual archive as the first learner because it can produce millions of local
  decisions overnight without additional downloads or model usage.

### Implemented and calibrated

- Added a narrow pixels-and-buttons runner capability with no public privileged emulator methods;
  the current button sampler itself receives only a seeded pseudorandom-number generator.
- Added a frozen 20×18 quantized pixel-cell representation and bounded first-visit reward.
- Added compressed snapshot lineage, under-visited archive selection, deterministic seeds,
  recoverable checkpoints, and time/action/disk limits.
- Added a self-contained live dashboard showing the information contract, discovery curve, action
  histogram, latest screen, and discovery reel.
- A 5,000-action calibration completed in about 19 seconds, found 591 coarse visual cells, retained
  a 591-cell archive in 4.4 MiB, and reached the name-entry interface without any game-state reward.

### Next

1. Run matched overnight Monkey and Archivist development arms.
2. Inspect whether visual novelty represents progress, text variation, or animation farming.
3. Freeze the next visual-cell version only after the failure evidence is understood.

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

## 2026-07-19 — Public baseline

### Published

- Created the public `PeteAndrews1289/pokemon-red-ai` repository under the MIT license.
- Published the verified Phase 0 harness on `main` before beginning model-training claims.
- Used the GitHub private commit address so the local personal email is not exposed in history.

### Documentation direction

- Treat the project as both an engineering experiment and a documented story.
- Keep infrastructure, training, and evaluation progress visually distinct.
- Generate local run reports from sanitized traces while keeping gameplay captures outside Git.
- Preserve failed attempts and interventions so a future video can show the real learning process,
  not only a successful montage.

### Verified on the documentation branch

- The expanded suite contains 25 passing unit and private-ROM integration tests.
- Trace manifests now identify the source commit, worktree state, run class, actor, start condition,
  schemas, and intervention count without recording a checkout path.
- The report generator keeps training and evaluation evidence separate, bounds large traces, escapes
  content, redacts common sensitive forms, and refuses to overwrite its source trace.
- A reviewed public Phase 0 trace and standalone report make the repeated calibration claim
  inspectable without publishing gameplay images or snapshot payloads.
