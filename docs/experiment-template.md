# Experiment record template

Copy this document for every result that may be discussed publicly. Keep failed, partial, and
inconclusive runs; do not create records only for successes.

Suggested filename: `YYYY-MM-DD-short-question.md`.

---

## Identity

| Field | Value |
| --- | --- |
| Experiment ID | `exp-YYYYMMDD-NNN` |
| Status | planned / running / complete / invalidated |
| Git commit | 40-character commit SHA |
| ROM fingerprint | supported SHA-256, never a path |
| PyBoy version | version |
| Machine class | CPU/GPU family; omit usernames and private paths |
| Operator | person or automation name |
| Started | ISO 8601 timestamp with timezone |
| Finished | ISO 8601 timestamp with timezone |

## Question

Write one falsifiable question. Example: “Does coordinate-cycle detection reduce timeouts on the
bedroom-to-front-door task without reducing success rate?”

## Why this matters

Explain what decision the result will change. If no plausible result would change the plan, this is
probably a demonstration rather than an experiment; label it accordingly.

## Hypothesis

State the expected direction before running anything. Include a reason and the observation that
would change your mind.

## Agent card

Link the completed [agent card](agent-card-template.md) for every evaluated configuration. Record:

- Planner/model and exact version
- Skill or checkpoint identifiers
- Observation schema
- Available controller actions
- Memory available within and between attempts
- Watchdog behavior
- Prompt or policy configuration

## Information boundaries

| Information | Acting policy | Referee only | Development only |
| --- | :---: | :---: | :---: |
| Pixels | yes/no | yes/no | yes/no |
| Map ID and coordinates | yes/no | yes/no | yes/no |
| Party/battle state | yes/no | yes/no | yes/no |
| Reward shaping fields | yes/no | yes/no | yes/no |
| Save-state access | never | never or declared | yes/no |
| Human notes or route hints | yes/no | no | yes/no |

Describe any additional fields. “Instrumented,” “screen-only,” and “pixels plus memory” are
different tracks and must not be collapsed into one label.

## Task and success rule

- **Start state:** exact clean boot or named development snapshot
- **Success event:** machine-checkable condition
- **Failure events:** timeout, blackout, invalid state, crash, or protocol breach
- **Action budget:** maximum controller decisions
- **Time budget:** emulator frames and wall-clock ceiling
- **Intervention rule:** what a person may do, if anything

Freeze these rules before the official attempts.

## Training protocol

Complete this section even when no training occurs.

| Resource | Budget | Used |
| --- | ---: | ---: |
| Environment steps |  |  |
| Emulator frames |  |  |
| Wall-clock time |  |  |
| CPU/GPU hours |  |  |
| Language-model calls |  |  |
| Input/output tokens |  |  |
| Estimated API cost |  |  |
| Human demonstrations |  |  |

Record seeds, curriculum stages, reward terms, snapshot distribution, checkpoint selection rule,
and anything reused from earlier experiments.

## Evaluation protocol

- Number of planned attempts:
- Seeds or initial-state sample:
- Held-out from training: yes/no and how:
- Checkpoint frozen before evaluation: yes/no:
- Prompts/configuration frozen before evaluation: yes/no:
- All attempts retained: yes/no:

## Results

| Metric | Result | Uncertainty or denominator |
| --- | ---: | --- |
| Success rate |  | successes / attempts |
| Median controller actions on success |  | sample count |
| Median emulator frames on success |  | sample count |
| Timeouts |  | count |
| Blackouts |  | count |
| Loop detections |  | count |
| Human interventions |  | count and type |
| Invalid attempts |  | count and reason |

Do not report shaped reward as task success. For small samples, show every outcome rather than a
misleadingly precise percentage.

## Attempt ledger

| Attempt | Seed/start | Outcome | Actions | Frames | Interventions | Trace |
| ---: | --- | --- | ---: | ---: | ---: | --- |
| 1 |  |  |  |  |  |  |

## Visual evidence

Include visuals that answer a question, not decorative dashboards.

- Success/failure strip for every attempt
- Progress-versus-action plot with task landmarks
- Coordinate path or state-transition diagram when navigation is relevant
- Loop excerpt when the watchdog matters
- Training curve with evaluation markers when learning is relevant
- A short representative clip chosen by a rule declared before selection

Keep raw gameplay captures outside Git. Public charts should use aggregated, reviewed data and no
copyrighted assets extracted from the ROM.

## Anomalies and invalidations

List crashes, trace gaps, protocol changes, accidental hints, manual resets, or suspiciously easy
starts. Explain whether each attempt remains valid. Never silently remove an inconvenient run.

## Interpretation

Separate these three statements:

1. **Observed:** what the recorded evidence directly shows.
2. **Inferred:** the most likely explanation.
3. **Unknown:** plausible alternatives the experiment did not distinguish.

## Claim check

Before publication, answer yes or no:

- Does “autonomous” account for every intervention and reset?
- Does “screen-only” exclude all RAM-derived policy inputs and shaping?
- Does “learned” identify demonstrations, curricula, and pretraining?
- Does “from scratch” define what was reset and what knowledge remained?
- Does “beat” name the exact endpoint reached?
- Are failed attempts and resource costs visible?

## Next decision

State the concrete change this result justifies, or say that no change is justified yet.
