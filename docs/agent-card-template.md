# Agent card template

An agent card describes exactly what was allowed to act. Complete one whenever a planner, learned
policy, prompt, observation schema, or memory rule changes materially.

## Identity

| Field | Value |
| --- | --- |
| Agent ID | short stable name |
| Version | semantic version or Git commit |
| Role | baseline / planner / skill / hybrid |
| Training status | untrained / training / frozen |
| Intended task | bounded task name |

## Plain-English description

Explain the system in three sentences for someone who has never trained a model:

1. What information does it receive?
2. How does it choose an action?
3. What, if anything, can it remember or learn?

## Components

| Component | Implementation | Frozen for evaluation? |
| --- | --- | :---: |
| High-level planner |  |  |
| Navigation skill |  |  |
| Battle skill |  |  |
| Memory |  |  |
| Watchdog |  |  |
| Executor |  |  |

Use “none” rather than leaving an ambiguous blank.

## Observation contract

List every input with shape, range, update frequency, and source. Separate policy-visible fields
from referee-only measurements. Link the versioned observation schema.

## Action contract

List every action the agent can request, its duration, and any action masking. State whether the
agent operates every frame, every controller press, or only at higher-level decision boundaries.

## Learning history

- Algorithm and implementation:
- Random seeds:
- Training environments and start-state distribution:
- Environment steps and emulator frames:
- Demonstrations, labels, walkthroughs, or handcrafted routes:
- Pretrained models or external knowledge:
- Checkpoint-selection rule:

If no training occurred, write that explicitly.

For an evolutionary policy also record:

- genome schema, parameter count, and genome hash;
- parent genome, generation, mutation seed, and mutation magnitude;
- archive descriptors, cell, and elite-replacement reason;
- candidate population, workers, evaluated descendants, and emulator-hours;
- whether the result is clean-start or checkpoint-assisted;
- complete ancestral replay result and lineage hash, when applicable.

## Memory and reset rules

Describe what persists:

- During one controller action
- During one attempt
- Between attempts in one evaluation
- Between training and evaluation
- Across separate experiments

## Safety and authority boundaries

Confirm whether the agent can:

- Load or save emulator snapshots
- Write emulator memory
- Read referee-only fields
- Change its own budget or success rule
- Request human help
- Access the internet or external tools during evaluation

Any “yes” needs a protocol-level justification.

## Known limitations

List expected failure modes before evaluation: repeated inputs, text boxes, map transitions,
partial observability, long-horizon credit assignment, battle menus, or planner hallucinations.

## Evaluation history

Link experiment records rather than copying only the best score.

| Experiment | Task | Attempts | Successes | Notes |
| --- | --- | ---: | ---: | --- |
|  |  |  |  |  |

## Change history

Document why each new version exists and whether its results remain comparable to older versions.
