# The story of this project

> **Editorial update:** Pure Monkey has finished its role as the opening control. It could produce
> accidents but could not remember them. The next protagonist is a population: successful pixel
> policies have descendants, failed branches go extinct, and several kinds of survivor remain
> visible. The design and its strict claims are defined in
> [Evolutionary Explorer](neuroevolution.md).

## The question

Can an AI learn to make meaningful progress through Pokémon Red—and can we explain what it is
doing clearly enough that somebody else can tell the difference between learning, luck, scripting,
and a carefully edited success?

That second half is the real project.

It would be easy to record a run, cut around the failures, and announce that an AI played a game.
It is much more interesting to keep the failures, define the rules before the attempt, show what the
agent was allowed to see, and build a trail of evidence from its first useless button presses to its
first reliable skill. This repository is meant to become that trail.

For the next act, the central character is not one agent but a family tree. Each child lives with a
fixed neural policy. Selection decides which behaviors receive descendants. The audience can watch
useful accidents become inherited tendencies, dominant families stall, rare lineages open new
parts of the game, and old champions go extinct. Planner and hybrid systems remain possible later
comparisons rather than claims about the current implementation.

## Where the project honestly stands

**Online Q-learning pretrials have run. Neuroevolution has not started.**

Phase 0 built the measuring instrument: a reproducible emulator harness that can start the exact
same game, issue timed controller inputs, observe a small and disclosed slice of state, restore an
in-memory snapshot, and record what happened without publishing private or proprietary data.

That is less glamorous than a victory montage, but it is the foundation that makes every later
claim meaningful. Before asking whether an agent improved, we need to know that two runs began
under the same conditions. Before comparing two approaches, we need one referee. Before making a
training graph, we need a definition of success that cannot quietly change after seeing the result.

The measuring-instrument milestone remains important. From a clean boot, the harness can
reproducibly move through the introduction, choose the built-in names RED and BLUE, and stop at the
first playable moment in the bedroom. It can then move exactly one tile and restore the untouched
starting state. No policy decided those actions and nothing was learned; this is a deterministic
test sequence used to prove that the laboratory works.

| Question | Current answer |
| --- | --- |
| Has an AI learned to play Pokémon Red? | No. |
| Has online reinforcement learning begun? | Yes, in development pretrials; no frozen task evaluation has been claimed. |
| Does Pure Monkey learn? | No; it is now a preserved and retired random baseline. |
| Has neuroevolution begun? | No; the successor is designed at E0 but not implemented. |
| Can the software boot and control the game reproducibly? | Yes. |
| Can it verify the intended game revision? | Yes. |
| Can it record controller actions and selected state without leaking the ROM path? | Yes. |
| Can it reach the first playable state twice with identical results? | Yes. |
| Is the current test sequence an autonomous playthrough? | No; it is test infrastructure. |
| What comes next? | Deterministic genome inference, mutation, MAP-Elites, genealogy, and bounded population pretrials. |

Keeping this table current is part of the project. A small true claim is more valuable than a large
ambiguous one.

## Why Pokémon Red?

Pokémon Red is complicated enough to produce an interesting long-form story and constrained
enough to study one layer at a time.

The game mixes several kinds of problem:

- navigating rooms, towns, routes, doors, and map transitions;
- reading menus and choosing actions with delayed consequences;
- battling under resource constraints;
- remembering places, people, items, and unfinished goals;
- recovering when a plan fails or an action produces an unexpected result;
- working toward objectives that may be many minutes apart.

Its controller vocabulary is tiny, but the space of possible histories is enormous. Pressing one
of a few buttons is easy. Knowing *why this button, here, now* is hard.

The early game also provides a natural ladder of increasingly demanding goals. Leaving the
bedroom proves basic movement. Reaching Professor Oak requires navigation and event handling.
Choosing a starter and surviving the rival battle introduce menus and combat. Delivering Oak's
Parcel requires a multi-map round trip. Defeating Brock requires navigation, preparation, battle
strategy, and persistence. Each goal can become an episode and an evaluation rather than one
unverifiable claim that the agent can “play Pokémon.”

## The project promise

This is a passion project, but it should behave like a careful experiment. The storytelling rules
are therefore also engineering rules.

### Show the conditions

Every reported run should say what the acting system could observe, which information was reserved
for scoring, where the run began, what software and checkpoint were used, how much computation was
allowed, and whether a person intervened. “The agent saw the screen” and “the referee read a memory
address” are different facts and should appear as different facts.

### Show attempts, not just highlights

An official evaluation is a set of attempts declared in advance, not the prettiest clip found after
an afternoon of experimentation. Report the denominator: three successes out of twenty attempts is
not “it did it,” and one spectacular failure can be as informative as one success.

### Separate practice from the exam

Training runs are where rewards, starting states, and designs change. Evaluation runs use frozen
code, prompts, checkpoints, budgets, and success criteria. Development snapshots can make practice
faster, but an official clean-start claim must actually begin at a clean start.

### Count human help

A reset, corrected menu choice, hand-written route, loaded state, changed prompt, or manually
unstuck character may all be reasonable development tools. They are not invisible. Each should be
counted and described whenever it affects a reported result.

### Let failure remain part of the record

Loops, timeouts, blackouts, reward exploits, wrong turns, and confused plans are not debris to
remove from the story. They are the plot. The audience should see the system's failure vocabulary
grow more sophisticated: from random motion, to locally competent but aimless behavior, to a good
plan poorly executed, to a rare edge case in an otherwise reliable skill.

## The cast of the system

The architecture is easier to follow if each component has one job and one kind of responsibility.
These are engineering boundaries, not claims that the parts are people.

### The world: game and emulator

Pokémon Red supplies the rules and consequences. PyBoy runs the game. The emulator harness owns
button timing, screenshots, frame counting, and private in-memory snapshots. The acting system
cannot alter game memory or request a teleport.

### The senses: observation adapter

The future observation adapter will decide what information crosses from the game into an agent.
It is not built yet. Phase 0 instead has a six-field read-only instrumentation snapshot for harness
validation and future referee logic: whether the game has started, an anonymous map number, tile
coordinates, party size, and battle state. Phase 1 must explicitly choose which of those fields—if
any—become policy inputs alongside pixels or visible text.

### The strategist: planner

The planned language-model component will choose bounded goals such as “find an exit from this
room” or “return to a known doorway.” It will not press a direction every video frame. Its value is
reasoning over goals, discoveries, and failures—not twitch control.

### The practiced hands: skills

Learned policies will handle repeatable execution problems such as walking toward a target,
crossing a doorway, navigating a menu, or selecting a battle action. Reinforcement learning is one
candidate for training these skills. A skill should have a clear input, action budget, completion
condition, and failure result.

### The notebook: memory

Memory will record discoveries and outcomes: which doorway led where, which plan failed, and which
facts have supporting evidence. It should not become a hidden walkthrough. Independent evaluation
runs begin with the memory declared by the experiment protocol.

### The skeptic: watchdog

The watchdog looks for repeated screens, coordinate cycles, depleted budgets, and other signs that
the system is no longer making progress. It may ask for a new plan or end an attempt. It may not
silently fix the run.

### The official: referee

The referee decides whether a task succeeded and records measurements. It can use disclosed
read-only signals that the acting policy does not receive. This separation prevents the scorer's
answer key from leaking into the student's test paper.

### The documentarian: recorder

The recorder turns an attempt into evidence: events, metrics, hashes, selected screenshots, and
video-ready summaries. It is responsible for making both progress and uncertainty visible.

## The story arc

The project has a useful progression from certainty about the laboratory to uncertainty about
intelligence.

### Prologue — Build the measuring instrument

The first victory is not in the game. It is making the same experiment happen twice.

Questions answered in this phase include: Do we have the intended ROM revision? Does one controller
action mean the same number of frames each time? Can a snapshot be restored faithfully? Can the
first playable state be recognized without mistaking leftover memory values for gameplay? Can the
public trace remain useful without containing the owner's private file paths?

The dramatic tension is trust. By the end of the prologue, the audience should believe the later
graphs represent real, comparable runs.

### Interlude — Randomness reaches its limit

Pure Monkey is the “monkeys with typewriters” idea made literal. It can stumble into a starter,
Route 1, or a battle because Pokémon remembers what happened. The actor remembers nothing. A lucky
run does not make the next button even slightly less random.

That is a conclusion rather than an embarrassment. The random baseline establishes the floor and
creates the next question: **what if luck could reproduce?** Retiring Monkey on screen gives the
project a visible moment where evidence changes the plan.

### Chapter 1 — Give accidents descendants

Introduce genomes as inheritable sets of neural-network parameters. One fixed child plays; the
sealed referee measures what happened; diverse champions produce mutated children. Show the family
tree before showing a reward curve.

The conflict is not simply “score goes up.” A family that farms Route 1 may dominate a naive genetic
algorithm. MAP-Elites preserves different champions—map explorers, story-progress lineages,
collectors, and battle-experienced branches—so one local optimum does not become the entire species.

The honest endpoint is a qualified population engine and the first inherited improvement, not a
full-game promise.

### Chapter 2 — Learn to leave home

The first agent-facing task should be deliberately small: leave the bedroom, then leave the house.
A random policy establishes how hard the task is by accident. A human demonstration establishes a
practical action count. The first learned policy establishes whether a reward signal and observation
are sufficient.

This chapter can reveal classic learning problems in miniature: walking into walls, oscillating
between two tiles, opening menus unintentionally, discovering a reward shortcut, and reaching a
door without crossing it.

### Chapter 3 — Deliver Oak's Parcel

The parcel is the first meaningful quest. It requires the agent to sequence events, survive map
transitions, remember a return destination, and distinguish temporary movement from actual task
progress. This is the first strong test of the planner/skill division.

Success should mean completing a predefined event from a clean start within a fixed action budget,
not merely reaching Viridian City or touching a promising coordinate.

### Chapter 4 — Defeat Brock

Brock turns the project from navigation into preparation. A successful system must manage a party,
select battle actions, respond to losses, and coordinate short-term skills with a longer-term goal.
It is also a natural point for the first serious comparison among language-model-only,
reinforcement-learning-only, and hybrid systems.

### Later chapters — Generalize or merely memorize?

Once the agent can complete rehearsed tasks, the harder questions begin. Does a skill survive a
different starting tile? Can the planner recover from an unfamiliar detour? Does stored knowledge
help more than it traps the agent in old assumptions? Can a policy trained on one map transfer to
another? A full-game attempt is meaningful only after these narrower questions have honest answers.

## Making progress legible

Every milestone should produce both a written account and a compact visual record. The two formats
serve different purposes: visuals make patterns immediate; text supplies conditions, caveats, and
causes.

### The milestone card

Place a one-screen summary at the beginning of every update:

```text
MILESTONE        Leave the bedroom
STATUS           Training / Evaluation / Complete / Blocked
ACTING SYSTEM    PPO navigation skill, checkpoint 0042
OBSERVATION      84x84 pixels + previous action
START            Fixed clean-bedroom snapshot (training only)
SUCCESS          Cross the bedroom exit within 300 actions
RESULT           17 / 20 evaluation attempts
HUMAN HELP       0 interventions during evaluation
VERSION          Git commit, configuration, random seeds
```

The card prevents a successful clip from outrunning its context. Use plain words first and precise
technical identifiers second.

### The run strip

Represent every official attempt as one equal-width mark, ordered by run number. Use a consistent,
color-blind-safe palette and never encode outcome by color alone.

```text
01 ✓  02 × timeout  03 ✓  04 ↻ loop  05 × blackout  ...  20 ✓
```

This is the visual antidote to cherry-picking. Clicking or expanding a mark can reveal the seed,
action count, duration, terminal reason, and trace identifier.

### The progress curve

For training, plot the median and a spread across a window or several seeds, not only the single
highest return. Show evaluation success on a separate axis or panel. Label environment steps and
emulator-hours; wall-clock time belongs in the caption. Draw vertical annotations when rewards,
observations, or algorithms change, because curves on opposite sides of such a change are not one
continuous experiment.

Training reward answers “is the policy optimizing the scoring signal?” Evaluation success answers
“does it complete the declared task?” The latter is the claim viewers care about.

### The route trace

On an original, abstract tile grid—not an extracted game map—draw the agent's visited coordinates
as a path. Mark the start, goal region, map transitions, stalls, and repeated cycles. Multiple runs
can be shown as occupancy density rather than an unreadable bundle of lines.

This visual can explain a behavior more honestly than a highlight reel: a policy may reach the exit
often while spending half its budget circling furniture.

### The decision timeline

For a hybrid agent, place planner decisions above the timeline and controller actions below it.
Show when a skill began, ended, timed out, or triggered replanning. This makes the boundary between
“the language model decided” and “the trained policy executed” visible.

### The failure atlas

Maintain a small gallery of recurring failure modes using original diagrams or tightly framed,
rights-reviewed footage when appropriate. Give each failure a stable name, first-seen version,
frequency, suspected cause, and current mitigation. Examples might include `DOORWAY_OSCILLATION`,
`MENU_DRIFT`, `FALSE_PROGRESS`, and `STALE_PLAN`.

The atlas turns embarrassment into continuity. A viewer can watch an old failure disappear, mutate,
or return under new conditions.

### The narrated example

Pair aggregate results with one uncut or minimally accelerated representative attempt selected by a
rule declared in advance—for example, the median successful run and the first failed run. Overlay
only information available in the saved trace. Label reconstructed or reenacted sequences clearly.

## A repeatable update format

Each devlog entry, release note, or video episode can follow the same seven beats:

1. **Question:** What did we want to learn?
2. **Rules:** What could the agent see, and what counted as success?
3. **Build:** What changed since the previous experiment?
4. **Prediction:** What did we expect before running it?
5. **Evidence:** What happened across all declared attempts?
6. **Failure:** What went wrong, including the most instructive example?
7. **Next bet:** What single change will the next experiment test?

The prediction is especially important. Writing it before the result helps distinguish explanation
from hindsight.

## Language and claims

Words such as “understands,” “learned,” and “autonomous” compress many assumptions. They can be used
in an informal narrative, but the nearby evidence should make their operational meaning clear.

Prefer:

- “completed 17 of 20 held-out attempts” over “mastered the room”;
- “received pixels plus tile coordinates” over “learned from vision”;
- “used no intervention during evaluation” over “fully autonomous”;
- “trained for two million emulator steps” over “trained for a day”;
- “reached Brock from the declared start state” over “beat Pokémon”;
- “the planner proposed this subgoal” over “the AI knew what to do.”

Reserve “screen-only” for an acting policy that received no emulator-memory fields, OCR text, map
identifiers, or privileged state. Reserve “from scratch” for a protocol that precisely says which
pretrained components, demonstrations, maps, prompts, and prior knowledge were absent. Reserve
“no walkthrough” for a system whose prompts, memory, reward, and code do not encode a route.

## Visual and editorial identity

The project should look like a laboratory notebook with the warmth of a childhood adventure, not an
imitation of the game's commercial artwork.

- Use original diagrams, charts, typography, and simple geometric icons.
- Give each system component one stable symbol and label; do not rely on character likenesses.
- Use a color-blind-safe palette with redundant shapes, labels, or line styles.
- Preserve aspect ratios and avoid decorative pixel art copied from the ROM.
- Do not place ROMs, extracted sprites, maps, music, fonts, or other proprietary assets in the
  repository.
- If gameplay footage is used in a video, keep it purposeful and transformative, add commentary,
  and make a separate rights decision for the publication platform. Repository documentation
  should work without that footage.
- Mark simulated, reconstructed, sped-up, and illustrative visuals on screen.

An original recurring visual can be a “lab bench”: World → Senses → Decision → Action, with the
Referee and Recorder outside the control loop. As the project advances, light up only the components
actually present in that experiment. In Phase 0, the decision boxes remain visibly empty. That
absence tells the truth at a glance.

## What success would mean

The satisfying ending is not necessarily a full-game completion. A good outcome would be a body of
work in which somebody can inspect an attempt, understand the system's information and constraints,
reproduce the measurement, and see why the next design follows from the previous failure.

If the hybrid system eventually defeats Brock, that will be a memorable scene. The deeper result
will be everything underneath it: the failed routes, the learning curves, the action budgets, the
component boundaries, the unedited attempts, and the honest record of how much help it needed.

The central story is not that a machine pressed the right buttons. It is that an opaque-looking
achievement became a sequence of visible, testable steps.
