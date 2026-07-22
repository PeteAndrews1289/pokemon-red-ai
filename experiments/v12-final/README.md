# V12 final experiential-learning result

## Result in one sentence

The agent discovered a replay-verified path from power-on through Route 1, but after approximately
9 hours 55 minutes and 8.24 million training actions it retained **zero competent skills**, made
**zero composition attempts**, and did not demonstrate that it had learned to play Pokémon Red.

This is the final declared experiment in the project. It is a negative learning result, not an
unfinished success claim.

## Experimental question

Can one randomly initialized recurrent visual policy learn reusable, goal-sensitive behavior from
its own experience, retain rare discoveries, and connect those behaviors into a journey from clean
power-on—without demonstrations, route instructions, imported weights, save-state starts, online
language-model decisions, or human-selected controller actions?

The ultimate target was the strict Hall of Fame. The nearer diagnostic was deliberately harder
than “did the training system ever see Route 1?”: could a frozen policy repeatedly reproduce each
self-discovered transition, then compose the competent transitions from power-on?

## Frozen identity

| Field | Value |
| --- | --- |
| Run ID | `v12-final-48h-20260722-005136-seed20260722` |
| Source commit | `804ffe810fce5002afb03406f65dfac2ca5be214` |
| Source state at launch | Clean |
| Seed | 20260722 |
| Policy | One recurrent goal-conditioned visual PPO actor |
| Initialization | Random, untrained parameters |
| Start | Direct verified ROM power-on |
| Started | `2026-07-22T04:51:38.691970Z` |
| Last observed status | `2026-07-22T14:46:37.026602Z` |
| Parallel environments | 4 |
| Declared wall-clock ceiling | 48 hours |
| Declared action ceiling | 150,000,000 |
| Actual end | User-requested stop after the result had plateaued |
| Online decision-model calls | 0 |
| Imported actions, demonstrations, or parameters | 0 |

The actor saw processed current and previous pixels, three recent actions, and a self-observed goal
frame. Trainer-only state could grade durable consequences and replay-verify discoveries; it could
not choose a button or enter the actor's observation. The full boundary is documented in
[Version 12](../../docs/version-12-final-self-learner.md).

## Final measurement

Two endpoints are reported because the requested stop interrupted the runner before its normal
finalizer completed:

| Measurement | Last integrity-bound checkpoint | Last observed status |
| --- | ---: | ---: |
| Elapsed time | 35,634.036 s (9h53m54s) | 35,696.136 s (9h54m56s) |
| Training actions | 8,224,768 | 8,236,144 |
| PPO updates | 4,016 | 4,021 |
| Actions per second | — | 230.729 |
| Episodes | 902 | 903 |
| Unique positions | 694 | 694 |
| Deepest verified milestone | Route 1 | Route 1 |
| Verified promotions | 7 | 7 |
| Frozen exam successes / attempts | 55 / 502 | 55 / 502 |
| Competent skills at end | 0 | 0 |
| Composition attempts / successes | 0 / 0 | 0 / 0 |
| Hall-of-Fame completions | 0 | 0 |
| Run output size | — | 64,823,188 bytes |

The additional 11,376 observed actions after the checkpoint are useful operational telemetry, but
they are not represented as a second sealed checkpoint.

## What it discovered

The archive admitted a milestone only after replay verification. Discovery was fast at first:

| Combined action | Time (UTC) | Verified milestone | Stored route depth |
| ---: | --- | --- | ---: |
| 992 | 04:51:43 | The adventure begins | 248 |
| 2,132 | 04:51:56 | Reached the ground floor | 517 |
| 38,972 | 04:55:06 | Stepped outside | 1,526 |
| 39,884 | 04:55:15 | Followed Professor Oak into his lab | 1,754 |
| 43,564 | 04:55:48 | Chose a starter Pokémon | 2,539 |
| 64,432 | 04:57:48 | Finished the first rival battle | 4,811 |
| 378,388 | 05:21:57 | Reached Route 1 | 17,150 |

Route 1 arrived about 30 minutes after launch. The next milestone, Viridian City, never arrived.
The run then spent about 7.86 million more observed actions and more than nine additional hours at
the same verified frontier.

These discoveries show that the training system could find and preserve useful trajectories. They
do **not** show that the current frozen policy could execute those trajectories reliably.

## What it learned—and failed to retain

The run performed real optimization:

- 4,021 PPO updates were observed;
- 64,336 future-frame hindsight lessons generated 3,518,624 trained action examples;
- the actor accumulated 39,328 self-imitation examples and 154 self-imitation updates;
- 2,103 battles started, with 510 classified durable successes and 370 blackouts; and
- 8,909 visual-recovery windows produced 3,491 credited escapes without a trainer-selected button.

But the behavioral authority was the frozen no-update exam, not training activity or loss:

| Self-discovered skill | Exam result | Final 10-attempt window | Final status |
| --- | ---: | ---: | --- |
| The adventure begins | 55 / 160 | 1 / 10 | Not competent; competence lost twice |
| Reached the ground floor | 0 / 342 | 0 / 10 | Not competent |
| Stepped outside | 0 / 0 | — | Ineligible behind prior gate |
| Followed Professor Oak into his lab | 0 / 0 | — | Ineligible behind prior gate |
| Chose a starter Pokémon | 0 / 0 | — | Ineligible behind prior gate |
| Finished the first rival battle | 0 / 0 | — | Ineligible behind prior gate |
| Reached Route 1 | 0 / 0 | — | Ineligible behind prior gate |

The first skill temporarily crossed the 8/10 competence threshold, then fell below it twice as the
same policy continued changing. At the end it could start the game only once in its latest ten
frozen attempts. It never passed the ground-floor skill, so later skill and composition exams
correctly remained locked.

The hindsight diagnostic tells the same story. Qualification Canary 3 had moved the demonstrated
action log-probability advantage for the correct goal to `+0.00353084`. At the final checkpoint it
was effectively zero, while contrast loss sat at its `0.10` margin. The actor had millions of
hindsight examples but was no longer meaningfully preferring the demonstrated actions for the
correct goal over a blank goal.

## Interpretation

There are three different senses of “learning,” and this run separates them:

1. **Did parameters update from experience?** Yes. PPO, hindsight, and self-imitation all changed
   one recurrent policy.
2. **Did training create transient behavior?** Yes. The first frozen skill briefly crossed its
   declared competence threshold.
3. **Did the policy acquire stable, cumulative game competence?** No. Competence was forgotten,
   the second skill passed 0/342 exams, composition never began, and the frontier stopped at Route
   1.

The central failure was therefore not merely insufficient exploration. The system could discover
opening trajectories much faster than it could turn them into durable closed-loop behavior.
Continued updates overwrote a fragile skill, goal conditioning collapsed toward irrelevance, and
the sequential competence gate prevented the archive's seven successes from being mistaken for
one capable player.

## Stop and integrity note

The user chose to end the plateaued attempt before the 48-hour ceiling. The interrupt reached the
persistent terminal wrapper as a broken pipe before the runner wrote its planned terminal
power-on evaluation and final `finished` status. Consequently, the last status file still says
`running` even though the process and dashboard listener are absent.

An exact resume was attempted only to let the built-in finalizer close the record. It failed closed:
the current V12 hindsight-learning state no longer matched the SHA-256 bound into the last
checkpoint. The sealed model, curriculum, and self-skill files still match their checkpoint
hashes; the V12 learning-state file does not. No additional training was accepted and no terminal
evaluation was fabricated.

| Checkpoint-bound artifact | Expected SHA-256 | Current SHA-256 | Result |
| --- | --- | --- | --- |
| PPO model | `c2e17e76e5c24c716d0a9c18eb899c4cfbfd063cbb911d18e4e4cdce6ffbb777` | same | Match |
| Curriculum | `285ea85fc764f0e6f6bcbc476fad3e3ac2de99bbfecb6f6baaf7fd95c3ad3648` | same | Match |
| Self-skill ledger | `278a822d70c2b724e9b92b026db7752ca4474ee8e4f798402fabe93064a60b22` | same | Match |
| V12 hindsight state | `ba6534767f1f4c64f40c064d310be35051d384d44f8b39a3a770c39d0f07f1a7` | `b45db715fd03bca4cf5378d118849b26cbab2418ac30138f0ac0a7398befb13d` | Mismatch; resume refused |

This leaves two explicit limitations:

- there is no clean fixed-policy terminal power-on evaluation artifact; and
- the final 11,376 observed actions are outside the last integrity-bound checkpoint.

The shutdown defect weakens terminal evaluation evidence, but it does not rescue the learning
claim: the last checkpoint already records zero competent skills, zero composition attempts, and
no progress beyond Route 1.

## Claim boundary

This experiment supports the following claims:

- a local M1-class Mac can execute millions of four-environment recurrent PPO actions overnight;
- a randomly initialized agent can discover and replay-verify several early Pokémon Red milestones
  without imported gameplay;
- self-generated hindsight and imitation can create dense training updates; and
- training activity, archive depth, and even temporary competence can coexist with catastrophic
  forgetting and no cumulative skill composition.

It does **not** support claims that the agent understood Pokémon, learned a stable opening policy,
could reach Viridian City on demand, could complete the game, or would inevitably succeed with the
remaining 38 hours.

## Public evidence files

- [`summary.csv`](summary.csv) contains the final aggregate endpoint.
- [`milestones.csv`](milestones.csv) contains the replay-verified discovery timeline.
- [`skill-exams.csv`](skill-exams.csv) contains the complete frozen-exam denominator by skill.

No ROM, save state, emulator snapshot, gameplay capture, private path, or proprietary game asset is
published here.
