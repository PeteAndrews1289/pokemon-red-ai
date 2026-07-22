# The story of this project

> **Editorial update:** Pure Monkey could produce accidents but could not remember them. A neural
> population then inherited one narrow accident—starting the game—but six controlled selection and
> mutation treatments still failed to leave the first map. The next protagonist is an expedition
> that can remember verified stepping stones without pretending those checkpoints are one learned
> policy. Its Q0 machinery worked, and one of two Q1 seeds assembled and replayed a 419-action route
> outside. The failed companion seed and nearly one million verification actions keep that moment
> from becoming a false victory. Archive v2 has now made that memory bounded and survived both a
> graceful interruption and a deliberate hard crash. The next question is whether the verified
> accident can teach a visual model. Its destination and strict claims are defined in the
> [Hall of Fame completion program](completion-program.md).

> **Latest turn:** the project drifted from observing learning into supplying a new lesson whenever
> the agent failed. V6 made the problem measurable: its retained policy improved from 0/10 to 5/10
> on the first connection but failed the 8/10 gate after one million actions. V7 now removes the
> inherited brain, later checkpoints, route hints, and demonstrations.
> A random power-on agent may train only on actions it discovered and replay-verified itself. Its
> first tiny canary started the game and reached the ground floor without a supplied route.

> **Newest turn:** V7 restored the right source of knowledge but gave one network two competing
> jobs: wander noisily for PPO and memorize every action in a lucky verified trace. V8 kept the
> then-live V7 run unchanged and later locked it as a historical denominator, gave discovery to
> four orange Explorers, and gave
> retention to a separate blue Student. Replay—not the host—decides which loops can be removed.
> Training loss stops at an exam door: only frozen attempts can mark a skill competent. The first
> real-ROM canary qualified that mechanism on the trivial `game_started` outcome. The final
> committed canary got farther: its Explorer followed Oak into the lab and left four verified
> lessons behind. But the exam door stayed shut—seven frozen attempts, seven failures. That
> contrast qualified V8's measurement. A longer final run then reached Route 1, grew the library
> from four skills to seven, and lifted action fit from 13.78% to 53.08%, but only one of 47 frozen
> exams succeeded. Zero skills crossed the competence gate. The point survives more data:
> discovery, compression, and even much better fit are visible progress, but none may masquerade as
> reliable behavior. The corrected story waits 16,384 Explorer actions, freezes the next Student
> version, and collects exactly one grade; 8/10 must span ten checkpoints.

> **Current turn:** V8's Student had studied only successful recorded stories. During a frozen
> attempt, its own first wrong action could put it on a screen the story never contained. Version 9
> asks whether that exposure bias—not merely too few cloning updates—explains both the 0/7 canary
> and final 1/47 result. The
> run's own lineage is normalized into exact consecutive edges. The canonical Student receives a
> BC warm start, then acts closed loop from disclosed near-target snapshots; the start moves
> backward only after a hard practice gate. A Student rollout can write a new lesson only if it
> reaches the target and exact replay verifies it. Every failure remains on screen but is never
> imitated. A future recurrent PPO recovery lever is designed to trigger automatically after a
> declared no-success condition, yet it stays behind glass—unimplemented, disabled, and unclaimed
> for the initial qualification. The closed-loop path itself is now engineering-checked: exact
> target identity, terminal-reason counts, bounded rotating success replay, graph hash binding,
> checkpoint rollback, and the two-window 27/30 gate are implemented. The first real-ROM attempt
> then failed usefully: its 180-second campaign overran to 248.801 seconds while immediate success
> reports replaced richer periodic dashboard diagnostics. The project kept the failure, fixed
> cancellation and report
> merging, and reran. The authoritative canary stopped itself at 144.082 seconds against 144.0,
> recorded every one of 22 practice outcomes, retained 16 exact successes, and exposed bounded
> aggregation—but its frozen exam door still read 0/3. V9's mechanism, observability, and wall-time
> boundary are qualified. Learning is not.

> **Architectural turn:** V9 closed intentionally after 2h52m39.143s and 1,431,556 Explorer actions so the
> matched-configuration V10 successor could begin. It reached Route 1 and 68.5919% Student training
> accuracy, yet passed only 4/87 frozen exams, produced zero competent skills, and never composed
> them. The `8h` run-name suffix was a ceiling, not elapsed time. V10 then tested bounded recovery
> before reset and closed after 4,503.282 seconds and 534,924 actions. It finished at Route 1 with
> 3/32 frozen exams and zero competent skills. The mechanism recovered locally, but the learned
> journey still did not compose. V11 therefore changes the unit of reasoning: a disclosed
> structured-state planner, map navigator, persistent memory, and controller specialists now share
> one assisted hierarchy. C1 failed on path resolution, C2 on MCP authorization, and C3 was rejected
> when initialized bedroom RAM produced a false story state. C4 qualified the opening referee with
> 136 actions, 70 language-model calls, empirical RIGHT-movement proof, and objective 1/84. A fresh
> unbounded clean-start run is active, with no completion guarantee and no Hall-of-Fame claim.

## The question

Can an AI learn to make meaningful progress through Pokémon Red—and can we explain what it is
doing clearly enough that somebody else can tell the difference between learning, luck, scripting,
and a carefully edited success?

That second half is the real project.

It would be easy to record a run, cut around the failures, and announce that an AI played a game.
It is much more interesting to keep the failures, define the rules before the attempt, show what the
agent was allowed to see, and build a trail of evidence from its first useless button presses to its
first reliable skill. This repository is meant to become that trail.

The investigation now has two lanes that must not be blended in the edit. The **assisted
hierarchical lane** asks whether an openly aided planner–memory–navigator–specialist system can hold
together an entire adventure from power-on. The **frozen learned-policy lane** asks whether the
self-generated experience from this project can eventually be distilled into fixed learned
components that pass declared exams without the planner's explicit help. V11 is active in the first
lane. V7–V10 are preserved evidence in the second. An assisted completion would be a real result,
but it would not retroactively prove that a neural policy learned Pokémon Red from pixels.

The family tree remains Act II: it showed that useful accidents can become inherited tendencies,
then exposed the clean-start horizon. Act III asks whether evolution can preserve a state, the
exact actions that reached it, and a verifiable ancestry, then explore outward. Every checkpoint
restore is disclosed as training assistance. A later frozen visual model must make the complete
journey without those restores before the project says one model learned the game.

## Where the project honestly stands

**The checkpoint expedition has replayed named transitions. V8's committed canary built four
self-generated lessons through Oak's lab and failed 0/7 frozen exams; its later final run built
seven through Route 1, improved offline fit, but finished at 1/47 with zero competent skills. V9's
closed-loop self-correction mechanics now pass the 288-check engineering suite, and its corrected
real-ROM canary qualifies mechanism, observability, and wall-time control. The final V9 campaign
reached Route 1 but passed only 4/87 frozen exams, with zero competent skills and no composition.
The matched-configuration V10 campaign closed at 4,503.282 seconds and 534,924 actions with 3/32
frozen exams and zero competent skills. V11's fourth canary qualified its opening control/referee
boundary; a fresh unbounded clean-start run is active. No Hall-of-Fame result exists.**

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
| Has online reinforcement learning begun? | Yes. Frozen attempts have been recorded, but no current self-taught lane has demonstrated a competent multi-skill policy. |
| Does Pure Monkey learn? | No; it is now a preserved and retired random baseline. |
| Has neuroevolution begun? | Yes. It inherited game-start behavior, but all six follow-up lanes failed the second-map gate. |
| Has the checkpoint expedition left the house? | Once in two bounded random-emitter seeds; the lineage replayed, but the Q1 robustness gate failed. |
| Can its checkpoint memory survive a crash? | Yes in the staged Archive v2 gate; a hard-crash twin recovered and matched the uninterrupted deterministic terminal state. |
| Can the software boot and control the game reproducibly? | Yes. |
| Can it verify the intended game revision? | Yes. |
| Can it record controller actions and selected state without leaking the ROM path? | Yes. |
| Can it reach the first playable state twice with identical results? | Yes. |
| Is the current test sequence an autonomous playthrough? | No; it is test infrastructure. |
| Can one model execute the lucky route? | Yes once: Stage 0 fit 419/419 labels, survived frozen reload, and selected the exact 419 actions from clean power-on to `left_home`. This is route memorization, not a robust skill. |
| Has checkpoint-assisted PPO completed Oak's errand? | Yes. V5.1 replay-verified the Pokédex by action 402,320, but this is an assisted training lineage rather than one clean-start policy. |
| Did V5.2 teach one model to compose those steps? | Not demonstrated. It verified Oak's Lab exit and Route 1, but its replay gate tested stored actions rather than the current policy's complete behavior. |
| What happened to V7? | It remains a path-free, hash-matched historical denominator under its original shared-policy, raw-trace rules. It is not an active runner and is not rewritten as part of V11. |
| What does V8 change? | It separates PPO exploration from a recurrent Student, replay-distills only self-generated trajectories, and collects one deterministic grade per Student checkpoint. The clean 3,584-action canary reached Oak's lab and built four lessons but passed 0/7 frozen exams; it remains the qualification record. |
| Why did V8 close? | Its final longer run spent 784,386 Explorer actions and 2,513 Student updates, reached Route 1, built seven lessons, and raised fit to 53.0817%, yet passed only 1/47 frozen exams. Zero skills became competent and no composition ran. More cloning improved fit without establishing reliable behavior. |
| What does V9 change? | It tests exposure bias with exact consecutive edges, BC warm start, reverse closed-loop Student practice, and success-only replay-verified aggregation. Exact-target checking, full terminal counts, graph/checkpoint binding, rotating bounded replay, and the 27/30×2 gate are implemented. The actor still sees only pixels, its action history, and a self-generated visual goal. |
| Is PPO already rescuing V9? | No. Same-boundary recurrent PPO is a deferred automatic-escalation design for a future no-success rung. It is not implemented or active in initial qualification. |
| What happened in the first V9 canary? | It reached `Stepped outside` and 19/22 exact practice outcomes, but synchronous work overran a 180-second budget to 248.801 seconds. Immediate success reports also replaced richer periodic diagnostics. Manual STOP exposed both defects; it did not cause the reporting bug. |
| What did the corrected V9 canary prove? | Commit `e1ea199` fixed cancellation/report merging. The replacement honored 144.0 seconds within 0.082 seconds, ran 22 fully classified practice attempts, retained 16 verified successes, and exposed success-only replay. It qualifies mechanism, observability, and wall-time—not competence. |
| Has V9 learned a skill? | Not demonstrated. The corrected canary passed 0/3 frozen exams, with zero competent skills. The current suite passes 276 non-integration plus 12 integration checks. |
| How did V9 close? | The user intentionally stopped `parallel-ppo-v9-self-correcting-8h-20260721-seed20260809` at 2h52m39.143s: 1,431,556 actions, Route 1, 68.5919% fit, 4/87 frozen exams, zero competent skills, and no composition. |
| How did V10 close? | After 4,503.282 seconds and 534,924 actions: Route 1, 3/32 frozen exams, zero competent skills, and no composition. Recovery was measurable; long-horizon learned competence was not. |
| What did the V11 canaries establish? | C1 failed on path resolution; C2 failed on MCP authorization; C3 was operational but rejected for false initialized state; C4 qualified the opening referee with 136 actions, 70 language-model calls, real RIGHT-movement proof, and objective 1/84. |
| What is running now? | A fresh unbounded V11 assisted-hierarchy attempt from clean power-on and empty run memory. It has no planned wall-clock cutoff, but can still stop on failure, safety limits, operator action, or strict success. |
| Does “unbounded” mean it will beat the game? | No. It changes a scheduling limit, not the probability of success. Hall of Fame requires strict terminal evidence; no such result is claimed. |
| What comes next? | Audit whether V11 can sustain verified objective progress. If it completes, preserve the guided journey as an assisted result and as possible training data for the separate frozen learned-policy lane. |

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

Each implemented actor adapter decides what information crosses from the game into that agent.
Pixels-only learners receive rendered frames; the conventional learner receives its separately
declared coarse state; the Q0/Q1 suffix emitter receives no observation at all. V11 explicitly
adopts a structured-state assisted actor boundary, including the declared objective and map tools.
That broader interface is why its result belongs in a separate lane from the frozen pixel-policy
experiments.

### The strategist: planner

V11's language-model component chooses bounded goals such as “find an exit from this room” or
“return to a known doorway.” It delegates ordinary inputs to tools and specialists instead of
pressing a direction every video frame. C4 qualified this division only at the opening: 70 calls
produced 136 controller actions and a real RIGHT-movement proof. Later-game planning remains an
active hypothesis, not a demonstrated capability.

### The practiced hands: skills

V11 currently uses declared controller specialists for repeatable execution problems such as
walking toward a target, crossing a doorway, navigating a menu, or selecting a battle action. They
are assisted components, not evidence that a neural policy learned those behaviors. The separate
learned-policy lane may later replace them one at a time, with a clear input, action budget,
completion condition, and frozen failure denominator for each replacement.

### The notebook: memory

V11 memory records discoveries and outcomes: which doorway led where, which plan failed, and which
facts have supporting evidence. The active attempt began with empty run memory. This notebook is an
explicit part of the assisted system and must not be mistaken for learned model weights or a hidden
walkthrough.

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

### Method turn — Split the discoverer from the student

V7 creates the cleanest version of the new-player question so far: random weights, power-on, and no
imported answer. Its unresolved tension is visual. One network is asked to be an orange scribble
that explores and a blue line that remembers. A verified route may be real and still be a terrible
lesson because it contains every loop taken before luck finally worked.

V8 makes that tension the plot. Show the raw route as a knot. Let the emulator reject one unsafe
deletion and approve another. Then let a separate recurrent Student study only the surviving
self-generated sequence. The loss curve may rise or fall, but it cannot resolve the scene. Freeze
one Student checkpoint for one grade, then advance training before adding another tile. Reveal ten
checkpoint-labeled exam tiles and count every failure.

Make the scaling repair tangible. Seal the full verified dataset on an archive shelf, cut a second
training copy into immutable shards, color each shard's at-most-512 loss examples and gray burn-in
prefix differently, then advance a cursor one shard per round. The status card should show one
selected shard and zero full-source opens. Say explicitly that this bounds routine memory and I/O,
while keeping roughly a second copy of the pixels as the cost of immutable provenance.

When the story reaches power-on composition, show the trainer-side RAM referee switching the
Student's ordered playlist of self-generated visual goals. The frozen Student chooses every
button, and no authored quest direction is inserted, but this remains goal-conditioned
hierarchical control. An eventual win is completion under that declared switching protocol—not
unaided pixel-only autonomy.

The save/load hash bug is a useful engineering beat, not a triumph montage. Show the processed
visual and enumerated RAM matching while PyBoy's broader game-area hash alone changes. Label the
corrected 289-action two-skill replay **STORED-ACTION VERIFIER TEST** and follow it immediately with
the wrong-endpoint rejection. Do not cut from that acceptance into language suggesting the Student
learned to leave the bedroom.

The unchanged V7 denominator belongs on the same screen. This turns an architecture change into a
causal question: did separating discovery from memory and distilling the route create competence,
or merely a cleaner-looking dataset?

### Architectural turn — Stop teaching one button at a time

V8–V10 provide the negative result that justifies the pivot. More self-generated lessons, better
training fit, closed-loop correction, and explicit local recovery all remained compatible with
near-zero frozen competence and no reliable composition. V10's final card is the hinge:
`4,503.282 SECONDS · 534,924 ACTIONS · 3/32 EXAMS · 0 COMPETENT SKILLS`.

V11 asks a different question: can a system with an explicit plan, memory, map-local navigation,
and controller specialists maintain the causal thread of a long role-playing game? Its four opening
canaries are a miniature version of the whole project's philosophy. C1 and C2 expose operational
boundaries. C3 creates a tempting false story that the visible game rejects. C4 finally proves real
control—136 actions, 70 planner calls, RIGHT movement observed—and advances objective 1/84. Only
then does the fresh unbounded run begin.

This is the active **assisted hierarchical lane**. The V7–V10 artifacts remain the **frozen
learned-policy lane**. The video should show both tracks side by side whenever “learning” is spoken:
one asks whether the assembled system can finish; the other asks how much of that ability can later
survive after assistance is replaced by frozen learned components.

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

Version 5.2 begins this chapter before the battle. V5.1 showed that finishing Oak's errand did not
automatically teach the route north: after receiving the Pokédex, it spent 3,035,252 more actions
without reaching the Forest. The new curriculum replaces one distant Forest target with visible
steps through Route 1, Viridian, Route 2, both Forest gates, Pewter, and its Gym. That is explicit
training assistance, not a hidden discovery claim. Each step still needs exact replay admission,
and Brock remains unfinished until the Boulder Badge itself is verified.

Version 6 adds a second axis to this chapter. The furthest verified checkpoint measures discovery;
the backward consolidation start measures how much of that route one retained policy is currently
rehearsing. A rolling 8/10 training gate can move the start earlier, but only frozen attempts can
later establish competence. This prevents a scrapbook of valid fragments from being narrated as
one continuous learned playthrough.

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

The central story is not “a monkey eventually got lucky,” and it is not yet “an AI beat Pokémon
Red.” It is the trail from blind chance, through inherited and learned local habits that failed to
compose, to an openly assisted hierarchy that must show its work. If that hierarchy reaches the
Hall of Fame, the ending is a disclosed assisted completion. If it does not, the exact planning or
tool boundary becomes the ending. Either way, the frozen learned-policy question remains visible
rather than being smuggled into the claim.
