# Video and series outline

> **Series-direction update:** The opening question is now “What happens if I give an agent the
> Pokémon Red screen and buttons, but never tell it what the game is?” Episode 1 compares the
> Monkey and Archivist discovery curves. The detailed Phase 0 material below remains the prologue
> explaining why the measurements can be trusted. See [Blind curiosity](blind-curiosity.md).

This document is a production guide for telling the project's story without getting ahead of the
evidence. It assumes the first public video is made at the end of Phase 0, before model training.

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
| 1. Leave the room | Can a small learned policy acquire basic movement? | Held-out bedroom-exit success rate |
| 2. Leave home | Does the skill survive doors, stairs, and a second map? | House-exit evaluation plus failure atlas |
| 3. Meet Oak | Can the system trigger the story event and choose a starter? | Starter-choice evaluation with menu failures visible |
| 4. The first battle | Can battle behavior be learned without scripting the answer? | Rival-battle evaluation under declared observations |
| 5. A real errand | Can a planner and skills deliver Oak's Parcel after the rival battle? | Clean-start parcel completion rate |
| 6. Why hybrid? | Which tasks favor language-model, RL, or combined control? | Predeclared engineering comparison |
| 7. Brock | Can the full system prepare, navigate, and win? | Clean-start Brock attempts, including every failure |

Do not promise a full playthrough in the first episode. Promise an investigation with the next
milestone close enough to be credible.

## Episode 0: “Before I Train an AI to Play Pokémon”

- **Target length:** 12–16 minutes
- **Purpose:** Introduce the ambition, show why instrumentation matters, and end at the exact point
  where training can begin.
- **Current status represented:** No model has been trained and no acting agent has played the game.

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
| “I trained an AI to play Pokémon.” | “I built the reproducible environment; training begins next.” |
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
