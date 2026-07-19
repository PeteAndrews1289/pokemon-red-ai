# Overnight comparison analysis

This checklist turns the first Monkey and Archivist runs into a reproducible development report and
video evidence package. It is deliberately written before the final outcomes are known.

## Preserve the evidence first

Do not edit, rename, or move an active run directory. When both processes finish:

1. Confirm each `status.json` says `finished` or `failed` rather than stale `running`.
2. Record the stop reason, total actions, elapsed time, frames, visual cells, archive size, restores,
   source commit, implementation digest, and seed.
3. Check that both checkpoint generations can be opened before relying on resumability claims.
4. Keep ROMs, screenshots, console logs, and checkpoint payloads under Git-ignored `runs/`.
5. Create any public summary from reviewed aggregate values; never commit a run directory wholesale.

An unexpected process failure is part of the result. Preserve its failure status and console log
before attempting a resume.

## Compare like with like

The two algorithms have different throughput. The Monkey does not save or restore archive states,
so it will normally press more buttons per wall-clock second. Produce two comparisons.

### Action-matched comparison

Choose the largest controller-action count reached by both valid runs. Interpolate or use the nearest
earlier recorded status point for each arm.

Report:

- definite new visual cells;
- definite novelty per 1,000 actions;
- representative discovery screens available before that action count;
- action distribution; and
- for Archivist, retained cells, restores, and maximum reproducible action depth.

This comparison asks whether memory changes discovery efficiency.

### Time-matched comparison

Choose the largest elapsed wall time reached by both valid runs and use the nearest earlier status
point.

Report the same fields plus actions per second. This comparison asks what each method produces from
the same overnight waiting budget.

Keep these views separate. A faster algorithm and a more action-efficient algorithm are different
findings.

## Quantitative evidence table

Populate this table from traces only after both runs stop:

| Field | Monkey | Archivist |
| --- | ---: | ---: |
| Run class | Development | Development |
| Continuous playthrough | Yes | No |
| Snapshot-assisted | No | Yes |
| Seed | Recorded in manifest | Recorded in manifest |
| Wall time used | Pending completed run | Pending completed run |
| Controller actions | Pending completed run | Pending completed run |
| Emulated frames | Pending completed run | Pending completed run |
| Definite new visual cells | Pending completed run | Pending completed run |
| Not-definitely-new observations | Pending completed run | Pending completed run |
| Archive cells | Not used | Pending completed run |
| Archive restores | 0 | Pending completed run |
| Stop reason | Pending completed run | Pending completed run |
| Output size | Pending completed run | Pending completed run |

“Definite” matters because the bounded novelty filter can have false positives. It can miss a truly
new cell by calling it already seen; it cannot create a false first-visit score.

## Qualitative screen review

Review every saved milestone screen in chronological order. For this development analysis, assign
one exploratory post-hoc label:

- boot/logo animation;
- title/menu;
- dialogue;
- name-entry variation;
- transition/blank frame;
- overworld or interior navigation;
- battle interface;
- repeated visual exploit;
- unknown; or
- other, with an explanation.

These labels are human interpretation and were not available during the run. Display that fact on
the screen atlas. Do not force ambiguous images into a higher-progress category.

For each arm, select:

- the earliest screen in each observed category;
- the three clearest examples of misleading novelty;
- the three most surprising discoveries;
- the final screen; and
- at least one visually boring failure.

The reel is a bounded sample, not every screen encountered. Say so in the report.

## Curve review

Plot or extract these views from recorded status events:

1. definite new visual cells versus controller actions;
2. definite new visual cells versus wall time;
3. rolling novelty per 1,000 actions;
4. Archivist archive size versus actions;
5. Archivist restores versus actions; and
6. action share by button.

Look for slope changes and connect them to nearby milestone screens. A flat curve may indicate a
loop or exhausted region. A sudden steep curve may indicate a meaningful transition, animated
sequence, or interface exploit. The curve alone cannot distinguish them.

## Interpretation decision tree

### If the Monkey has more visual cells

First control for its higher action count. If it still leads when action-matched, inspect whether
continuous animation or interface variation dominates its reel. The conclusion may be that the
archive's selection strategy is too conservative—not that memory is intrinsically harmful.

### If the Archivist has more visual cells

Inspect whether the gain comes from new screen categories or finer variants within one interface.
Report restore cost and wall-clock throughput beside the advantage.

### If both become trapped in the same interface

This is strong evidence for the next experiment: random local action selection is the bottleneck.
Use the archive data to design a Curious policy, but do not train on hand-selected “good” screens
without disclosing that additional supervision.

### If one reaches a recognizable game milestone

Describe the screen-level observation precisely. Unless a sealed referee verifies the underlying
event, prefer “displayed the bedroom” or “displayed a battle interface” over “completed the intro”
or “entered battle.” Never feed the post-hoc label back into the still-running arm.

### If a run crashes or hits a safety limit

Classify the harness failure separately from ordinary exploration failure. A low-disk or output cap
is an expected safety stop; an emulator exception is a development defect. Do not quietly replace
the attempt in a comparison.

## Minimum morning report

The first report should contain:

1. one-sentence result with no semantic overclaim;
2. experimental contract and exact source commit;
3. complete run ledger;
4. action-matched and time-matched tables;
5. two discovery curves;
6. side-by-side action histograms;
7. a labeled screen atlas;
8. expected and observed failure modes;
9. what cannot yet be concluded; and
10. the next experiment chosen from the evidence.

## Candidate claims, ordered from weakest to strongest

Use the strongest sentence the evidence actually supports:

1. “Both bounded processes completed without a harness failure.”
2. “The agents encountered different coarse visual-cell distributions.”
3. “At equal actions, one arm produced more definite first-visit visual cells.”
4. “The Archivist repeatedly returned to and branched from retained visual discoveries.”
5. “Post-hoc review found more distinct screen categories in one arm's bounded reel.”

None of these statements alone supports “the agent understood Pokémon,” “learned the objective,” or
“made more semantic game progress.” Those require a separate frozen evaluation and sealed referee.

## Publication boundary

Safe public artifacts include reviewed Markdown summaries, aggregate tables, generated charts, and
small screenshots or video excerpts whose use has been deliberately reviewed. Unsafe default
artifacts include ROMs, emulator states, checkpoints, raw save data, private filesystem paths,
credentials, and unreviewed traces or console logs.

The public report should link the exact Git commit and disclose any invalidated or resumed segment.
