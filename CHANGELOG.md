# Changelog

## Unreleased — Version 12 final experiential learner

- Closed the V11 continuous assisted attempt after 950.308 seconds, 329 controller actions, and
  144 online model calls, without party or badge progress. V11 remains a disclosed assisted control
  rather than the final learning claim.
- Added `self_taught_v12`: one random-initialized recurrent visual policy, four emulator workers,
  direct replay-verified ROM power-on, zero imported curriculum/actions/weights/save states, and
  zero online decision-model calls.
- Added bounded future-frame hindsight that converts visually meaningful 8–128-action excerpts from
  each rollout into at most 16 self-generated goal lessons without crossing episode resets.
- Added a correct-goal-versus-blank contrast objective and dashboard diagnostic. A matched-budget
  canary moved demonstrated-action correct-goal advantage from `-0.00018086` to `+0.00353084` after
  the fixed 0.25-weight, 0.10-margin term was introduced.
- Added direct terminal evaluation from sealed power-on, checkpoint-separated frozen exams, V12
  learning/audit telemetry, and explicit zero-assistance counters.
- Added a fail-closed 48-hour launcher with a 150-million-action safety ceiling, four environments,
  source/ROM/port/storage gates, a 100 GiB output ceiling, localhost dashboard on port 8777, and
  macOS sleep prevention. It does not launch until the T7 is mounted with at least 150 GiB free.
- Preserved three real-ROM canaries as a ROM-free qualification record. They qualify the V12
  mechanism and throughput, not a competent skill or whole-game completion.
- Added the V12 design, aggregate qualification CSV, fixed falsifiers, and updated project narrative,
  progress, roadmap, architecture, decision register, and video outline.

## Version 11 — Hierarchical completion pivot

- Closed V10 cleanly before changing architectures. Run
  `parallel-ppo-v10-recovery-8h-20260721-seed20260809` ended by SIGINT after 4,503.282 seconds
  (1h15m03.282s), 534,924 Explorer actions at 118.785/s, 522 PPO updates, 122 episodes, 567 unique
  positions, and seven promotions through Route 1. The `8h` and 150-million-action values were
  ceilings, not its achieved duration or count.
- Preserved the complete negative learning result. The Student completed 270 rounds and 3,366
  updates over 121,194 examples, ending at 43.2519% accuracy and 1.556849 NLL. Frozen exams passed
  3/32, zero skills became competent, and no composition ran. Final hashes matched; artifacts
  occupied 51,716,995 bytes.
- Closed V10's 1,977-window recovery denominator as 956 escaped, 910 context-changed, 110 expired,
  and one abandoned at campaign end, with zero controller overrides. This validates local recovery
  accounting without establishing broader exploration, reliable learning, or gameplay completion.
- Added [the V11 design](docs/version-11-hierarchical-pivot.md) and changed the primary completion
  lane from a flat reward-driven policy to a disclosed hierarchical hybrid: structured-state
  language-model planning, hand-authored current objectives, processed maps, map-local A*
  navigation, controller specialists, persistent run memory, and a separate read-only referee.
- Pinned the adaptation target to `sethkarten/continual-harness` commit
  `bbab97ad73e460b7cd7c08527d10ced30cc03fbe`. V11 runs the authenticated planner locally and keeps
  the private ROM and runtime artifacts on external storage. The experiment is labeled
  `STRUCTURED-STATE LLM PLANNER + A* NAVIGATOR + CONTROLLER SPECIALISTS`, `ASSISTED`, `POWER-ON`,
  and `HYBRID-SYSTEM`; it is not a pixels-only learning claim.
- Hardened the declared clean-start and completion boundary. Adjacent ROM-state auto-load is
  disabled by default. A claimed attempt imports no save, action lineage, evolved policy, or
  prior-run gameplay memory. Completion requires event bit `0x901` together with Hall-of-Fame map
  `0x76`, not entry into the Champion room. The final objective advances through the post-battle
  Hall-of-Fame transition, and Red recording uses its native 160×144 frame size.
- Defined four separate evidence layers for the live record: game, plan, journey, and reliability.
  The supervisor must preserve status snapshots, an append-only timeline, important frames, hourly
  Markdown chapters, source/ROM hashes, intervention counts, storage limits, and exact stop reason.
- Ran four bounded V11 canaries and preserved each failed boundary. Canary 1 ended after 25.559
  seconds with zero actions because the planner scratch path was resolved twice; unexpected clean
  harness exits now fail closed. Canary 2 was stopped after 108.110 seconds and 13 language-model
  calls with zero actions because MCP requests were cancelled under the unattended approval policy;
  the Pokémon server is now required, preapproved, and limited to the exact audited tool allowlist.
- Canary 3 proved the planner, MCP bridge, ordinary controller actions, dashboard, recording, and
  clean shutdown worked together, but rejected its own apparent progress. During Oak's visible
  introduction the structured state claimed `RedsHouse2f (3,6)` and `overworld`; the unguarded
  objective endpoint accepted `pallet_000` as complete. The operator stopped it after 251.630
  seconds and 50 actions. This is a state-truth failure, not a bedroom or Potion result.
- Added a server-enforced opening referee. Pre-control map, coordinates, and generic milestones stay
  unavailable; a directional action must produce a real bedroom coordinate change before the
  opening objective may advance. Canary 4 proved control when RIGHT moved RED from `(3,6)` to
  `(4,6)` at `2026-07-22T03:22:41Z`. `pallet_000` completed at 450.05 seconds / 111 actions, and the
  bounded run ended at 600.521 supervisor seconds (596.087 metrics seconds), 136 actions, 70
  language-model calls, 2,438,617 logged tokens, and $0.5150955 logged estimated cost. It finished
  in `RedsHouse2f (0,2)`, story index 1/84, with no party, badges, or Hall-of-Fame result.
- Found one residual server-layer pre-game map leak during Canary 4 even though the public planner
  state and objective ledger remained guarded. Fixed that leak before launching the fresh
  continuous run `v11-continuous-20260721-233300` from power-on. Its localhost dashboard uses port
  8775. The active run tests sustained planning; its launch is not a promise of completion.
- Reframed a future guided completion as both an endpoint and a teacher. Its success and correction
  states may train behavioral-cloning and DAgger-style specialists, which must later replace guided
  components one at a time under frozen power-on evaluation.

## Unreleased — Version 10 recovery before reset

- Implemented a separate `self_taught_v10` successor without editing the frozen V9 campaign or
  rewriting its provisional evidence. V10 preserves fresh random parameters, power-on-only imported
  curriculum, the run's self-generated verified frontier, separate Explorer and Student, V9
  closed-loop practice, success-only aggregation, and strict frozen exams.
- Changed generic Explorer loop handling from immediate termination to a bounded chance to recover.
  Repeated ineffective directional outcomes can activate recovery; the PPO policy continues to
  choose every button, a qualifying new visual outcome may preserve the episode, and expiry retains
  a classified failure and frontier restart. After `blocked_repeat`, only a directional material
  visual outcome is credited `escaped`; non-directional material change closes as zero-credit
  `context_changed` and is not an escape or success. Generic material actions remain eligible after
  visual-cycle or pixels-only long-stagnation triggers, which already incur the -2 loop penalty.
- Added pixels-only long-stagnation recovery after 1,024 consecutive ineffective outcomes, before
  the legacy hard watchdog can terminate. Visually effective backtracking resets that hard timer
  without clearing the independent 128-frame/eight-signature visual-cycle detector.
- Made expired recovery and emulator failure true PPO terminals; only the ordinary episode action
  ceiling remains a time-limit truncation. Bound campaign-cumulative narrative and recovery
  counters to the V10 checkpoint while intentionally resetting episode-local visual recovery state
  with fresh environment rollouts.
- Preserved the no-cheating boundary. Trainer-only recovery code may compare processed visual
  change with the policy-submitted action for reward and termination, but cannot choose, replace,
  sample, or mask an action. It receives no RAM, route distance, destination, coordinate, map, or
  direction hint.
- Added fail-closed recovery telemetry and dashboard requirements: ineffective directions, trigger
  types, activations, credited escapes, zero-credit context changes, expirations, recovery actions,
  active recoveries, abandonment on resume/episode/campaign end, unresolved inactive windows, and
  trainer-selected buttons. Every opened window must appear in exactly one denominator; unresolved
  inactive windows must remain zero.
- Added [the V10 design](docs/version-10-recovery-before-reset.md), DR-0058, qualification gates,
  falsifiers, matched-comparison metrics, claim boundaries, and the video chapter “The reset button
  was hiding the lesson.”
- Corrected the draft reward after an adversarial reward audit: escape credit is now 0.25 raw units
  and cannot exceed the 0.25 repeated-block activation penalty. A credited directional
  blocked/escape pair is recovery-reward-neutral; a blocked/non-directional context change receives
  zero credit and retains the -0.25 penalty.
- Passed deterministic E2 qualification. The focused V10/PPO/dashboard suite passed 67 checks; the
  whole default suite passed 293 with 13 private-ROM checks skipped; and all selected ROM-bearing
  files then passed 54/54 with the private ROM in 19.02 seconds. Ruff, the private-artifact guard,
  documentation links/placeholders, compilation, and diff checks also passed.
- Locked environment and reporting semantics in deterministic checks: a simultaneous pixels-only
  stagnation activation suppresses legacy termination; exact recovery expiry is terminal; the
  ordinary action ceiling remains truncated and classifies an active window abandoned; perceptual
  activity can reset hard stagnation while short-cycle detection remains live; checkpointed active
  ranks become abandoned on resume; and hourly Markdown reports detections beside the full recovery
  denominator.
- Added direct E3 mechanism calibration at the committed 289-action ground-floor fixture plus six
  settling noops. Up (0% changed pixels / 0 MAE) and Right (0.642% / 0.509) classified blocked;
  Down (20.972% / 23.165) and Left (21.215% / 26.851) classified as material directional visual
  outcomes; and Start
  (37.708% / 89.667) materially changed context. Exactly three policy-submitted Up actions opened
  recovery; Start then closed it as zero-credit `context_changed`. A fresh Up×3 sequence followed
  by policy-submitted Down closed as credited `escaped`; both sequences preserved
  `submitted == executed`. This calibrates the detector on the private ROM; it is not a gameplay
  canary.
- Passed the first bounded real-ROM V10 campaign canary on 2026-07-22 UTC (2026-07-21 local) from
  clean commit `a0ec14a5506fe3a0c4bcb15787f68be4d512d764`, seed 20260810, and one environment. It
  stopped cleanly at `duration_limit` after 144.102 seconds, 6,099 actions at 42.324 actions/second,
  and 47 PPO updates; checkpoint hashes verified and the run occupied 40 MiB. It made two verified
  promotions, reached the ground floor, and observed 93 unique map positions.
- Closed the canary's recovery denominator exactly: all 73 windows were `blocked_repeat`; 36 were
  credited `escaped`, 32 were zero-credit `context_changed`, and five expired, for a 36/73 = 49.315%
  credited escape rate across 702 recovery actions. The five expirations matched five
  `visual_recovery_expired` episodes. Active, abandoned, unresolved, and trainer-selected-action
  counts all ended at zero.
- V10 now earns a matched longer V9/V10 comparison. The canary did not activate visual-cycle or
  long-stagnation recovery and does not establish exploration superiority, learning, competence,
  long-run reliability, or Hall-of-Fame capability.
- Launched matched-configuration successor
  `parallel-ppo-v10-recovery-8h-20260721-seed20260809` from clean commit
  `513afc378d091d18560efb4af4931d882c05000d` at `2026-07-22T00:37:44.442964Z`. It retains V9's
  seed 20260809, V8 root curriculum, four environments, eight-hour/150-million-action ceiling, and
  PPO/Student practice configuration; source commit and wall-clock start differ. Recovery uses 32
  actions, blocked threshold 3, ineffective thresholds 2% and MAE 2, escape thresholds 5% or MAE 5,
  and penalties/credit 0.25/0.25/1.0. Dashboard port remains 8774.
- Preserved the stronger live V10 snapshot at about `2026-07-22T00:42:55Z` as heartbeat evidence
  only: running at 310.686 seconds, 22,532 actions (72.523/s), 22 updates, 30 episodes, five
  promotions through `chose_starter`, 286 positions, five skills, and 0/1 frozen exams with zero
  competent skills. Its 366 blocked-repeat windows comprised 165 escaped, 169 context-changed, 30
  expired, and two active; completed 364, abandoned/unresolved/overrides zero, and 3,475 recovery
  actions. `checkpoint.json` recorded 20,480 actions, both policy hashes matched independently, and
  the dashboard returned HTTP 200. No trend or result is claimed.
- Clarified a live-dashboard observability gap exposed by V10. Explorer frames and the public
  status heartbeat paused for 524 seconds while the still-healthy process performed CPU-heavy,
  synchronous Student work between rollouts, then resumed without intervention. The dashboard now
  turns its frame heartbeat amber after 20 seconds and explains that replay, practice, or an exam
  can temporarily pause gameplay snapshots. It does not fabricate frames or treat trainer work as
  Explorer actions.
- Closed the matched V10 run when the project pivoted to V11. Its exact terminal statistics and
  interpretation are recorded in the V11 section above; the earlier 310.686-second snapshot remains
  historical heartbeat evidence and is no longer the current status.

## Unreleased — Version 9 self-correcting Student

- Declared and launched campaign
  `parallel-ppo-v9-self-correcting-8h-20260721-seed20260809` from source commit `d1c0c0d` at
  `2026-07-21T21:43:57.163627Z`. Its immutable launch contract is seed 20260809, eight hours,
  150,000,000 actions, four environments, 256 rollout steps, strict reverse practice at two
  consecutive 27/30 windows, practice interval 4 with two attempts, frozen exams every 16,384
  Explorer actions, a 100 GiB output cap, and a 50 GiB free-space floor. Dashboard port is 8774.
- Kept the long run fresh-start. Its V8 source contributes only the power-on root curriculum state;
  no V8 weights, controller actions, or learned skills enter V9. No mid-run rule change is allowed.
- Recorded the first exam-boundary snapshot as provisional E1 live evidence: at 161.420 seconds and
  16,388 Explorer actions (101.524/s), the run had 16 PPO updates, two verified promotions, three
  skills, and milestone index 2, `Reached the ground floor`. The Student had 13 rounds, 60 updates,
  0.1396277 action accuracy, and 2.105477 NLL. Practice was 7/8 exact target with one timeout,
  seven retained successes, and 14 success-only updates. The one 556-action frozen exam failed;
  zero skills were competent and no composition ran. These are not terminal results or evidence of
  a trend.
- Closed that run intentionally at the user's request so V10 could begin. It ended
  `stop_requested` at `2026-07-22T00:36:38.849066Z`, after 10,359.143 seconds (2h52m39.143s),
  1,431,556 Explorer actions at 138.1925/s, 1,398 PPO updates, 558 episodes, 716 unique positions,
  seven promotions through Route 1, and eight discovered skills. The `8h` name was a ceiling, not
  the actual duration. Final hashes verified and artifacts occupied 57 MiB.
- Recorded the complete V9 learning denominator: 797 Student rounds, 10,692 updates, 330,505
  examples, 68.5919% accuracy, and 0.904136 NLL; 558/698 exact practice attempts, 882 practice
  updates, and 651,629 practice actions; 4/87 frozen exams, zero competent skills, and no
  composition. The run also recorded 139 visual-cycle and 419 stagnation endings plus 146 battle
  successes. Better fit and isolated exam passes did not become reliable reusable behavior.
- Rejected two background handoffs that both failed before creating the run: a generic `nohup`
  handoff and a launchd service whose context lacked permission to access the external SSD. The
  successful detached user-session launch preserves the interactive user's permissions and adds
  sleep prevention; no failed launcher changed the experiment state.
- Preserved the first V9 real-ROM canary,
  `parallel-ppo-v9-canary-20260721-seed20260801`, as a failed pre-hardening diagnostic. It was
  configured for 180 seconds but synchronous work overran the wall-time boundary; a manual STOP
  ended it at 248.801 seconds and 12,360 Explorer actions. It reached index 3, `Stepped outside`,
  with three promotions and six skills. Closed-loop practice recorded 19/22 exact targets and
  three timeouts; frozen exams ended 0/3. Immediate success-only training reports replaced rather
  than merged richer periodic dashboard diagnostics, so those fields are not treated as an
  authoritative final report. Manual STOP exposed the defect; shutdown did not cause it.
- Fixed synchronous campaign cancellation and status/report merging in commit `e1ea199`. The
  authoritative qualification canary,
  `parallel-ppo-v9-canary2-20260721-seed20260802`, ran from
  `2026-07-21T21:31:41.473766Z` to `21:34:08.155927Z`, a 146.682-second process span including
  roughly 2.6 seconds of setup/finalization. Its campaign clock honored the 144.0-second budget,
  ending `duration_limit` at 144.082 seconds with 12,520 Explorer actions at 86.895/s, 12 PPO
  updates, two promotions, zero promotion failures, and three skills through index 2, the ground
  floor.
- Qualified V9 mechanism, observability, and wall-time control—not competence. The authoritative
  canary completed 20 Student rounds, 64 optimizer updates, and 1,400 examples; final action
  accuracy was 0.1415313 and NLL 2.211105. Practice reached 16/22 exact targets (72.727%), with two
  wrong-state outcomes and four timeouts. It retained 16 replay-verified successes, applied 32
  success-only updates, and exposed three aggregated practice datasets containing 39 examples and
  20,000 bytes in the last replay round. Frozen exams ended 0/3, zero skills were competent, and
  no learning success is claimed. The run occupied 42,336,864 bytes.
- Recorded V8's final longer run,
  `parallel-ppo-v8-distilled-student-8h-20260721-seed20260793`. It ended by explicit stop request
  after 5,668.623 seconds, from `2026-07-21T18:52:49Z` to `20:27:21Z`, with 784,386 Explorer
  actions at 138.373 actions/second and 1,532 PPO updates. Seven verified promotions reached
  milestone 7, Route 1. Seven skills compressed 13,011 original actions to 8,582 using 238 oracle
  calls and 373,639 replay actions. The Student completed 387 rounds, 2,513 updates, and 137,437
  examples; final action fit was 53.0817% accuracy and NLL 1.295676. It passed only 1/47 frozen
  exams, so zero skills became competent and zero compositions ran. This is the final V8
  behavioral result and remains negative.
- Preserved the clean V8 qualification canary as distinct historical evidence. It produced
  four verified/distilled lessons, 51 Student rounds, 134 optimizer updates, two clean resumes, and
  bounded replay, but passed 0/7 frozen exams; zero skills were competent and composition remained
  ineligible. Its then-current supported-ROM suite passed 245/245 in 24.80 seconds; neither figure
  is overwritten by the longer run.
- Integrated V9 as an engineering-checked response to exposure bias. Behavioral cloning remains
  the canonical Student's warm start, but the Student must then act closed loop on states produced
  by its own buttons. The current suite passes 276 non-integration and 12 integration checks, 288
  total. The corrected real-ROM canary qualifies the mechanism and reporting boundary, not frozen
  competence or later-game progress.
- Implemented consecutive edge normalization under `self-generated-consecutive-skill-graph-v1`:
  derive
  exact adjacent source-to-next-target lessons from replay-local first hits, bind original offsets,
  stable-state and private-snapshot identities, reject incomplete/non-monotonic/ordinal-only state
  reuse, and add no imported or human-selected action. Public audits omit actions and save payloads.
- Integrated graph-audit hash binding into every normalized V9 skill and fail-closed checkpoint
  validation, so a skill cannot silently detach from the exact graph that created it.
- Implemented reverse practice under protocol `v9-student-closed-loop-reverse-practice-v1`: horizons
  expand 8/16/32/64 through the full edge, practice promotion requires two consecutive
  non-overlapping 27/30 windows, deterministic retention is 25%, and pending scheduling choice plus
  attempt seed survive resume exactly.
- Restricted practice observations to `pixels`, `action_history`, and `target_pixels`. Reset
  protocol `zero-recurrent-sentinel-history-duplicate-frame-v1` zeroes recurrent state and keeps
  skill/checkpoint/rung/horizon identities trainer-only.
- Defined success-only aggregation under `v9-student-successful-rollout-v1`. Failed attempts remain
  in the denominator but cannot become imitation labels; successful Student actions require exact
  target-state and replay verification. Terminal-reason counters distinguish `exact_target`,
  `timeout`, `emulator_stopped`, and `milestone_wrong_state`. Deterministic reservoir sampling
  retains at most 32 success records per rung; immutable bounded shards rotate through Student
  replay instead of repeatedly loading one full success artifact.
- Bound the mutable practice ledger to the same Student checkpoint generation. Resume restores the
  hash-matching practice snapshot, pending choice, promotion windows, terminal denominator,
  reservoir, and replay provenance, rolling live practice bookkeeping back with the model rather
  than pairing a newer curriculum with an older Student.
- Preserved strict frozen exams. Reverse-rung promotion does not grant competence, frozen attempts
  apply no update or aggregation, and restore-free power-on composition remains separate.
- Predeclared same-boundary recurrent PPO recovery as a future conditional automatic escalation
  targeting the canonical Student. It is not implemented or active in initial qualification and
  cannot be enabled before the closed-loop path and matched BC-only ablation qualify.
- Added the V9 architecture, qualification ladder, falsifiers, actor boundary, budget accounting,
  claim language, dashboard requirements, and “It Never Practiced Being Wrong” video chapter in
  `docs/version-9-self-correcting-student.md`.

## Version 8 — parallel recurrent PPO

- Froze the Version 8 design while preserving the active Version 7 long run unchanged as its
  shared-policy, raw-trajectory denominator.
- Separated four PPO Explorers from a recurrent Student with its own parameters and
  optimizer. V8 retains V7's ban on demonstrations, imported actions, predecessor weights, route
  graphs, coordinates, and semantic actor goals.
- Added self-generated trajectory distillation. Trainer-only repeated-state signatures and bounded
  chunk reduction may propose deletions, but every accepted edit must replay from the same source
  to the same protected outcome. Raw/compressed mappings and full edit accounting remain auditable.
- Added sequence-aware Student replay with recurrent burn-in, overlapping horizons, temporal visual
  goals, and skill-balanced sampling, plus a prerequisite scheduler with minimum evaluation,
  mastery, retention, starvation protection, and competence revocation.
- Added fail-closed self-generated composition training. The deepest competent chain is streamed
  once from exact power-on and every protected endpoint must match before training. Only bounded
  pre/post-switch excerpts are retained, with continuous context across each switch, compact
  per-skill clips, goal indices, and hash-bound audit metadata; failed fingerprints never train.
- Kept only the current deepest verified composition active in Student loading while preserving
  prior ledgers/audits as archived evidence. The active composition receives one replay ticket per
  constituent skill, at least half of its draws rotate deterministically across boundaries through
  a checkpointed cursor, and individual skills are split at admission into immutable hash-bound
  replay shards. Each shard owns no more than 512 loss-bearing examples and may retain up to one
  burn-in predecessor prefix. Persistent per-skill cursors cover every shard across resumes while
  routine replay opens only one bounded shard per skill; the original full NPZ is provenance-only.
  Focused unit and real-ROM integration checks cover these controls, while learned multi-skill
  behavior remains unproved.
- Kept per-action imitation loss uniform across replay-proven local actions and composition
  excerpts. Extra composition exposure comes only from the declared one-ticket-per-constituent-
  skill replay schedule, not recency or gamma weighting.
- Exposed Student replay-memory status: individual/active composition dataset counts, retained
  examples and bytes, train/stored ceilings, total and loaded shard counts, loaded loss-bearing and
  context examples, shard bytes read, full-skill artifacts opened, replay cursors and minimum
  completed coverage cycles, ticket-expanded sampling-cycle size, archived composition count,
  active switch examples, and failed composition builds.
- Added periodic frozen Student exams and four distinct progress depths: discovery, distilled
  library, local competence, and restore-free composition. Training loss and PPO reward remain
  diagnostics rather than competence evidence.
- Documented V8's information contract, expanded crash-integrity boundary, qualification ladder,
  claim limits, falsifiers, matched ablations, dashboard panels, and video narrative in
  `docs/version-8-distilled-student.md`.
- Passed the first V8 real-ROM mechanism and clean-resume canary. It stopped and resumed twice,
  completed 5,248 Explorer actions in 48.038 seconds, verified `game_started`, distilled one
  256-action edge to 254 actions with a successful final replay, and trained the separate Student
  for eight updates over 128 examples. Final Student NLL was 2.06915 and action accuracy was
  16.14%; its model, optimizer, and bound ledger hashes matched the checkpoint.
- Preserved the original canary's 2/2 local and 14/14 power-on duplicate deterministic attempts as
  historical mechanism wiring only. They are explicitly superseded and provide no robustness
  evidence, chance comparison, later skill, production competence, or Hall-of-Fame behavior.
- Passed a clean-source V8 canary from commit `4c3c1fc`. It started from random power-on, survived
  two stop/resume cycles, and ended by request at 3,584 Explorer actions after reaching milestone
  index 4, `met_professor_oak`, with four verified and distilled skills.
- Recorded the negative learning result without promotion: 51 Student rounds and 134 optimizer
  updates ended at NLL 2.07149, 13.7795% action accuracy, and 0/7 frozen exams. No skill was
  competent and no composition attempt was eligible.
- Qualified bounded replay on the canary artifacts: the final round selected four of five shards,
  loaded 1,016 loss-bearing plus eight loss-free context examples, completed at least five coverage
  cycles, and opened zero full skill artifacts during routine replay.
- Changed V8 grading to exactly one deterministic attempt per Student checkpoint. The rolling
  10-wide, 8/10 competence window now spans ten distinct checkpoints and Student versions; the
  cadence is 16,384 Explorer actions, never ten duplicate resets in one exam round.
- Checked the grading scale against the safety ceiling: `66 × 10 × 16,384 = 10,813,440` Explorer
  actions, about 10.8 million, is the all-milestone local-exam opportunity floor. It remains below
  150 million but excludes discovery, composition, replay, and Student-training work.
- Removed authored progress from the V8 stagnation watchdog. Route distance, canonical milestone
  index, and Viridian Mart script no longer reset its timer; general durable consequences and new
  positions remain allowed. V7 intentionally retains its historical authored termination shaping
  so the live denominator remains resume-compatible; that boundary is now disclosed as not fully
  blind.
- Hardened the zero-authored-guidance reward path. When V8's navigation and Mart reward weights are
  disabled, reward tracking no longer calls authored route guidance or active-goal lookup and
  skips Mart-distance and Mart-script calculations entirely.
- Required a clean Git commit for V8 launch, including untracked-file detection. V8 checkpoints bind
  exact source and verified-ROM identities plus curriculum, Explorer, Student, Student optimizer,
  and checkpoint-specific skill/exam ledger state.
- Hardened atomic artifact fallback: a hash-matching `previous` model or optimizer is copied back
  to `latest` atomically without consuming the fallback. A unit test recovers again after a second
  interrupted rotation; a full process-kill real-ROM crash twin remains pending.
- Bounded routine checkpoint I/O without weakening resume. A checkpoint fully validates every new
  or changed skill shard plus each new or active composition, but may trust unchanged archived
  artifacts only when their seals are already bound by the last atomically committed checkpoint.
  Resume and full audit still hash-check every skill, shard, composition dataset, and audit.
- Preserved V7 resume compatibility by omitting V8-only controls from its serialized configuration.
  A legacy manifest's missing ROM identity is backfilled only on resume after ROM verification,
  without rewriting its original source provenance.
- Expanded the V8 dashboard to show four separate depths, explicit Hall-of-Fame completions,
  Explorer/Student hashes, the locked V7 denominator, and distillation-audit fallbacks that label
  absent historical metrics instead of silently displaying zero.
- Added `--v7-denominator PATH` for fresh V8 launches. It read-only pairs a running or finished V7
  self-taught checkpoint with its hash-matching latest/previous model generation, then seals only
  path-free run ID, actions, milestone, model/checkpoint hashes, source state/timestamps, and lock
  time into the V8 manifest. Resume reuses the seal and rejects re-locking.
- Renamed the V8 dashboard's total to **Explorer actions** and expanded its Student card with shard
  stored/owned/context footprint, bytes, coverage cycles, and zero-full-source-open evidence. The
  exam copy now explicitly names trainer-side RAM milestone goal switching.
- Clarified the V8 composition boundary. One frozen Student chooses every button, while the
  trainer-side RAM referee switches an ordered playlist of the run's self-generated target clips
  at declared milestones. This supplies no authored quest direction or controller action, but it
  is goal-conditioned hierarchical control; a Hall-of-Fame result would be completion under that
  declared goal-switching protocol, not unaided pixel-only autonomy.
- Fixed a P0 composition-verifier defect found on the real ROM: PyBoy's complete game-area hash can
  change across save/load even when the processed visual and enumerated gameplay RAM are exact.
  Composition now uses the exact save/load-stable visual-plus-RAM signature; distillation retains
  the stricter game-area hash because all deletion candidates replay from the same snapshot.
- Added real-ROM verifier acceptance for a stored two-skill
  `power_on → game_started → left_bedroom` chain, a four-noop save/load regression, and validly
  encoded wrong-endpoint rejection. These prove endpoint and composition mechanics only; they do
  not show that a Student learned or autonomously produced the stored actions.
- Preserved the live V7 denominator snapshot at `2026-07-21T17:29:11Z`: 6,466,564 actions, Route 1,
  seven discoveries, zero competent skills, 19/1,274 rehearsals, and 66,560 imitation examples.

- Added Version 7's demo-free self-taught mode. It requires random neural initialization, retains
  only the unique verified power-on snapshot, and rejects predecessor policies and consolidation.
- Added self-generated visual skills. Replay-verified transitions save their own terminal screen,
  reconstructed pixel/action examples, source state, action count, and integrity hashes.
- Added direct recurrent-policy self-imitation using only the current run's successful actions,
  balanced rehearsal of up to eight skills, weakest-skill scheduling, and rolling 8/10 competence.
- Removed authored quest direction from V7 reward: milestone, Mart, active-route, and landmark-
  recovery components are explicitly zero. The actor receives pixels, recent actions, and only a
  self-discovered target screen during rehearsal.
- Added dashboard and narrative measures for discovered skills, competent skills, weakest-skill
  window, imitation updates, and examples.
- Added a checkpoint-specific self-skill ledger. Resume restores the exact ledger paired with the
  saved model, so later competence or imitation bookkeeping cannot invalidate crash recovery.
- Passed 188 tests with the private ROM, including a real recurrent self-imitation gradient update
  and restart-safe pending self-imitation state.
- Passed the first 8,192-action, four-worker V7 canary from random parameters and power-on only. It
  discarded 25 inherited entries, imported zero parameters/actions, replay-verified game start and
  the ground floor, created two skills, trained eight imitation updates over 2,048 examples, and
  reproduced the ground-floor skill once with zero verification failures and matching hashes.
- Preserved the first longer-launch preflight. It reached five verified milestones through starter
  selection in 41,256 actions, then stopped cleanly when checkpoint/ledger crash atomicity was
  identified for hardening before the overnight run.

- Added Version 6 retained-policy consolidation. A new campaign may import one clean, hash-valid,
  architecture-compatible Version-5.2-or-later PPO policy and optimizer instead of restarting from
  the Frontier Apprentice seed.
- Added a backward competence scheduler that separates frontier discovery episodes from earlier-
  start rehearsal, fixes the target at the current verified frontier, and moves the start one
  verified checkpoint backward only after a declared rolling success threshold.
- Added persistent per-gate attempts, successes, best reached index, rolling windows, passed gates,
  and an explicit power-on training gate. The ledger is atomic and hash-bound into every PPO
  checkpoint.
- Added four dashboard and hourly narrative measures: consolidation start, target, rolling
  competence, and backward gates passed. Frontier restores cannot count as competence.
- Preserved the first failed V6 canary, which incorrectly subtracted the inherited policy's old
  timestep count from the new campaign budget and stopped after one 1,024-action rollout. Added a
  regression that separates fresh retained campaigns from true resumes.
- Passed the corrected 8,192-action four-worker V6 canary with eight updates, retained policy and
  optimizer provenance, all four frames, zero promotion failures, and matching model, four novelty
  memories, and consolidation-state hashes. One of two genuine earlier-start episodes reached the
  Pokédex; the shortened 3/4 gate correctly remained closed.
- Passed 180 tests with the private supported ROM and documented the architecture, evidence ladder,
  limitations, production questions, and video narrative in `docs/version-6-consolidation.md`.
- Closed V5.2 cleanly at 5,354,500 actions, 5,229 PPO updates, 3,146 episodes, and eight verified
  promotions with zero replay failures. It reached Route 1 at action 707,472, then spent more than
  four million additional actions without reaching Viridian City. Its model and four terminal
  novelty memories matched their recorded hashes.
- Launched the first declared 24-hour V6 run with V5.2's exact policy and optimizer, four workers,
  a 50/50 frontier-to-consolidation split, an 8/10 rolling gate, and the 150-million-action safety
  ceiling. The initial gate connects `left_oaks_lab_with_pokedex` to Route 1.
- Closed that V6 diagnostic at 1,001,476 actions, 978 updates, 390 episodes, and 72m 51s. Across 206
  earlier-start attempts it reached Route 1 11 times and ended at 5/10 in the rolling window, below
  the required 8/10. No backward gate or power-on gate passed.

- Closed Version 5.1 cleanly after 3,437,572 actions, 3,357 PPO updates, 1,900 episodes, and six
  verified promotions. It reached the Pokédex at action 402,320 with a 10,819-action complete
  lineage, then spent 3,035,252 more actions without reaching Viridian Forest.
- Preserved the two-sided result: active-goal backtracking worked through Pallet Town and Oak's Lab,
  while all 1,900 episodes still ended in either long stagnation or a visual cycle. The terminal
  model and all four novelty memories matched their hashes.
- Added Version 5.2's seven new chapter checkpoints from leaving Oak's Lab with the Pokédex through
  Route 2, both Viridian Forest gates, and Pewter Gym. The canonical catalogue now contains 66
  outcomes without renumbering anything already verified through Pokédex index 15.
- Added a source-disclosed map graph through the first Gym. The assisted teacher receives only the
  next map and bounded route distance, never target tiles, menu commands, battle actions, or scripted
  buttons.
- Added bounded navigation-recovery reward: after at least 12 stationary actions under a landmark
  goal, credit is paid only when movement resumes, is disabled in battle, and is capped at three
  payments per episode.
- Passed 174 tests with the private supported ROM and a fail-closed migration audit of the completed
  V5.1 model, four worker memories, and all 24 verified curriculum entries.
- Passed an 8,192-action, four-worker real-ROM V5.2 canary with eight PPO updates, 256.18 combined
  actions/second, all four live frames, +24 bounded recovery credit, zero promotion failures, and
  matching terminal model plus four novelty-memory hashes.
- Added the design, completed predecessor denominator, evidence boundary, falsifiable run questions,
  and video narrative in `docs/version-5-2-northbound.md`.
- Declared and launched the first 24-hour V5.2 run from commit `c8a4be3`, seed `20260782`, with four
  workers, a 150-million-action ceiling, hourly narrative updates, and the verified Pokédex
  curriculum.

- Closed Version 5 cleanly after 1,390,596 actions, 1,358 PPO updates, 723 episodes, and three
  verified promotions. It entered the Mart at action 619,660 and obtained Oak's Parcel at 619,956.
- Preserved a negative result: Mart-approach credit continued accumulating after the Parcel,
  proving that a locally bounded lesson can still be globally obsolete.
- Added Version 5.1 active-goal reward ownership. Mart approach and dialogue shaping now expire as
  soon as their owning lesson is complete.
- Added three item-qualified return milestones for Route 1, Pallet Town, and Oak's Lab so a fetch
  quest's reverse leg becomes visible, replay-verifiable curriculum progress.
- Added a persistent certified/observed map graph, assisted next-route-map context, signed
  potential-based route reward with zero oscillation profit, and goal-aware stagnation handling.
- Added fail-closed Version-5 curriculum migration and retained all 21 entries plus three verified
  promotions in a migration audit; Version-5 weights remain ineligible under the changed protocol.
- Added the full design, limitations, falsifiable questions, and video beat in
  `docs/version-5-1-backtracking.md`.
- Passed a four-worker 8,192-action real-ROM Version-5.1 canary with eight PPO updates, +24 net
  active-route credit, no expired Mart reward, zero verification failures, and matching terminal
  model plus four novelty hashes.

- Closed Version 4 cleanly at 1,776,644 actions and 1,735 updates. Its 2,109-action Route 1 suffix
  reached Viridian City at action 790,900 and passed one edge replay plus three complete power-on
  replays, producing the first PPO curriculum promotion.
- Added Version 5's separately labeled assisted teacher: a 64 × 64 episodic visited-position map,
  next-milestone goal, coarse navigation/interaction/battle hint, and map/goal context.
- Inserted the replay-verifiable `entered_viridian_mart` micro-milestone without changing any
  earlier ordinal; Oak's Parcel and later milestones shift by one.
- Added bounded new-best-distance shaping toward the Viridian Mart door and map-scoped Mart script
  progress. Neither reward can be harvested by simply walking away and returning.
- Added fail-closed migration from a completed Version-4 curriculum, including terminal model and
  worker-memory hashes, entry hashes, canonical milestone checks, and one-root validation. Version-4
  weights remain ineligible under the changed observation and reward objective.
- Increased furthest-frontier reset sampling to 90 percent and added the current lesson plus both
  lesson rewards to the live dashboard and hourly narrative.
- Passed a 16,384-action four-worker real-ROM Version-5 canary with 16 PPO updates, 14.5 bounded
  Mart-approach credit, zero verification failures, and matching terminal model/memory hashes.

- Added four-worker recurrent PPO so every rollout can update one shared CNN-LSTM instead of
  teaching only from rare verified named promotions.
- Added pixels-only and separately labeled 24-value privileged actor modes, with exact warm-start
  of the existing visual encoder, actor LSTM, and action head.
- Added a frozen private curriculum built only from one atomic checkpoint's replay-verified
  Archive-v2 cells.
- Kept named curriculum advancement behind one exact parent-edge replay and three exact complete
  power-on replays; reward remains diagnostic rather than completion evidence.
- Added hash-bound latest/previous model checkpoints, explicit partial-rollout restart semantics,
  stop/status commands, storage guards, TensorBoard output, hourly Markdown chapters, and a live
  multi-environment dashboard.
- Benchmarked 2, 4, and 6 workers on the target 8 GB M1 and selected four. Pixels-only, privileged,
  and production-shaped canaries completed real optimizer updates and correct final checkpoints.
- Documented the influence of PWhiddy's Pokémon Red PPO experiments, the differences in observation
  and evidence rules, and a video narrative that keeps learning, behavior, and verified proof as
  separate meters.
- Rejected version 1 after 862,212 actions exposed episode-reset novelty farming: 1,784 local
  position rewards corresponded to only five new global positions in one measured slice.
- Persisted reward memory independently for every worker across episode resets and resumes, primed
  every restored parent without payment, hash-bound all worker memories into PPO checkpoints, and
  bumped the protocol before a fresh run.
- Rejected version 2's unconditional battle-ending reward after it became the dominant return while
  verified progress remained at Route 1. Its preserved one-hour record contains 1,064,964 actions,
  1,040 updates, 260 episodes, 515 positions, zero promotions, and 1,003 rewarded battle exits.
  Version 3 pays a much smaller battle-success bonus only after durable experience or capture
  progress, records no-progress exits separately, adds bounded worker-lifetime experience rewards,
  and refuses cross-protocol resume.

## Unreleased — Visual Apprentice Stage 0

- Added immutable extraction of the certified 419-action Q1 promotion into 420 processed private
  decision-boundary frames with exact source, action, array, and terminal integrity checks.
- Added a frozen 468,312-parameter CNN-LSTM behavioral-cloning actor using two `72 × 80` grayscale
  frames, previous action, and recurrent state; no referee or checkpoint value enters the actor.
- Added bounded CPU overfit training, teacher-forced and feedback-mode exact-label gates,
  container-independent parameter hashing, safe frozen reload, metrics, events, and a live page.
- Added a clean-power-on live evaluator with a 1,000-action ceiling and no snapshots, rewards,
  updates, retries, interventions, or restored recurrent state.
- Added an `apprentice` PyTorch extra and deferred sb3-contrib to later recurrent-PPO work.
- Extended the publication guard to reject private NumPy datasets and model checkpoint payloads.
- Kept the Stage-0 claim boundary explicit: implementation and synthetic checks do not prove a
  real-ROM result, recovery, held-out skill, or general Pokémon play.

## Unreleased — Q1 `left_home` result

- Completed both frozen 20,000-action checkpoint-search seeds with zero interventions and exact
  action-limit stops.
- Verified a 419-action power-on lineage through `left_home` in seed `20260731`; all three milestone
  promotion replays matched hashes and canonical semantics.
- Preserved seed `20260730` as a valid failure at `left_bedroom`, making the declared Q1 result 1/2
  rather than promoting one successful clip into a two-seed pass.
- Recorded 40,000 exploration actions, 954,704 replay actions, 2,984/2,984 replay passes, and 2,502
  stored evidence cells across the complete result.
- Accepted the narrow H3 milestone claim while keeping learned-policy claims open: the current
  random button emitter receives no observation and performs no policy update.
- Added a public metadata-only Q1 record with both seeds, integrity hashes, timeline, interpretation,
  scaling limits, and the next matched-emitter decision.
- Added a dual-frame recording requirement after the exact semantic `left_home` capture occurred
  during a visually unclear transition.

## Unreleased — Hall-of-Fame completion foundation

- Concluded the six-lane selection × mutation lab without naming a winner: frontier selection
  roughly doubled game-start retention, but all six treatments remained on one map with no party,
  and most children spent nearly their whole lifetime repeating one action.
- Defined a six-level evidence ladder separating infrastructure, discovered checkpoints, complete
  lineage replay, and one frozen policy completing Pokémon Red.
- Added a 55-outcome referee through a strict Hall-of-Fame condition, including mandatory key items,
  HMs, locations, and story gates.
- Added a private content-addressed frontier store with complete ancestry, exact action segments,
  semantic identity hashes, capacity control, orphan recovery, tamper-evident audit events, and
  ancestry-wide replay quarantine.
- Added a bounded single-writer expedition runner with exact random/counter/archive resume,
  stop/resume ledger preservation, adaptive 32–1,024-action suffixes, disk ceilings, event captures,
  status commands, and a safe localhost-only dashboard.
- Rejected a hash-only verifier that could reproduce a deliberately forged Hall-of-Fame label while
  the real ROM remained at power-on; replay now recomputes the milestone from actual semantic state.
- Closed audit failures involving forged descriptors, unverified-ancestor replay laundering,
  evicted-cell resume counts, torn audit tails, and force-added private files beneath ignored paths.
- Passed Q0 against the private ROM: a 512-action exploration admitted 42 cells and replayed all 42
  exactly, while correctly reporting Oak's introduction as `power_on` rather than game progress.
- Froze Q1 as two fresh `left_home` trials, each limited to 20,000 exploration actions, one hour,
  and 2 GiB. The current suffix generator is labeled as seeded random, not as a learned pixel model.
- Blocked any multi-day or 150-million-action expedition until streaming lineage replay, indexed
  verification, bounded validation, and private-payload retention prevent superlinear growth.

## Unreleased — evolutionary successor decision

- Concluded the first 90-minute successor pretrial with clean final checkpoints: Evolutionary
  Explorer evaluated 236 policies over 2,838,873 actions and preserved a 33-elite tier-1 archive;
  the online learners completed roughly 2.2–2.56 million actions each and plateaued around Pallet
  Town and Route 1.
- Recorded a narrow inherited game-start behavior and diagnosed two candidate bottlenecks:
  archive-wide uniform parent selection and destructive broad mutation.
- Froze the development archive and specified a six-lane 2 × 3 engineering fork: uniform/frontier
  selection crossed with broad/gentle/multiscale mutation, with 1,536,000 actions per lane and a
  clean power-on Pokémon start for every child.
- Added a public design record with evidence hashes, audience-friendly explanations, dashboard
  measurements, a video narrative spine, and explicit fresh-run claim boundaries.
- Implemented the generic N-lane evolution orchestrator, paired 2 × 3 preset, safe local dashboard,
  hourly Markdown chronicle, synchronized JSONL evidence, and graceful group stopping.
- Qualified all six treatments against the private ROM and frozen 33-elite archive: every lane
  completed exactly one 12,000-action child, wrote one genealogy record, and exited successfully.
- Qualified whole-lab recovery by interrupting all six children, resuming against the identical
  manifest and archive hash, and refusing completion until every terminal status met the exact
  action and evaluation ceilings.
- Added synchronized ten-minute visual sets, dashboard and image hashes, and exact first-milestone
  captures so the eventual video record does not depend on an overwritten latest frame.
- Added explicit uniform/frontier selection, broad/gentle/multiscale mutation, sealed archive
  import, parent/lineage provenance, mutation channels, milestone timing, and action telemetry.
- Implemented the 13,096-parameter recurrent pixel policy, deterministic genome serialization,
  mutation-only reproduction, bounded quality-diversity archive, immutable genealogy, and resume
  checkpoints.
- Added a clean-start evolutionary runner and living family-tree dashboard; replaced Monkey with
  Evolutionary Explorer in the successor arena pretrial.
- Set the pretrial lifetime to 12,000 actions and the founding population to 16 genomes.
- Added an early action-profile diversity bin after a two-child qualification revealed archive
  collapse before either child reached a semantic milestone.
- Retired Pure Monkey from future headline arenas after it completed its role as a non-learning
  random baseline; retained its runner and artifacts for reproducibility.
- Specified Evolutionary Explorer as its planned replacement: a small recurrent pixels-only policy
  evolved through mutation-only, quality-diversity selection.
- Defined separate clean-start and checkpoint-assisted evidence tracks, with complete power-on
  lineage replay required for promoted expedition milestones.
- Added planned genome, archive, genealogy, dashboard, compute, storage, and qualification gates.
- Reframed the video narrative around the question, “What if a useful accident could reproduce?”

## Unreleased — discovery reward protocol

- Standardized all continuous agents on eight deterministic actions and removed Select.
- Added a sealed RAM referee for every lane without leaking its measurements into blind policies.
- Added Pokédex, event-flag, warp, party-level, move, item, and blackout measurements.
- Rebalanced generic outcome rewards away from local-coordinate farming.
- Added explicit Oak's Parcel, Pokédex, Poké Ball, key-item, and HM milestones for Conventional.
- Added mild repeated-action, revisitation, and stationary-loop penalties.
- Added per-component reward ledgers and richer live dashboard fields.
- Ignore temporary starter-preview Pokédex bits until the in-game Pokédex is obtained.

## Unreleased

- Scale the final arena to 1,048,576 policy buckets and a 150-million-action safety ceiling.
- Add 128-step returns, bounded uniform replay, and protected important-transition replay.
- Remove visual novelty from Outcome-Rewarded and Conventional reward channels.
- Capture exact screenshots and referee telemetry for semantic milestones.

This project records milestones, not just software releases. A version is considered meaningful
only when its behavior and evidence can be reproduced from the corresponding Git commit.

## Unreleased

### Added

- Game-naive pixels-only Monkey and visual-novelty Archivist runners from clean power-on
- Narrow actor capability exposing pixels and buttons but no RAM, tiles, snapshots, or raw emulator
- Bounded visual novelty, compressed discovery archive, action lineage, and deterministic seeds
- Atomic checkpoints plus wall-clock, action, archive, output-size, and free-disk safeguards
- Live visual dashboard with discovery curve, action distribution, latest screen, and discovery reel
- Blind-curiosity protocol covering leakage, honest claims, expected failures, and run controls
- Standalone visual HTML reports generated from sanitized smoke/bootstrap traces
- Reviewed public Phase 0 calibration evidence with a sanitized trace and generated report
- Documentation hub, narrative, evidence board, detailed roadmap, and visual storytelling guide
- Episode 0 YouTube production outline and plain-language glossary
- Experiment-record and agent-card templates
- GitHub experiment issue form and reproducibility-focused pull request template
- Automated local-document link and placeholder checks
- Git commit, dirty-worktree, actor, run-class, schema, start, and intervention provenance in traces
- Private home-path and common credential-pattern checks in the repository safety guard

### Planned

- Matched overnight Monkey and Archivist development runs
- Pixel-only learned curiosity policy without demonstrations or semantic rewards
- Sealed post-hoc referee for interpretation, visibly separate from training inputs
- Frozen restore-free power-on evaluations

## 0.1.0 — 2026-07-19

### Added

- Exact Pokémon Red US Rev. 0 ROM fingerprint validation
- Headless PyBoy 2.7.0 emulator lifecycle and controller timing
- In-memory, integrity-checked snapshots bound to the ROM and emulator version
- Sanitized JSONL traces and private local screenshots
- Deterministic clean boot through the RED and BLUE name menus
- Verified first playable bedroom state at logical frame 9,804
- Versioned, six-field read-only state observation
- One-tile controller calibration from the bedroom start
- Unit, private-ROM integration, lint, CI, and artifact-safety checks

### Evidence

- 13 tests passed on the development machine
- Two independent clean boots produced identical state, screen, game-area, and snapshot hashes
- No ROM, save data, private path, or generated gameplay image entered Git

The detailed engineering record is in [docs/devlog.md](docs/devlog.md). Future model results will
be reported separately from harness milestones so infrastructure progress cannot be mistaken for
learning progress.
