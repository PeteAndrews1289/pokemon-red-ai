# The selection × mutation lab

> **Final status, 2026-07-19:** complete. All six lanes reached exactly 128 evaluated children and
> 1,536,000 controller actions, for 9,216,000 actions total in 3,523.886 wall-clock seconds. Every
> lane remained at milestone tier 1, one map, zero warps, zero party members, and zero badges.
> Frontier–broad reached the largest local position count, seven, but no treatment passed the
> predeclared second-map gate. The mechanism matrix is therefore preserved as a useful failed
> qualification, not promoted into a multi-day completion configuration.

| Lane | Game starts / 128 | Archive insertions | Positions | Maps | Result |
| --- | ---: | ---: | ---: | ---: | --- |
| Uniform / Broad | 42 | 7 | 4 | 1 | Failed next-map gate |
| Uniform / Gentle | 56 | 0 | 4 | 1 | Failed next-map gate |
| Uniform / Multiscale | 54 | 5 | 6 | 1 | Failed next-map gate |
| Frontier / Broad | 86 | 9 | 7 | 1 | Failed next-map gate |
| Frontier / Gentle | 114 | 2 | 6 | 1 | Failed next-map gate |
| Frontier / Multiscale | 100 | 6 | 6 | 1 | Failed next-map gate |

Frontier selection retained game start in 300 of 384 children (78.1%), versus 152 of 384 (39.6%)
under uniform selection. Frontier–gentle was the strongest retention condition at 114 of 128
(89.1%), but its two insertions show the tradeoff: it protected the known behavior without turning
that behavior into a new map or party member. The treatment changed inheritance; it did not solve
composition or horizon.

Another failure signal was nearly hidden by the position table. Across all lanes, the median
longest repeated-action streak was roughly 11,798–11,810 actions out of each 12,000-action child.
Observation: most policies became almost constant-action controllers. Hypothesis, not conclusion:
deterministic argmax control may be a deeper bottleneck than either tested selection or mutation
setting.

The final private comparison summary is identified by SHA-256
`a13137e6ecad9a01e43e52c1b35299847583aff8be7b1e4c3309517fc4a8ee2b`. The run paths,
snapshots, ROM, and gameplay captures remain outside Git.

The earlier qualification deliberately tested the machinery, not the hypotheses. It confirmed that all
six processes imported the same 33 elites, used the paired seed and declared treatment, began each
child from power-on, and stopped at an exact lifetime boundary. Broad changed 1,311 parameters in
the paired first child while gentle changed 272, making the intended intervention visible in the
evidence rather than merely present in configuration. The recovery rehearsal also required the
aggregate to re-read all six terminal statuses before declaring the comparison complete; stale or
unequal lane totals now produce an explicit incomplete result.

## Why the experiment changed

The first Evolutionary Explorer pretrial produced one encouraging result and two useful failures.

The encouraging result was small but real: several deterministic neural policies learned a
repeatable way through the title sequence into the game-start state, and descendants of those
policies were much more likely to do the same. This is the first example of a useful accident
becoming inheritable. It is **not** the same as choosing a starter, leaving Pallet Town, or learning
Pokémon in a human sense.

The failures explain why the population stopped there:

1. **Selection was too democratic.** Parents were drawn uniformly from the whole archive. Most
   evaluations therefore descended from policies that had never started the game, even after
   start-capable lineages existed.
2. **Mutation often erased the fragile behavior being selected.** The broad control changes about
   ten percent of the 13,096 parameters. Only one of 23 observed children of the best four-position
   parent retained all four positions.
3. **The diversity grid rewarded difference before usefulness.** Many non-starting policies
   occupied distinct action-profile cells. That kept behavioral variety, as designed, but also
   gave unproductive lineages many chances to reproduce.

These were not reasons to hide the run. They were the reason the completed grid changed one
selection dimension and one mutation dimension. The result showed that a fragile inherited skill
could survive much more often without extending into meaningful gameplay.

## What the 90-minute pretrial actually found

The run ended gracefully after roughly 90 minutes. Every lane wrote a final checkpoint; the
evolutionary archive, genealogy, and narrative were preserved before the processes stopped.

| Lane | Final development-run observation |
| --- | --- |
| Evolutionary Explorer | 2,838,873 actions; 236 evaluated policies; nominal generation 14; 33 archive elites; tier 1; one map; four positions; 71 evaluations reached the game-start state; 38 archive insertions |
| Visually Curious | 2,557,662 actions; six maps observed; maximum party level 27 |
| Outcome-Rewarded | 2,262,634 actions; six maps observed; maximum party level 29 |
| Conventional | 2,223,674 actions; six maps observed; maximum party level 28 |

The three online learners reached the familiar Pallet Town and Route 1 region, then plateaued in a
six-map local loop. Their levels show activity and battle experience, not story completion. The
Evolutionary Explorer did less in-game but answered a different question: its descendants could
inherit a deterministic title-sequence behavior. Neither result establishes a trained Pokémon
player.

Two post-run comparisons shaped the branch:

- children of parents that had reached the game-start state did so about 79% of the time, versus
  about 4.7% for children of non-starting parents—roughly a 17-fold association in this one
  development run;
- about 64% of child evaluations still used a non-starting parent because archive-wide uniform
  selection did not favor the newly useful frontier.

Those percentages are retrospective diagnostics, not a held-out success rate. They motivated the
next test; they do not prove that the effect will repeat under another seed.

### Frozen evidence anchors

The private run payload remains outside Git. These content hashes identify the exact local
artifacts used to choose the next design without revealing a ROM, save state, or private path.

| Artifact | SHA-256 |
| --- | --- |
| Final evolutionary archive checkpoint | `a786b8f4087dfdbd882778b9777c9dde1e99143e0bd94e0c4bdc14f570092eda` |
| Genealogy | `efba7dc5d9c127425caa74df948097a4e8e8f76bb7722b2bb02746ba0bf2b182` |
| Final narrative snapshot | `915406e43832df933491e18d1582b255c383e44545b0b038e6f14a422966666c` |

## The 2 × 3 question that was tested

The completed lab asked:

> Is progress limited mainly by choosing the wrong parents, by mutations that are too destructive,
> or by an interaction between the two?

Two parent-selection rules form the rows. Three mutation rules form the columns.

| | **Broad control** | **Gentle** | **Multiscale** |
| --- | --- | --- | --- |
| **Uniform selection** | **U-B:** reproduce the old mechanism | **U-G:** test retention without selection pressure | **U-M:** mix refinement with rare leaps |
| **Frontier selection** | **F-B:** test selection pressure alone | **F-G:** favor progress and protect it | **F-M:** favor progress while preserving escape mutations |

This is a factorial engineering pretrial, not six different agents competing for one trophy. The
useful result may be an interaction: gentle mutation could help only when useful parents are chosen
often enough, while broad mutation could remain valuable when the population is stuck.

## The two selection rules

### Uniform archive selection

Choose every parent uniformly from the occupied archive. This is the existing control. It protects
diversity, but an action-profile niche that never started the game receives the same reproductive
chance as the most advanced lineage.

Audience version: **every surviving family gets the same number of lottery tickets.**

### Frontier selection

For 80% of births:

1. find elites at the current highest milestone tier;
2. sample three candidates from that frontier;
3. choose the best candidate by the existing lexicographic fitness vector.

For the remaining 20%, choose from the whole archive. That diversity reserve prevents selection
from permanently silencing an unusual lineage just because it is not currently the most advanced.

Audience version: **most children come from families at the frontier, but one birth in five still
comes from the wider gene pool.**

“Frontier” does not mean that the agent sees a waypoint. The acting policy still sees only pixels
and its previous action. A sealed referee measures the result after the lifetime and decides which
genomes may reproduce.

## The three mutation rules

The percentages below refer to independent parameter changes in a 13,096-parameter recurrent
policy. All perturbations are zero-mean Gaussian noise and all profile choices are recorded.

| Profile | Rule | Purpose |
| --- | --- | --- |
| **Broad control** | Existing rule: mutate each parameter with probability `0.10` at sigma `0.05`; on 5% of births use sigma `0.20` with the same parameter probability | Reproduce the mechanism that generated the source archive |
| **Gentle** | Mutate each parameter with probability `0.02` at sigma `0.01` | Ask whether small edits preserve the fragile start behavior long enough to refine it |
| **Multiscale** | 80% micro (`p=0.01`, sigma `0.02`); 15% broad (`p=0.10`, sigma `0.05`); 5% macro (`p=0.10`, sigma `0.20`) | Spend most births refining, while retaining occasional wider searches |

Audience version: the broad control **rewrites many letters**, gentle mutation **corrects a few
characters**, and multiscale mutation usually edits carefully but occasionally **rewrites a
sentence**.

## What stays equal

Each lane receives:

- the same frozen archive of 33 source elites;
- 128 child evaluations;
- exactly 12,000 controller actions per child;
- exactly **1,536,000 controller actions total**;
- the same ROM fingerprint, emulator version, recurrent topology, pixel observation, action set,
  timing, archive capacity, progress referee, and fitness ordering;
- a declared deterministic random seed and complete parent/mutation genealogy;
- a clean power-on Pokémon state for every child.

The six lanes ran concurrently on the same Mac. Controller actions were the primary scientific
budget because wall-clock speed varied with processor contention; both action-normalized and
wall-clock views were retained.

### What “same frozen archive” does and does not mean

The imported archive contains neural-network parameters and their recorded metadata. It does not
drop a child into Pallet Town or restore the source run's emulator state. Every new child must
reproduce its behavior from power-on with a reset recurrent memory.

This made the lab an **engineering fork**: all lanes inherited a population discovered in an
earlier pretrial so the selection and mutation mechanisms could be compared quickly. No mechanism
passed the progress gate, so no fresh-founder winner was selected. Clean-start neuroevolution is
preserved as the historical control; the completion track moved to explicitly labeled checkpoint
search.

## Measurements that mattered

The dashboard and final report were designed to show more than the largest score.

| Measurement | What it reveals |
| --- | --- |
| Children reaching game start | Whether the known fragile behavior survives |
| First directed warp / second map | Whether a lineage adds real navigation progress |
| Starter, Pokédex, species, party, and badge milestones | Whether progress moves beyond the title and local movement |
| Parent tier distribution | Whether frontier selection actually changes reproductive attention |
| Parent → child retention rate | Whether mutation preserves an ancestral capability |
| Added-position and added-warp rate | Whether retention also permits improvement |
| Archive insertions and replacements | Whether a lane creates useful behavioral variety |
| Maximum and median lineage depth | Whether improvements form sustained family lines |
| Mutation channel and changed-parameter count | Which scale produced each surviving descendant |
| Actions and wall time to first milestone | Whether a method learns sooner, not merely eventually |
| Crashes, retries, checkpoint time, CPU, and disk | Whether the experiment is operationally credible |

The first target is deliberately modest: retain the title-sequence behavior and produce the first
directed warp or second-map descendant. Reaching a starter is a stretch result. A higher generation
number alone does not count as progress; a batch counter can rise even when no useful lineage
deepens.

## Visual and narrative evidence

The 2 × 3 grid is also the episode's central visual. Each cell showed the latest frame, actions,
children evaluated, source of the current parent, mutation channel, milestone tier, archive size,
and a small lineage trace. Shared charts should compare all six lanes at the same action count.

The recorder freezes all six `latest.png` images together every ten minutes, stores their action
counts and SHA-256 hashes, and preserves the corresponding dashboard HTML. Separately, each lane
captures the first observed game-start, map, warp, starter, battle, Pokédex, species, blackout, and
badge frame at the exact triggering action. These files live with private run artifacts on the SSD,
not in Git, and give the final edit real transitions rather than reconstructed screenshots.

The lab can be recovered after an orchestrator interruption only with the identical manifest:
source commit, clean/dirty state, ROM fingerprint, archive hash, lane matrix, seed, and all budgets
must match. Completed lanes resume as no-op terminal checks while unfinished lanes continue from
their own checkpoints. A final comparison is valid only when every lane reports the exact action
and completed-child ceilings with `action_limit`.

A clear video sequence is:

1. **The first inheritance:** show a parent that starts the game and several descendants repeating
   it. Explain that one lifetime is fixed; learning happens only when successful policies reproduce.
2. **The family-tree bottleneck:** zoom out and reveal that most children still came from families
   that never started.
3. **The mutation tragedy:** show a useful parent beside descendants that lost its behavior.
4. **The fork:** turn the two suspected causes into the 2 × 3 grid.
5. **The race with equal fuel:** advance all lanes by controller actions, not a misleading reward
   total or unequal wall time.
6. **The result, including failure:** identify which mechanism retained, extended, or destroyed the
   behavior, and preserve empty branches as evidence.
7. **The reset:** reveal that there was no winner. Better retention still produced no next map, so
   the story turns from inheriting weights to remembering verified game states.

Suggested episode question: **“Evolution finally remembered how to press Start. Could it remember
that skill long enough to learn anything else?”**

## Claim boundary

After this lab, the strongest permissible statements are:

- “Frontier selection retained the source archive's start behavior more often under this declared
  budget.”
- “Frontier–gentle had the best retention and little archive novelty.”
- “No lane added a directed warp, second map, or party member.”

Do **not** say:

- “The AI learned Pokémon Red” because reaching game start is far below game competence;
- “the best algorithm won” because one archive, one machine, and one seed family are not a general
  benchmark;
- “six independent fresh runs” because all lanes share an imported source population;
- “one model learned over 90 minutes” because each child was fixed and learning occurred through
  population-level selection;
- “the pixels-only policy knew the milestone” because only the sealed referee saw semantic state.

## Decision taken after the lab

Every lane reached its equal action ceiling, but none satisfied the required progress criteria:

1. retains game-start behavior across descendants;
2. adds a directed warp, map, or other milestone;
3. produces more than one surviving useful lineage;
4. remains deterministic, recoverable, and bounded;
5. wins on action-normalized evidence rather than one edited highlight.

Because no lane improved, the result narrowed the problem. The project did not invent a winner from
seven local positions. It preserved the matrix and moved to a checkpoint-assisted expedition with
strict information labels and complete power-on replay.

## Research background

- [MAP-Elites](https://arxiv.org/abs/1504.04909) introduced an archive of high-performing,
  behaviorally diverse solutions rather than one global champion.
- [Novelty Search with Local Competition](https://doi.org/10.1145/2001576.2001606) combines
  behavioral novelty with competition among nearby behaviors, a useful direction if archive-wide
  diversity keeps overwhelming progress.
- [Safe Mutations for Deep and Recurrent Neural Networks](https://arxiv.org/abs/1712.06563) asks how
  parameter changes can create meaningful behavioral variation without destroying a network's
  function.
- [Go-Explore](https://www.nature.com/articles/s41586-020-03157-9) demonstrates the value of
  preserving rare progress and returning to promising states in hard-exploration problems. This
  six-lane lab imported **genomes**, not emulator states; checkpoint-assisted expeditions are the
  separately labeled successor track.
