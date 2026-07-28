# V12 qualification: can ordinary experience become a goal-sensitive lesson?

This directory is the public, ROM-free summary of three private real-ROM canaries run on the target
M1 iMac on 2026-07-22. Private checkpoints, frames, save states, and the ROM remain outside Git.
Exact aggregate measurements are preserved in [`summary.csv`](summary.csv).

The qualification was not a miniature game-completion claim. It tested whether the final learner
could:

- start from a directly created and replay-verified clean power-on state;
- train one recurrent actor across four emulator workers;
- relabel its own visually meaningful future states as goals;
- reject static excerpts and episode-boundary crossings;
- train every pending lesson exactly once;
- show whether the goal actually changes demonstrated-action probability;
- keep online language-model calls, demonstrations, imports, and trainer-selected buttons at zero;
- write live dashboard, narrative, checkpoint, recovery, and terminal-evaluation evidence; and
- stop cleanly at its declared action limit.

## Preserved sequence

### Canary 1 — the pipeline worked, but goal use was unmeasured

`v12-canary-20260722-002324`, seed 20260722, trained for 20,000 counted actions. It
replay-verified three discoveries through `Stepped outside`, generated and trained 624 hindsight
lessons, and retained useful throughput. It passed only 1/9 deterministic exams, so zero skills
became competent. This qualified plumbing, not learning.

### Canary 2 — a new diagnostic rejected the attractive loss curve

`v12-canary2-20260722-002841`, seed 20260723, measured the demonstrated actions under their real
future goal and under a blank goal. The difference was `-0.00018086`: essentially no evidence that
the actor used its goal. The run was retained as a failed qualification instead of treating falling
hindsight loss as progress.

### Canary 3 — explicit correct-goal contrast moved the metric

`v12-canary3-20260722-003128` repeated Canary 2's seed and 6,000-action training budget after adding
one declared contrastive term: weight 0.25 and margin 0.10. The correct-goal advantage moved to
`+0.00353084`, best verified progress reached `left_bedroom`, and throughput remained 133.055
actions/s. The margin was not mastered, no skill became competent, and its 512-action terminal
blank-goal exam stayed at power-on.

## Qualification decision

V12 is qualified to begin a longer fixed-budget experiment because the implementation can now
measure and push the exact relationship its hindsight idea depends on. It is not qualified as a
successful Pokémon player. The 48-hour result must still show whether goal sensitivity grows,
whether deterministic skills appear, and whether any of them compose from power-on.

For the architecture, fixed contract, evidence rules, and launch gate, see
[`Version 12: every journey creates its next lesson`](../../docs/version-12-final-self-learner.md).
