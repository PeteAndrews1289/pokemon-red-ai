# Video and series outline

> **Series-direction update:** Pure Monkey supplied the opening experiment and the conclusion: luck
> cannot accumulate when success never changes later behavior. Evolutionary Explorer then showed
> that a useful accident could have children—but the completed
> [selection × mutation lab](selection-mutation-lab.md) showed that better inheritance still did not
> create meaningful game progress. The current story is the checkpoint-expedition pivot: first make
> long-horizon discoveries reproducible, then use them to train and evaluate one frozen policy. Q1
> now supplies the first payoff and complication: one random-emitter seed replayed a route outside,
> the other failed, and verification cost almost one million additional controller actions.
> Archive v2 is the engineering resolution to that cliff: bounded local proof, a preserved failed
> stop attempt, and a hard-crash twin that returned to the same deterministic terminal state. The
> next protagonist is the model asked to turn the lucky route into a recoverable visual skill.
> Its Stage-0 audition has now passed: after fitting the one 419-action route, the frozen model
> reproduced that route exactly from power-on. The dramatic question is no longer whether the
> wires connect; it is what happens when the apprentice starts midway with no remembered context
> or makes its first mistake. Frontier Apprentice supplied the next honest limitation: it could
> learn a replay-verified victory, but almost every ordinary failed attempt taught the network
> nothing. Four-worker recurrent PPO is the new protagonist because every rollout can now change
> the shared policy. The verifier still decides whether any apparent progress is real.
> Version 4 now supplies the payoff: at action 790,900 a worker reached Viridian City and survived
> all four replay tests. It also supplies the next complication. Across the completed run, 968
> episodes produced 499 visual loops and 469 long stagnations; arriving once did not make the next
> errand reliably learnable. Version 5 turns Viridian into a visible classroom. The teacher gets a
> map of where it has looked and a lesson card saying “enter the Mart.” The future student must
> eventually take the exam without either aid. Version 5 then passed both classroom lessons: it
> entered the Mart and obtained Oak's Parcel. The twist is that the reward system kept pointing at
> the Mart after the task changed. The model had not “forgotten Oak”; the experiment had encoded
> novelty and an expired lesson more clearly than intent. Version 5.1 turns the route around, makes
> backtracking measurable, and asks whether a demonstrated path can become a two-way skill.

This document is a production guide for telling the project's story without getting ahead of the
evidence. The detailed Episode 0 section preserves the original before-training production plan;
the evolutionary sections above it should follow the current evidence.

## The editorial premise

**Working series title:** *Can an AI Learn Pokémon Red—and Show Its Work?*

**One-sentence promise:** Follow one agent from its first controlled button press to increasingly
ambitious goals, with every attempt, intervention, observation, and rule made visible.

The hook is not “AI beats an old game.” Many projects can produce a successful clip. The hook is
building an honest, understandable record of how competence appears: what was engineered, what was
learned, what was supplied in advance, and what failed along the way.

The host's role is not to pretend to know the ending. The host forms a concrete hypothesis, builds
the next test, and lets the evidence change the plan.

## Proposed series arc

| Episode | Central question | Honest endpoint |
| --- | --- | --- |
| 0. Before the AI | How do we know a later success is real and repeatable? | A deterministic, instrumented clean start in the bedroom |
| 1. Monkeys with controllers | What can true randomness accomplish, and what can it never retain? | Preserved baseline plus the retirement decision |
| 2. Survival of the luckiest | Can useful accidents accumulate through selection and mutation? | Better retention, no next map, and an honest failed mechanism |
| 3. Leave home | Can checkpointed search discover and exactly replay one tiny step? | One success, one failure, a verified 419-action lineage, and no false two-seed victory |
| 4. The apprentice | Can one lucky route become a reusable pixel-conditioned skill? | Deliberate overfit smoke, recovery failures, and the first frozen local evaluation |
| 5. Four games, one memory | Can failures teach one shared recurrent policy? | PPO learning curves, complete denominator, and a replay-verified milestone result or plateau |
| 6. The road back | What happens when the correct progress is through familiar territory? | Parcel return checkpoints, active-goal reward accounting, and an honest test of route reuse |
| 6. A real errand | Can a population extend a verified lineage through Oak's Parcel? | Checkpoint-assisted result clearly separated from clean-start policy ability |
| 7. Nature or nurture? | Which progress came from pixels, rewards, RAM, or selection? | Successor comparisons with declared information budgets |
| 8. Brock | Can an evolved lineage prepare, navigate, and win? | Power-on lineage replay, including every failed branch |

Do not promise a full playthrough in the first episode. Promise an investigation with the next
milestone close enough to be credible.

## Featured completed episode: “What If Luck Could Reproduce?”

- **Central narrative:** Random play can create a miracle but cannot inherit it. Evolution turns an
  accident into an ancestor.
- **Honest endpoint:** Frontier selection made the known game-start behavior much more heritable,
  yet all six lanes remained on one map and most policies collapsed into a repeated-action habit.
- **Do not claim:** that one network learned during its lifetime, that checkpoint-assisted search
  equals one clean-start policy, or that a rising archive score means the game is solved.

### Current evidence turn: “It remembered Start—and then stalled”

The 90-minute pretrial supplies the middle of the episode, not its triumphant ending. The population
found an inheritable title-sequence behavior: children of game-starting parents repeated it far more
often than children of non-starting parents. Then progress stopped. Reveal the two suspects only
after showing the family tree: useful parents rarely reproduced under uniform selection, and broad
mutations often destroyed their fragile behavior.

Turn those suspects into a full-screen 2 × 3 board. Rows are uniform versus frontier selection;
columns are broad, gentle, and multiscale mutation. Give every lane a visible action “fuel tank” of
1,536,000 actions. This transforms parameter tuning into an audience-readable question: **should
evolution choose better parents, make smaller changes, or do both?**

The result card must say `INHERITED ARCHIVE — FAILED NEXT-MAP GATE`. Frontier selection retained
game start in 78.1% of children versus 39.6% under uniform selection, but no lane reached a second
map or formed a party. Do not crown Frontier–Broad because it visited seven local positions. The
next honest step is the checkpoint-expedition pivot, not a larger copy of the same run.

## The new central narrative: “First, teach the experiment to remember”

The strongest story is no longer a tournament between four agents. It is a sequence of increasingly
hard promises:

1. **Randomness can stumble forward, but cannot retain the lesson.** Pure Monkey establishes the
   denominator.
2. **Inheritance can retain one behavior, but still fail to compose the next.** The population and
   six-lane lab make that failure visible.
3. **A checkpoint can remember progress, but a saved state can also create a convincing lie.** The
   first replay verifier accepted a forged Hall-of-Fame label because the bytes replayed exactly.
   Semantic recomputation rejected it: the real replay was still at power-on.
4. **Reliable discovery precedes learned completion.** The expedition must build an exact,
   power-on-replayable solution lineage. That lineage becomes self-produced curriculum for a later
   model; it is not itself described as one model solving the game.
5. **The final claim is deliberately difficult.** One frozen policy must start at power-on and reach
   the Hall of Fame with its observation boundary, attempts, and interventions declared in advance.

The false Hall-of-Fame audit is a particularly useful visual beat. Put two green checks on screen:
`SNAPSHOT HASH MATCHED` and `SCREEN HASH MATCHED`. Then strike through the headline `HALL OF FAME`
when the independent referee reads `POWER ON`. The lesson is memorable: deterministic evidence can
reproduce a false label perfectly unless meaning is checked separately.

### Episode 3 result turn: “It left—and that still was not a pass”

Show both seed timelines at equal scale. Seed `20260730` reaches the ground floor and spends the rest
of its 20,000-action fuel without finding the exit. Seed `20260731` reaches the same point sooner,
then steps outside at action 17,832. Pause on the tempting successful clip before revealing the
predeclared rule: **both seeds had to succeed**. Put `H3 MILESTONE VERIFIED` beside `Q1 GATE: 1/2 —
FAILED` so the audience can see that a real achievement and a failed experiment can coexist.

Then reveal the second denominator. The two agents spent 40,000 actions exploring and 954,704
actions proving local checkpoints from power-on. Animate a short exploration bar beside a replay
bar almost twenty-four times longer. This turns an implementation bottleneck into the episode's
next question: can the experiment remember selectively without weakening proof?

Answer that question with the
[Archive v2 qualification card](../experiments/archive-v2-qualification/replay-cost.svg). First
replace the `23.87×` replay bar with `0.31× total / 0.11× ordinary edge`. Then show the interruption
denominator: the first stop command arrived too late and the run is visibly stamped `NOT RESUME
EVIDENCE`. Finally freeze the crash twin with one selection event in flight, preserve its 396-byte
tail, and reveal the exact terminal-state match. This is an engineering victory, not model
learning; use it to open the next act rather than as the episode's gameplay climax.

The exact `left_home` screenshot is a dark transition frame. Keep it on screen as `EXACT EVENT
FRAME`, then cut to the later clear outdoor frame as `STABLE NARRATIVE FRAME`. Do not substitute the
prettier image silently. That contrast expresses the whole editorial premise: evidence and
storytelling serve different jobs, and both should be visible.

### Episode 4 opening turn: “It copied perfectly. Did it learn?”

Use the [Stage-0 gate card](../experiments/visual-apprentice-stage0/stage0-gates.svg) as a fast
four-beat escalation: two independent data captures agree, offline feedback reaches 419/419, the
frozen reload stays identical, and the live model leaves the house in exactly 419 actions. Let the
moment feel like a win—then reveal that every one of those actions matched its only lesson. The
experiment proved the nervous system connects, not that the apprentice can recover.

The next visual should literally cut the route into a backward staircase: 8, 16, 32, 64, 128,
256, and 419 actions remaining. Reset the model's memory at each stair. Show successes moving into
the training tray and failures remaining visibly counted. This makes the distinction between
memorization and learning understandable without pretending that a high loss curve is the story.

### Episode 5 turn: “The failures were being thrown away”

Begin with the Frontier Apprentice rule as a physical sorting table. A verified named milestone
enters the training tray; every other attempt falls through a trapdoor. This was a deliberate trust
decision, not a coding accident—but it makes the limitation visible in one shot.

Then split the screen into four live Game Boy frames feeding one shared brain. Each worker gathers
a different experience; after one rollout, draw a single optimizer pulse back into all four. Put
the privileged referee outside the actor loop and label its two jobs: `REWARD` and `VERIFY`. The
actor side should remain visibly labeled `PIXELS + THREE RECENT ACTIONS` for Version 4.

Use the worker benchmark as a short comic beat. Two games leave empty CPU seats. Six games crowd
the machine and slow down. Four wins at 419.34 collection actions per second in the setup test.
Then immediately replace that number with the production-shaped 218.65 actions/s figure and explain
why four optimizer epochs do more work per rollout. This prevents a microbenchmark from becoming a
misleading headline.

The result reveal needs three meters that can disagree:

1. **Learning:** PPO updates and loss/entropy curves;
2. **Behavior:** map positions, reward components, loops, battles, and episodes; and
3. **Proof:** the furthest milestone that passed exact local replay plus three power-on replays.

If reward rises but the proof meter does not move, that is the episode's result. If a new milestone
passes, show the replay four times before celebrating it. If the archive-assisted system eventually
reaches the Hall of Fame, end on the next harder question: can one frozen policy do it from power-on
without checkpoint help?

Use PPO versions 1–4 as a compact objective-design sequence. Version 1 repeatedly rediscovered
familiar coordinates after resets. Version 2 remembered those coordinates, then made battle endings
its dominant return while Route 1 remained the verified frontier. Freeze on the word **ENDED**, cross
it out, and replace it with **DURABLE PROGRESS: EXPERIENCE OR CAPTURE**. The visual argument is that
better bookkeeping exposed a second ambiguity. Then show Version 3's nine wins among 152 battle
starts: it knew when a battle had paid off, but gave no credit to the actions between menu entry and
victory. Version 4 adds a visible opponent-HP bar that pays only while it falls. When a worker loops,
stamp the frame `VISUAL CYCLE` or `STAGNATION` and recycle its episode budget. Keep Route 1 on the
proof meter throughout; the sequence explains why the design changed without pretending Version 4
has already solved the game.

Then let Version 4 finally move the proof meter. Put `790,900 ACTIONS` beside the 2,109-action
candidate suffix, play its parent-edge replay once, and stack three full power-on replay checks
behind it. Only after the fourth check lands should `ROUTE 1` change to `VIRIDIAN CITY`. Follow the
celebration with the complete denominator: 1,776,644 actions, 968 episodes, 499 visual loops, and
469 long stagnations.

Version 5 should look like school. Put one card above all four workers: `CURRENT LESSON: ENTER THE
VIRIDIAN MART`. Draw their episode-local explored tiles onto a tiny fog-of-war map. Each time a
worker reaches a new closest distance, illuminate one small step; erase the map at reset so the
audience understands that it is short-term working memory, not a supplied world map. Keep three
meters visible and distinct: `GETTING WARMER` for bounded lesson reward, `LEARNING` for PPO updates,
and `PROOF` for replay-verified milestones.

The honesty beat is essential. When the teacher succeeds, do not say “the AI can now do it from the
beginning.” Place the map and lesson card into a tray labeled `TRAINING AIDS`, use the successful
trajectories to teach a new pixels-only student, then remove the tray for the restore-free power-on
exam. That separation is the central narrative: scaffolding can create competence, but graduation
requires doing without the scaffold.

### Suggested beats

1. **The retirement:** replay Pure Monkey's best moments, then reveal that every next action still
   had exactly the same random distribution.
2. **The inheritance rule:** draw one small neural genome, copy it, mutate a visible subset, and
   give the child one fixed lifetime.
3. **The first generation:** show policies as queues feeding emulator workers, not hundreds or
   thousands of simultaneous windows.
4. **Why one winner is dangerous:** show a Route 1 grinding dynasty taking over a naive
   winner-takes-all population.
5. **The ecosystem:** replace the leaderboard with the MAP-Elites grid and keep several behavioral
   champions alive.
6. **The family album:** follow one successful mutation backward through parent IDs and exact
   generation records.
7. **The replay test:** distinguish a checkpoint-assisted branch from the complete power-on action
   lineage used to verify it.
8. **The result:** report descendants evaluated, archive coverage, lineage depth, milestones,
   compute, crashes, interventions, and all failed children.

### Core visuals

- an animated family tree whose branches brighten, reproduce, or become extinct;
- a 2D MAP-Elites grid filling with colored champions;
- the six-cell selection × mutation dashboard, each cell with the same action-budget gauge;
- a parent/child weight-difference heat map;
- two side-by-side labels: `ONE FIXED LIFETIME` and `LEARNING BETWEEN GENERATIONS`;
- a continuous ancestral action ribbon replaying from power-on;
- a claim card separating `POPULATION REACHED`, `LINEAGE REPLAYED`, and `ONE POLICY SOLVED`.

## Episode 0: “Before I Train an AI to Play Pokémon”

- **Target length:** 12–16 minutes
- **Purpose:** Introduce the ambition, show why instrumentation matters, and end at the exact point
  where training can begin.
- **Historical status represented:** At the time this Episode 0 plan was drafted, no model had been
  trained and no acting agent had played the game. Later episodes must replace this card with the
  current evidence ladder rather than reuse it as a present-tense claim.

### Cold open — the future, interrupted (0:00–0:35)

**Narration idea**

> I want to build an AI that can plan its way through Pokémon Red. But before I show you a learning
> curve or one lucky victory, I need to answer a less exciting question: how would either of us know
> that it really learned anything?

**Picture**

- Begin with an original schematic of the future system: Planner, Skills, Memory, Watchdog.
- Flash three short original animations: a route loop, a rising graph that does not equal success,
  and twenty attempt marks with only one check.
- Pull the camera back to reveal that the system boxes are outlines marked “not built yet.”
- Title card: `EPISODE 0 — BUILDING THE MEASURING INSTRUMENT`.

**Claim shown on screen:** `TRAINING STATUS: NOT STARTED`.

Avoid opening with a fabricated “trained agent” sequence. If a future clip is used after later
episodes exist, label it with its episode, checkpoint, and evaluation status.

### Beat 1 — Why this game is an interesting test (0:35–1:45)

Explain that the controller is simple while the task is not. Movement, menus, battles, memory, and
long-delayed goals demand different forms of competence.

**Picture**

- Original icons for navigation, menu choice, battle, memory, and recovery.
- A widening decision tree made from generic arrows and buttons—not copied game graphics.
- A milestone ladder: Bedroom → House → Oak/Starter → Rival → Parcel → Brock.

**Audience takeaway:** A small action space does not imply a small reasoning problem.

### Beat 2 — The edited-success problem (1:45–3:00)

Stage a generic demonstration with twenty run markers. Highlight one success, then reveal the
nineteen failures. Explain why training reward, best run, and official success rate answer different
questions.

**Picture**

- First, a single large `✓` with the headline “IT WORKED.”
- Then zoom out to the complete run strip: `✓ × × ↻ × ...`.
- Split screen: `BEST CLIP` versus `17/20 PREDECLARED ATTEMPTS`.

**Narration point:** The project will keep the denominator, count help, and separate practice from
evaluation.

### Beat 3 — Defining the rules (3:00–4:30)

Introduce the observation boundary. The acting system will receive only declared inputs. The
referee may read limited state to score an attempt but cannot whisper those values to the policy.

**Picture**

- Original flow diagram: `GAME → OBSERVATION → AGENT → BUTTONS → GAME`.
- Put `REFEREE` beside the loop, connected to the game but not the agent.
- Animate six small labels for the current read-only observation: game started, map number, X, Y,
  party count, battle state.
- Add a large one-way sign over the interface: `READ ONLY`.

**Important wording:** Call the current setup **instrumented**, not screen-only. Explain that map
number and coordinates come from disclosed read-only memory fields.

### Beat 4 — The ROM fingerprint and private boundary (4:30–5:35)

Explain a hash as a fingerprint. Different game revisions can arrange internal data differently, so
the harness accepts one verified revision instead of assuming a filename is correct.

**Picture**

- Generic file card enters a fingerprint scanner.
- Show a shortened public hash such as `5ca7ba…96b7b`, plus size and title.
- Place the ROM outside a diagram of the Git repository, with a closed boundary around it.
- Show a green test result: `ROM OR SAVE DATA IN REPOSITORY: NONE`.

Do not display the user's path, ROM bytes, download source, or instructions for acquiring a ROM.

### Beat 5 — What a controller action actually means (5:35–6:45)

A press is not instantaneous in an emulator. Show the current action as eight held frames followed
by sixteen released frames. Explain why explicit timing makes runs comparable.

**Picture**

- A 24-cell timeline with the first eight cells filled and the next sixteen outlined.
- A tile-grid animation that moves a generic marker one square.
- Overlay: `SAME INPUT CONTRACT ON EVERY RUN`.

If gameplay footage is available and cleared for use, a brief side-by-side of “held too long” and
“one calibrated tile” can support the point. The explanation must still work with the original grid
animation alone.

### Beat 6 — The save-state trap (6:45–8:00)

Explain that development snapshots make repeated experiments practical, but they can also hide an
advantage. The harness stores snapshots privately in memory and binds them to the exact game and
emulator version. Official clean-start evaluations will say when snapshots are prohibited.

**Picture**

- A generic timeline rewinds from frame 12 to frame 5.
- Show both the visual state and the logical frame counter rewinding together.
- Stamp: `DEVELOPMENT TOOL ≠ CLEAN-START EVALUATION`.

**Claim boundary:** Snapshot restore has been tested for determinism; it is not evidence of agent
learning.

### Beat 7 — The first reproducibility test (8:00–10:00)

Describe the fixed sequence that advances through the introduction, chooses built-in names, and
stops in the bedroom. Run it twice. Compare the resulting named state fields, screen hash, snapshot
hash, and logical frame.

**Picture**

- Two parallel lanes labeled `RUN A` and `RUN B`.
- Identical action blocks flow through both.
- Four comparison rows click into place:
  - logical frame: match;
  - named state: match;
  - screen pixels: match;
  - private snapshot payload: match.
- End with a generic bedroom-shaped tile grid or a rights-reviewed, brief emulator capture. Do not
  add extracted sprites, maps, or ROM-derived artwork to the repository or downloadable graphics.

**On-screen disclaimer:** `FIXED TEST SEQUENCE — NO POLICY, NO LEARNING`.

Let this disclaimer remain visible long enough to read. The dramatic result is reproducibility,
not autonomy.

### Beat 8 — What has actually been built (10:00–11:10)

Return to the system diagram. Light up only the emulator harness, read-only instrumentation,
recorder, and tests. Leave the policy observation adapter, Planner, Learned Skills, Memory, and
Watchdog dimmed or outlined.

**Picture**

- `TEST SUITE PASS`, with the count generated from the release run rather than typed into the edit.
- Checklist: exact revision, timed inputs, in-memory snapshots, sanitized traces, clean bootstrap.
- A second list headed `NOT YET`: training environment, reward, policy, planner, learned behavior.

This is the episode's clearest status scene. Never let the visual imply that outlined components
already exist.

### Beat 9 — The first real experiment (11:10–13:10)

Introduce the next question: can a learned policy leave the bedroom? Explain the three reference
points planned before training:

1. a human action-count baseline;
2. a random-action baseline;
3. a frozen evaluation set and action budget.

Then show the proposed milestone card with blanks rather than invented results.

**Picture**

```text
MILESTONE        Leave the bedroom
OBSERVATION      To be frozen
ACTION SPACE     To be frozen
SUCCESS          Cross the declared exit
BUDGET           To be frozen
BASELINES        Human / Random
RESULT           Pending
```

**Prediction prompt:** Record a specific hypothesis before training. For example: “Coordinates may
speed up learning, but they may also let the policy memorize one start state.” Mark it as a
hypothesis, not a result.

### Close — invite the audience into the notebook (13:10–14:00)

**Narration idea**

> Today the AI did not play Pokémon. We built the thing that will let us tell when it finally does.
> Next, it gets its first objective, its first reward, and plenty of ways to fail.

**Picture**

- An empty training curve axes appears.
- Twenty blank evaluation slots appear underneath it.
- The first milestone, `Measuring instrument`, receives a check.
- The next milestone, `Leave the bedroom`, begins pulsing.
- End card links to the repository and the exact tagged release used for the video.

## Shot inventory for Episode 0

Capture or produce these before editing. Re-run all displayed measurements from the release commit.

| Asset | Format | Notes |
| --- | --- | --- |
| Master architecture animation | 16:9 vector/motion graphic | Original geometric design; components can light up by phase |
| Observation boundary | 16:9 diagram | Clearly separate agent inputs and referee-only state |
| Run-strip reveal | Motion graphic | Reveal all attempts after the tempting success clip |
| Controller timing | 24-cell animation | Eight held, sixteen released; label frame rate only if verified |
| Snapshot rewind | Motion graphic | Rewind game state and logical frame counter together |
| Dual-run comparison | Screen recording + overlay | Use actual current hashes or shortened identifiers from fresh runs |
| Status card | Full-screen graphic | “Training not started” must be prominent |
| Test output | Screen capture or recreated data card | Show only current, verified counts; hide private paths and machine details |
| Roadmap ladder | Original vector graphic | Bedroom, house, Oak/starter, rival, parcel, Brock; use text and generic symbols |
| Host segments | Camera | Record clean openings/endings so claims can be revised late in edit |

Keep repository-safe originals in a dedicated future media source folder only after its policy is
defined. Never commit generated recordings accidentally; the current repository intentionally
ignores them.

## A visual grammar for later episodes

Use the same visual elements in every episode so the audience learns how to read the experiment.

### Always-visible status chip

During demonstrations, show one of:

- `DEVELOPMENT` — system or reward is being changed;
- `TRAINING` — policy may learn from the attempt;
- `EVALUATION` — policy and rules are frozen;
- `ILLUSTRATION` — animation or reconstruction, not a recorded run.

### Information badges

When the acting configuration changes, briefly show:

```text
ACTOR        PPO skill / LLM planner / Hybrid / Scripted test
SEES         Pixels / Coordinates / Text / Memory
START        Clean boot / Development snapshot
HELP         Intervention count
SPEED        Real-time / 8× / 64× / Cut
```

### Results trio

Pair three visuals rather than relying on one curve:

1. **Training curve:** median objective and spread across steps or seeds.
2. **Evaluation strip:** every frozen attempt and terminal reason.
3. **Representative run:** one run selected by a declared rule.

### Failure card

```text
FAILURE          DOORWAY_OSCILLATION
FIRST OBSERVED   experiment identifier
RATE             6 / 20 evaluation attempts
EVIDENCE         repeated two-tile cycle
HYPOTHESIS       policy overreacts to alternating frames
NEXT TEST        four-frame action history
```

Keep “evidence,” “hypothesis,” and “next test” as separate lines. This prevents a plausible story
about a failure from becoming an asserted cause.

## Claims discipline checklist

Complete this before recording narration and again before publishing.

- [ ] Does every numerical result have an experiment identifier or reproducible source?
- [ ] Is the Git commit or tagged release recorded?
- [ ] Were evaluation rules and budgets frozen before the displayed attempts?
- [ ] Are all attempts represented, not only successes?
- [ ] Are training, development, evaluation, scripted tests, and illustrations labeled distinctly?
- [ ] Does “the agent saw” exclude referee-only and debugging-only information?
- [ ] Are human interventions, resets, and hand-written knowledge counted?
- [ ] Are emulator steps, emulator-hours, and wall-clock time kept distinct?
- [ ] Is a reward curve presented as a diagnostic rather than proof of task success?
- [ ] Is sped-up, cut, reconstructed, or reenacted footage labeled?
- [ ] Have test counts, package versions, and roadmap status been refreshed since the script draft?
- [ ] Are private paths, keys, ROM data, snapshots, and local usernames absent from the frame?
- [ ] Are repository visuals original and free of extracted proprietary assets?
- [ ] If gameplay footage appears, has the creator made and documented a separate platform-specific
      rights decision?

## Words to use carefully

| Tempting line | Better line |
| --- | --- |
| “I trained an AI to play Pokémon.” | “I built and tested several learners; none has yet completed a named gameplay milestone in the current expedition.” |
| “It learned the room.” | “It crossed the exit in 17 of 20 held-out attempts.” |
| “It only saw the game.” | “The policy received pixels plus the declared X/Y coordinates.” |
| “No cheating.” | “The policy could not write memory or load snapshots; the referee read these six fields.” |
| “Completely autonomous.” | “There were zero interventions during these frozen evaluation attempts.” |
| “It figured this out from scratch.” | “It used this pretrained planner, these prompts, and this trained skill.” |
| “It beat the game.” | “It completed the declared Brock milestone from a clean start.” |
| “Training took four hours.” | “Training used N emulator steps, H emulator-hours, and four wall-clock hours.” |

Specific language is not less exciting. It gives the audience a reason to trust the exciting part.

## Publishing notes

- Link the source release, experiment summary, and readable narrative—not a private run directory.
- Put key limitations in the spoken video and description, not only in a distant technical note.
- Avoid game music, extracted sprites, box art, official fonts, and downloadable ROM-derived assets.
- Keep any necessary gameplay excerpts short, analytical, and surrounded by original commentary;
  platform rules and rights questions require a separate review by the creator.
- Captions should spell out acronyms the first time they appear.
- Charts need direct labels and shapes in addition to color.
- Supply alt text or a text transcript for every result visual.
- Archive the final script and the release identifier so later episodes do not rewrite what was
  claimed at the time.

## Description template

Use this as a checklist, not as final copy:

```text
Question:
What this episode built:
What it did not build:
Acting system:
Agent observation:
Referee-only information:
Start condition:
Evaluation protocol:
Results and denominator:
Human interventions:
Training budget and compute:
Source release:
Experiment artifacts:
Known limitations:
Next hypothesis:
```

The description should remain useful to someone who never watches the video. The video should
remain honest to someone who never opens the description.
