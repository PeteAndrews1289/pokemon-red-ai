# Plain-language glossary

This glossary explains the terms used by the project for readers and viewers who do not work with
machine learning or emulators. Definitions describe how the project uses a word; a term may have a
broader meaning elsewhere.

## Quick mental model

The **game** is the world. The **emulator** runs that world. An **observation** is the slice of the
world shown to the **agent**. A **policy** chooses a controller **action** from that observation. A
**reward** is a training signal, while a **referee** independently decides whether the declared task
was actually completed. A **recorder** preserves the evidence.

Training is practice: the system may change. Evaluation is the exam: the system and rules are
frozen. A good result reports both what happened and the conditions under which it happened.

## A

### Action

One choice sent toward the game, such as Up, Down, Left, Right, A, B, Start, Select, or waiting. In
this project a controller action also specifies how many emulator frames the button stays held and
how many frames it remains released afterward.

An action is not necessarily one visible step. A direction might hit a wall, scroll a menu, or
continue movement depending on the game's current state.

### Action budget

The maximum number of controller actions an attempt may use. A budget prevents an agent from being
declared successful merely because it was allowed to wander forever. Reaching the goal after the
budget is a timeout, not a success for that protocol.

### Action space

The complete set of choices available to an agent. One experiment might permit the eight Game Boy
buttons plus waiting; another might offer higher-level choices such as “walk to adjacent tile.” The
action space must be disclosed because a high-level action can contain substantial hand-written
assistance.

### Agent

The system that observes the game and chooses what to do. “Agent” can refer to a reinforcement-
learning policy, a language model, or a hybrid of several components. The emulator harness and
referee are infrastructure around the agent, not part of its intelligence.

### Aggregate metric

A summary calculated across many attempts, such as success rate or median action count. Aggregate
metrics reduce the temptation to make a claim from one unusually good or bad run.

### Anonymous map identifier

A number used internally by the game to distinguish locations. The initial observation exposes the
number but does not translate it into a human-readable location name. This tells the agent that the
area changed without directly supplying a semantic map label.

### Attempt

One bounded try at a task, from a declared starting condition until success, failure, timeout, or
another terminal condition. An evaluation contains a predeclared number of attempts.

### Autonomy / autonomous

A claim about how much a system operated without human action. It is not all-or-nothing: a run can
have no intervention while still using hand-written rewards, pretrained models, fixed prompts, or
previously built maps. This project prefers the measurable phrase “zero interventions during the
evaluation attempts” and separately lists other supplied knowledge.

## B

### Baseline

A reference result used to understand whether a new method adds value. Planned baselines include a
random policy, a human demonstration, a language-model-only system, and a reinforcement-learning-
only system. A baseline is not necessarily weak; it is the comparison point.

### Battle state

A small read-only value indicating whether the player is outside battle, in a wild battle, in a
trainer battle, or in a loss transition. Version 1 can expose this field, but not the opponent's
identity, health, moves, or recommended action.

### Blackout

The game's consequence for losing all usable party Pokémon. For experiment reporting, a blackout
is a terminal reason or failure event, not merely a low reward.

### Bootstrap sequence

The fixed controller sequence used in Phase 0 to move from a clean boot through the introduction to
the first playable bedroom state. It is a test of the harness. It is **not** a policy, demonstration
of intelligence, or learned behavior.

## C

### Checkpoint

A saved set of learned model parameters at a particular point in training. Checkpoints allow the
same policy version to be evaluated repeatedly. They are different from emulator snapshots, which
save the game and emulator rather than the learned model.

### Cherry-picking

Showing the most impressive attempt while hiding how many failures were tried. The project counters
this with predeclared evaluations and run strips that represent every attempt.

### Clean boot / clean start

An attempt that begins from the game's normal initial startup rather than a convenient development
snapshot. The exact meaning must be stated: a clean boot could still use a fixed introduction
sequence unless the acting agent is required to handle that sequence itself.

### Configuration

The complete set of settings used for an experiment: observations, actions, rewards, budgets,
software versions, model parameters, prompts, and more. A saved configuration helps another person
understand and reproduce the conditions.

### Controller boundary

A moment after a button has been released and before the next is pressed. Snapshots and observations
are most reliable at this neutral point because no half-held input carries into the next action.

### Curriculum

A sequence of training tasks that becomes progressively harder—for example, first crossing a nearby
doorway, then leaving a room, then navigating several maps. A curriculum is supplied structure and
must not be confused with an agent discovering the entire problem unaided.

## D

### Deterministic

Producing the same relevant result when repeated under the same recorded conditions. The Phase 0
bootstrap is deterministic because two clean runs end with matching logical frames, named state,
screen pixels, and private snapshot payloads. Determinism in one test does not guarantee that every
future training operation is deterministic.

### Development run

An attempt used while code, rewards, prompts, starting states, or other rules may still change.
Development runs are for diagnosis and improvement. Their results are not frozen evaluation
evidence.

### Demonstration

A sequence of actions supplied by a human or another controller. Demonstrations can establish a
baseline or teach a policy. If training uses them, they are a real source of prior knowledge and
must be disclosed.

## E

### Emulator

Software that reproduces the behavior of another system—in this case, the Game Boy hardware needed
to run Pokémon Red. PyBoy is the emulator used by this project. The emulator is the environment in
which experiments run; it is not the AI.

### Emulator frame

One update of the emulated machine. Controller holds and releases are measured in frames so their
timing is explicit. A displayed video frame and an emulator frame are not always the same thing,
especially when training is accelerated.

### Emulator-hour

One hour of simulated game time. If four emulators each run one simulated hour in parallel, that is
four emulator-hours but perhaps only one hour of wall-clock time. Reporting both prevents parallel
compute from disappearing from the story.

### Environment

The world with which an agent interacts. In reinforcement learning, the environment receives an
action, advances the game, returns an observation and reward, and says whether the attempt ended.
Here it includes the emulator plus carefully designed interfaces around it.

### Episode

In reinforcement learning, one attempt from reset to a terminal condition. This use is unrelated to
a YouTube episode; documentation should say “training episode” or “video episode” when confusion is
possible.

### Evaluation

The exam. The policy, prompts, checkpoint, environment, success criteria, attempt count, and budgets
are frozen before official evaluation runs. Evaluation estimates performance under those declared
conditions; it does not make a universal claim about every possible game situation.

### Evaluation set

The starting states, seeds, or scenarios reserved for measuring performance rather than improving
the model. A held-out set helps test whether the system learned a reusable behavior instead of
memorizing its practice cases.

### Executor

The component that converts decisions into valid controller inputs. It enforces timing and action
rules. In the planned hybrid design, both the planner and learned skills must go through the
executor; neither can directly manipulate the emulator.

## F

### Failure atlas

A documented collection of recurring failure modes, each with evidence, frequency, a suspected
cause, and a proposed next test. Stable names such as `DOORWAY_OSCILLATION` make it possible to track
whether a problem actually disappears across versions.

### Fingerprint / hash

A short, fixed-size value calculated from file contents. If one byte changes, the fingerprint will
usually change dramatically. The project uses cryptographic hashes to verify the supported ROM and
the integrity of private snapshots. A hash identifies contents; it does not reveal the original ROM
or prove that a copy was obtained lawfully.

### Frame skip / action repeat

Applying one selected action across several emulator frames before asking the policy for another
decision. This can make training faster and decisions more meaningful, but it can also hide precise
timing. The exact repeat must be part of the configuration.

### From scratch

A strong and often ambiguous claim that a system began without relevant prior knowledge. A
pretrained language model, human demonstration, encoded map, shaped reward, or curriculum may all
provide knowledge. This project avoids “from scratch” unless the protocol defines exactly what was
and was not supplied.

### Frozen

Not changed during official evaluation. A frozen checkpoint alone is not enough; prompts, wrappers,
budgets, success rules, and observation processing also matter.

## G

### Game state

The information that completely describes the game's current situation. Full state is much larger
than the small observation shown to the agent. Screen pixels, controller history, timers, menus, map
data, party data, and many hidden variables can all be part of game state.

### Generalization

Succeeding in conditions that were not identical to training, such as a different starting tile or
unseen random seed. Generalization is stronger evidence of a reusable skill than repeating one
memorized action sequence.

### Git commit

A named snapshot of the project's source files and documentation. Recording the commit identifier
ties an experiment to the exact code that produced it.

### Gymnasium

A common Python interface for reinforcement-learning environments. It standardizes operations such
as resetting an environment and taking one step. Using the interface does not itself create or train
an AI; it makes algorithms easier to connect to the game harness.

## H

### Headless

Running the emulator without opening a normal game window. Headless mode is useful for automated
tests and fast training. Screens can still be captured from the emulated display.

### Held-out

Reserved from training or tuning and used only for evaluation. Held-out starting states and seeds
reduce—but do not eliminate—the risk that performance comes from memorization.

### Hold / release timing

The number of frames a button is held down followed by the number of frames all buttons remain
released. The default Phase 0 action holds for eight frames and releases for sixteen. Explicit
timing helps one action behave consistently at map, text, and menu boundaries.

### Human intervention

A person changing the course of an attempt after it begins—for example, pressing a button, loading
a state, correcting a prompt, resetting an agent, or manually moving it out of a loop. Development
interventions are often useful. Evaluation reports must count and describe them.

### Hybrid agent

A system that combines different decision-makers. The planned hybrid uses a language model for
bounded goals and learned policies for execution, with memory and a loop watchdog around them. A
hybrid result should identify which component chose each level of action.

## I

### Instrumented

An experiment in which the software reads declared internal game values in addition to, or instead
of, visible pixels. The current harness is instrumented because it can read six named memory
fields, although no acting policy consumes them yet. A future experiment is instrumented when its
declared policy or referee uses such fields. This is not inherently improper; the important
requirement is disclosure. It must not be described as screen-only.

### Integrity check

A test that data still matches the value recorded when it was created. Before loading an in-memory
snapshot, the harness checks its payload hash, ROM hash, and emulator version so incompatible or
changed state is rejected.

## J

### JSONL trace

A text log format with one JSON object per line. Each line can represent an event such as a button
action, observation, snapshot, or terminal result. JSONL is both machine-readable and inspectable
with ordinary text tools. Public-safe traces omit the ROM path, ROM contents, secrets, and raw save
states.

## L

### Language model / LLM

A model trained on text to predict and generate language. In the planned system, a language model
will propose bounded goals and reason over the agent's notebook. It has not yet been integrated.
Using a pretrained language model means the full system will not have learned everything solely
from game interactions.

### Learned skill

A bounded behavior produced by training rather than a fixed action script—for example, navigating
toward a nearby doorway. A convincing skill evaluation states its inputs, action space, training
budget, held-out cases, and success condition.

### Logical frame

The harness's reproducible frame counter. It advances as the emulator runs and rewinds when an
in-memory snapshot is restored, even though the emulator's own lifetime counter may not rewind.

### Loop

Repeated behavior with little or no progress, such as alternating between two tiles or reopening the
same menu. A loop definition must specify its evidence and window; merely disliking an agent's route
does not prove a loop.

### Loop watchdog

A planned component that detects repeated screens, coordinate cycles, or exhausted budgets. It may
request replanning or terminate an official attempt. It may not teleport the player, choose the
correct action, or secretly reload a snapshot.

## M

### Map transition

A change from one game map to another, often caused by crossing a doorway, stair, route boundary, or
other connection. A transition is a useful objective because it is more robust than rewarding one
exact tile alone.

### Median

The middle value after results are sorted. The median is less distorted than the mean by one very
long or unusually short attempt. Reports should still include success count and spread rather than
using the median alone.

### Memory (agent memory)

Information deliberately retained across decisions, such as discovered connections, recent
failures, or evidence-backed notes. This differs from the Game Boy's RAM and from model parameters.
The experiment protocol must say whether memory is empty, pretrained, or carried across runs.

### Metric

A measured number used to describe an experiment, such as success rate, actions used, loop count,
or emulator-hours. A metric is informative only alongside its definition and population.

### Milestone

A bounded project goal with an explicit success test. “Deliver Oak's Parcel” is a milestone;
“become good at Pokémon” is not measurable enough to be one.

### Model

A learned mathematical system that maps inputs to outputs. Depending on context, this may mean a
reinforcement-learning policy or a language model. The emulator, fixed bootstrap sequence, and
hand-written referee are software but are not learned models.

## O

### Observation

The information presented to the acting agent at one decision point. It might contain pixels, text,
coordinates, party summaries, or recent actions. Observation is deliberately smaller than full game
state. Every experiment must list its fields.

### Observation adapter

The component that turns raw emulator information into the explicit, versioned observation seen by
an agent. It is where pixels may be resized, values may be masked, and unavailable state may be
represented. Changing the adapter can change task difficulty.

### Official run

An attempt included in a predeclared evaluation. It uses frozen rules and counts whether it succeeds
or fails. A debugging run that happens to succeed cannot be relabeled official afterward.

### Overfitting

Performing well on practice situations while failing on meaningfully different ones. A navigation
policy that memorizes a fixed sequence from one exact tile may overfit the bedroom rather than learn
a transferable navigation skill.

## P

### Party count

The number of Pokémon currently in the player's party. Version 1 exposes only this number, not
species, levels, moves, health, or items.

### Planner

The proposed high-level decision component. It chooses bounded goals or strategies at a slower
timescale than controller actions. A planner may request “explore until a map transition”; a skill
then handles the individual inputs.

### Policy

The rule a reinforcement-learning agent uses to choose an action from an observation. A neural
network policy has learned parameters, while a random or hand-written policy can use the same
environment without learning.

### PPO

Proximal Policy Optimization, a reinforcement-learning algorithm planned as the first learned
baseline. In simple terms, it repeatedly collects experience and adjusts a policy while limiting
how abruptly the policy changes. Choosing PPO does not guarantee learning or good sample
efficiency; it is a starting point to test.

### Pretrained

Trained on data before this project or before a particular experiment. A general-purpose language
model is pretrained even if it has never interacted with this emulator. Pretraining is a source of
capability and must be disclosed when discussing “learning.”

### Privileged information

Information useful for scoring or debugging that the acting policy is not allowed to receive. For
example, the referee may inspect a task-completion flag. Keeping privileged information outside the
policy prevents the answer key from entering the observation.

## R

### Random policy

A baseline that selects among allowed actions randomly according to a declared distribution. It
measures how often a task can be solved by accident under the same action budget. Random does not
necessarily mean uniform; the distribution must be stated.

### RAM / working memory

The Game Boy's temporary memory while the game runs. It stores information such as current map and
coordinates. The project reads a few documented bytes through a read-only interface. It provides no
agent-facing method for writing memory.

### Read-only

Permitted to inspect a value but not change it. Read-only RAM observation is different from memory
editing, teleporting, or setting event flags. It can still make a task easier than pixel-only play,
which is why every field is disclosed.

### Recorder

The component that saves a structured account of what happened: actions, selected observations,
metrics, hashes, and artifact references. It should support analysis without exposing the ROM,
private paths, secrets, or raw save states.

### Referee

The independent component that decides whether the declared goal was reached and records outcomes.
The referee can use disclosed privileged state, but that state must not flow into the policy unless
it is also part of the declared observation.

### Reinforcement learning / RL

A training approach in which an agent acts in an environment and adjusts its policy using reward
signals. The developer does not specify the correct button at every step, but still makes important
choices about observations, actions, rewards, start states, algorithm, and curriculum. In this
project, RL training has not yet begun.

### Reproducible

Documented well enough that the same code, data identity, settings, and procedure can be run again
and meaningfully compared. Reproducibility does not require every result to be bit-for-bit identical
if the experiment is stochastic; it requires capturing randomness and reporting the resulting
distribution honestly.

### Reset

Ending an attempt and returning the environment to its declared starting condition. Training may
reset from a private development snapshot for speed. A clean-start evaluation uses the starting
procedure stated in its protocol.

### Reward

A numeric training signal intended to make some outcomes more desirable than others. A policy tries
to increase its accumulated reward. Reward is not the same as actual success; an agent can exploit
an imperfect reward without completing the intended task.

### Reward shaping

Adding intermediate rewards for behaviors believed to help, such as approaching a doorway or
entering a new map. Shaping can speed learning but also encode developer knowledge or create
loopholes. Each shaped term and its scale should be documented.

### ROM

A game cartridge image used by an emulator. The project verifies one exact Pokémon Red revision but
does not distribute it. Users must supply their own copy outside the repository and are responsible
for complying with the laws and terms that apply to them.

### Run strip

A compact visual with one equally weighted mark for every official attempt. Symbols distinguish
success, timeout, loop, blackout, and other terminal reasons. It shows the denominator that a
highlight clip hides.

## S

### Sample efficiency

How much useful behavior a method learns from a given amount of interaction. A sample-efficient
agent reaches a performance level with fewer emulator steps. Wall-clock speed alone does not measure
sample efficiency.

### Save file

The game's persistent cartridge data, comparable to what a physical cartridge stores between play
sessions. It is private and excluded from the repository. A save file differs from a full emulator
snapshot.

### Save state / emulator snapshot

A captured emulator state that can restore the game to an exact moment. The Phase 0 harness keeps
snapshots in memory rather than writing them into the project. Snapshots can accelerate training but
must be disclosed because they determine the starting situation.

### Screen-only

An observation setting in which the acting policy receives only visible screen pixels, possibly
with a declared history or transformation, and no emulator-memory values, OCR transcription, map
identifier, coordinates, or hidden game variables. Phase 0 has no policy observation yet; its
harness instrumentation means the overall setup should not be advertised as a screen-only agent.

### Seed / random seed

A number used to initialize a pseudorandom process. Recording seeds helps repeat sampling, training,
or evaluation choices. One seed is not a representative evaluation; multiple seeds reveal how
sensitive a result is to luck.

### Snapshot integrity hash

A fingerprint of a private in-memory snapshot. Comparing the hash can verify that the payload did
not change. The hash can be logged; the snapshot payload itself remains private.

### Stable Baselines3

A Python library that implements reinforcement-learning algorithms, including PPO. It is a planned
training dependency, not an agent or a result by itself.

### State hash / screen hash

A fingerprint used to compare named state or screen pixels without publishing all underlying data.
Matching hashes are strong evidence that two deterministic tests produced the same bytes under the
same encoding. The encoding and software version still matter.

### Success criterion

The exact condition that ends an attempt as successful. It should be frozen before evaluation and
tested by the referee. “Cross into the next map before 300 actions” is clearer than “looks like it
left the room.”

### Success rate

The number of successful attempts divided by all official attempts, reported with both numerator
and denominator—for example, 17/20, or 85%. A rate without the number of attempts can be misleading.

## T

### Terminal condition

An event that ends an attempt: success, timeout, blackout, detected loop, invalid state, or another
predeclared reason. Recording terminal reasons explains *how* attempts failed.

### Tile coordinate

The player's position on the game's movement grid, expressed as X and Y. Coordinates help measure
movement but do not inherently reveal where a goal is, what a location means, or how to reach it.

### Timeout

An attempt that exhausts its action, frame, or time budget without reaching another terminal
condition. Timeouts count in the evaluation denominator.

### Trace

The chronological record of events in a run. A trace can answer which actions were requested, when
state changed, and why an attempt ended. Traces are evidence, but they require a documented schema
and must be sanitized before publication.

### Training

Practice during which a model's parameters change in response to experience or data. Running a
fixed script, booting the game, or calibrating controller timing is not training. This project's
Phase 0 contains no model training.

### Training return

The sum of rewards collected in a training episode. It helps diagnose whether a policy is optimizing
the supplied signal. It is not proof that the intended task was completed, so evaluation success is
reported separately.

## V

### Versioned observation

An observation schema with an explicit version number. Adding a field can make a task easier and
invalidate direct comparison with older experiments, so schema changes create a new version rather
than silently altering the existing one.

## W

### Wall-clock time

The elapsed time experienced by the person running the experiment. It differs from emulator-hours
when the emulator is accelerated or several workers run in parallel. Both should be reported.

### Watchdog

See **Loop watchdog**. It monitors progress and enforces limits but does not secretly choose correct
game actions.

### Wrapper / harness

Software placed around the emulator to provide consistent inputs, observations, snapshots, checks,
and logs. Phase 0 built this measuring instrument. A harness can make learning possible, but it is
not itself a trained player.

## Terms deliberately kept separate

Some words sound similar but support different claims:

| Term A | Term B | Difference |
| --- | --- | --- |
| Model checkpoint | Emulator snapshot | Learned parameters versus a captured game moment |
| Training return | Task success | Optimizing a reward versus completing the declared goal |
| Agent observation | Referee state | Information used to act versus information used only to score |
| Development run | Official evaluation | Changeable practice versus a frozen exam |
| Wall-clock hour | Emulator-hour | Human elapsed time versus aggregate simulated game time |
| Read-only memory | Memory editing | Inspecting declared state versus changing the game |
| Clean start | Development snapshot | Normal startup procedure versus restored convenient state |
| Fixed test sequence | Learned policy | Hand-written verification actions versus behavior produced by training |
| One successful run | Success rate | An example versus performance across a declared set |
| Screen pixels | Screen-only protocol | One input type versus an exclusive observation claim |

When a result feels impressive, these distinctions are most important—not least important.
