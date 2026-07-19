# Experiment protocol

This document defines the claims the project may make and the evidence required to make them. It
exists so that an exciting result cannot quietly change the rules that produced it.

“Must” marks a requirement for an official result. “Should” marks the normal standard; deviations
need an explanation in the experiment record.

## Run classes

Every run receives exactly one primary class before it begins.

| Class | May change the system? | May update a model? | Supports a performance claim? |
| --- | :---: | :---: | :---: |
| Calibration | yes | no | Only the measured harness property |
| Development | yes | yes | No |
| Training | Frozen environment for that run | yes | No; training diagnostics only |
| Evaluation | no | no | Yes, under the frozen protocol |
| Demonstration | no | no | Illustrative only unless sampled by the evaluation rule |

A development run does not become an evaluation because it succeeded. A training episode does not
become a demonstration because its footage looks good. Reclassifying after seeing the outcome
invalidates the claim.

## Observation disclosure

Every experiment must list:

1. what reached the acting policy;
2. what was visible only to the referee;
3. what was available only during development; and
4. what persisted in memory between decisions, attempts, and runs.

The initial track is **instrumented**, not screen-only. A future screen-only track must exclude map
identifiers, coordinates, RAM-derived text, party fields, referee values, and any equivalent signal
from the policy input and reward-facing features.

The observation schema and action schema must carry versions. Adding one field, changing sampling
cadence, changing frame repeat, or altering invalid-action handling creates a new version.

## Authority boundaries

During official evaluation:

- The policy may request only declared actions.
- The executor is the only component that sends controller inputs.
- The policy, planner, skills, memory, and watchdog may not write emulator memory.
- The acting system may not load or save emulator snapshots.
- The referee may read declared scoring fields but may not select or modify actions.
- Development code may not silently rescue, teleport, heal, rewind, or extend a budget.
- External tools, internet access, and human advice are disabled unless the protocol explicitly
  defines them as part of the evaluated configuration.

If an experiment intentionally relaxes one of these boundaries, its title and agent card must make
that difference visible.

## Start-state policy

Training may use private task-specific snapshots to improve sample efficiency. Each snapshot set
must document how states were created and sampled.

Evaluation start states fall into three categories:

| Start | Appropriate claim |
| --- | --- |
| Clean boot | End-to-end progress from a new game |
| Declared fixed snapshot | Skill performance from one exact state |
| Held-out snapshot distribution | Generalization across declared local starts |

A snapshot-start evaluation cannot support a clean-start claim. A state used for training cannot
be described as held out. Development snapshots remain private and are identified by hashes or
anonymous IDs, never committed payloads or local paths.

## Training and evaluation separation

- Evaluation code, prompts, checkpoints, success rules, and budgets are frozen before official
  attempts.
- Checkpoint selection must use a declared rule that does not inspect the final evaluation set.
- Skill evaluations should use held-out initial states or random seeds.
- End-to-end evaluations begin from a clean game unless labeled otherwise.
- Run-specific notebook contents begin empty unless a continual-learning protocol is declared.
- Evaluation attempts do not update model weights, prompts, maps, or persistent memory.
- Every planned attempt is retained, including timeouts, blackouts, crashes, and protocol failures.

If a bug forces a protocol change, close the evaluation set, mark it invalidated or partial, make
the change, and begin a new version. Do not combine attempts from before and after the change as one
unchanged evaluation.

## Success, reward, and milestones

Task success must be a machine-checkable event independent of the training reward. Examples include
crossing a declared doorway, changing to a named map class, delivering an item event, or satisfying
a battle outcome.

Reward is an optimization signal. It may include shaping terms for distance, exploration, survival,
or intermediate milestones. A high return can reveal useful behavior or a reward exploit; it cannot
replace the task-success rule.

Ordered milestones may describe partial progress, but they must be declared before evaluation. The
project may report the furthest milestone reached alongside success rate, not instead of it.

## Budgets and stopping rules

Before evaluation, declare:

- number of attempts;
- action limit per attempt;
- emulator-frame or episode-time limit;
- wall-clock ceiling when relevant;
- model-call, token, and cost ceilings when relevant;
- watchdog stop conditions;
- blackout and crash handling; and
- whether a failed attempt is restarted automatically.

Maxima are ceilings, not goals. Report resources actually used as well as the allowed budget.

## Randomness and repetitions

Record every random seed used by the environment, policy, training library, and sampling process
when those seeds exist. Deterministic runs must say which outputs were compared and which sources of
nondeterminism remain.

For small evaluation sets, show the complete attempt ledger. Do not present a percentage without
its numerator and denominator. When uncertainty intervals would imply more precision than the
sample supports, publish the raw outcomes and describe the limitation plainly.

## Human intervention

An intervention is any human action that changes what happens in a run: controller input, reset,
snapshot load, prompt revision, manual plan, selected route, extended budget, or recovery action.

For every evaluation set, report:

- intervention count;
- intervention type and attempt;
- whether the affected attempt remains in the denominator; and
- the result with and without assisted attempts when both are meaningful.

Observing a run, stopping it under a frozen rule, or narrating later does not count as intervention.
Changing the run because of that observation does.

## Invalid and failed attempts

A failure is a valid attempt that did not meet success: timeout, loop, blackout, or ordinary task
failure. It remains in the result.

An invalid attempt violated the protocol or could not be measured: corrupted trace, wrong ROM,
crash before the declared start, accidental input, or mismatched configuration. Invalid attempts
remain in the ledger with their reason. The protocol must say whether they are replaced; both the
planned and valid attempt counts remain visible.

## Minimum reported metrics

### Outcome

- Task success count and rate
- Furthest declared milestone per attempt
- Median controller actions for successful runs
- Timeouts, blackouts, loop detections, crashes, and invalid attempts
- Human interventions and assisted outcomes

### Resources

- Wall-clock time and aggregate emulator-hours, reported separately
- Training decisions, raw emulator frames, and random seeds
- CPU/GPU class and aggregate compute when material
- Language-model calls, exact model identifier, input/output tokens, latency, and cost

### Identity

- Git commit and dirty/clean worktree state
- ROM fingerprint, never a ROM path
- Emulator, Python, library, observation, action, reward, and agent versions
- Configuration file or normalized configuration hash
- Checkpoint and prompt identifiers

Shaped training return is a diagnostic metric, not proof that a task was solved.

## Comparisons and ablations

Language-model, RL, scripted, human, random, and hybrid configurations use different resources.
Their comparison is an engineering ablation, not automatically a fair contest.

A comparison must share the same referee, task success rule, start-state distribution, and attempt
ledger format. It must disclose differences in information, compute, pretrained knowledge,
demonstrations, memory, tools, and action budget. An ablation should change one declared component
at a time when practical.

Claims must not use “learned from scratch,” “screen-only,” “autonomous,” “no walkthrough,” or “beat
Pokémon” unless the agent card and exact protocol support those words. The
[glossary](glossary.md) defines how this project uses them.

## Representative footage and visuals

Aggregate results come first. A representative run should be chosen by a rule declared before
editing, such as the median successful attempt plus the first failure. A best run may be shown if it
is labeled as best and placed beside the full attempt strip.

Charts must show units, denominators, evaluation markers, and meaningful configuration changes.
Training return and evaluation success belong in separate panels or are labeled separately. See
[Visual storytelling](visual-storytelling.md) for the visual contract.

## Artifact handling

The public repository may contain code, configuration, original diagrams, aggregated metrics,
templates, and explicitly reviewed sanitized traces. It must not contain:

- ROMs, save data, emulator snapshots, or extracted game assets;
- unreviewed gameplay screenshots, recordings, or proprietary audio;
- private checkpoints or datasets that cannot be redistributed;
- API keys, credentials, usernames, or absolute private paths; or
- reports that embed any of the above.

Generated local run reports contain no screenshots by default. They are presentation layers; the
source JSONL trace remains the machine-readable evidence.

## Required record and publication gate

Use the [experiment record template](experiment-template.md) and link the evaluated
[agent card](agent-card-template.md). Before publishing a result:

- freeze and identify the configuration;
- run the privacy, documentation, lint, and relevant test checks;
- preserve every official attempt in the ledger;
- review traces and visuals for private or proprietary material;
- separate observed facts, interpretation, and unknowns; and
- state the smallest claim justified by the evidence.

When in doubt, label a run as development and keep the conclusion narrow. The purpose of this
protocol is not to drain the fun from the project; it is to make the fun parts believable.
