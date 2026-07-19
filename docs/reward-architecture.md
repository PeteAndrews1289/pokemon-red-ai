# Reward architecture: from wandering to discovery

This document defines the second four-agent protocol. It was written after the first scaled
pretrial produced a striking failure: every agent could start the game, obtain a starter, battle,
level, and evolve, yet none could reliably escape the Pallet Town and Route 1 loop.

The failure was useful. It showed that table capacity and replay volume were not the limiting
factors. The limiting factors were the meaning of an action, the density of local rewards, and the
absence of intermediate progress signals.

## Design principle

The experiment is an information ladder, not a claim that all four lanes solve the same optimization
problem.

| Lane | Chooses buttons from | Receives as reward | Sealed referee |
|---|---|---|---|
| Pure Monkey | Seeded uniform randomness | Nothing | Measures only |
| Visually Curious | Rendered pixels | First visits to coarse visual cells | Measures only |
| Outcome-Rewarded | Rendered pixels | Generic game outcomes | Measures only |
| Conventional | Pixels plus coarse RAM progress | Generic outcomes plus required milestones | Measures only |

The referee reads RAM for reporting in every lane. Its outputs never enter the monkey or curiosity
policies or rewards. A dashboard value of zero therefore means zero observed progress, not “not
measured.”

## Deterministic action vocabulary

All four continuous lanes use the same eight actions:

1. Up
2. Down
3. Left
4. Right
5. A
6. B
7. Start
8. No-op

Select is removed because it is unnecessary for completing Pokémon Red and was consuming a large
fraction of early-run actions. Each non-scripted action now uses the same eight held frames and
twelve released frames. The policy chooses the action, not its timing. This removes a source of
transition noise where the same learned action could previously turn, move, repeat, or fail depending
on a second random timing choice.

The monkey remains a monkey: it samples uniformly from the eight actions. Deterministic timing makes
the comparison cleaner without giving it game knowledge.

## Sealed referee catalogue

The referee records:

- maps, coordinates, and unique directed warps;
- party size, species, levels, and learned moves;
- wild, trainer, and loss battle states;
- Pokédex seen and owned bits;
- bag item IDs and required-item milestones;
- persistent game event flags;
- badges, blackouts, and whether the Pokédex was obtained.

Pokédex bitfields are ignored until the Pokédex itself is obtained. During starter selection,
Pokémon Red temporarily writes preview bits into the owned-species field to draw the choice screen;
counting those bits would manufacture captures that never happened.

The implementation uses symbols documented by the
[PRET Pokémon Red disassembly](https://github.com/pret/pokered) and the supported US revision is
validated by ROM hash before a run starts. Raw ROM bytes, save states, and full RAM dumps are not
served by the dashboard.

## Generic outcome rewards

Outcome-Rewarded and Conventional share this base ladder:

| Event | Reward | Frequency rule |
|---|---:|---|
| Game begins | +3 | Once |
| New coordinate | +0.03 | Once per map-coordinate tuple |
| New map | +20 | Once |
| New directed warp | +5 | Once per source-destination pair |
| Party grows | +25 | Per additional member at a new maximum |
| New move learned | +2 | Once per move ID after the initial move set |
| First wild or trainer battle kind | +5 | Once per kind |
| New Pokédex species seen | +3 | Once per species |
| New Pokédex species owned | +25 | Once per species, including evolutions |
| Newly set persistent event flag | +8 | Once per bit during the run |
| Badge | +200 | Once per badge |
| First observed blackout | -2 | Loss is no longer treated as a discovery bonus |

The position term is deliberately tiny. In the first scaled pretrial, more than half of the guided
agents' returns came from local coordinates, while entering a new map was worth only five points.
The learner was being paid to vacuum Pallet Town rather than leave it.

Rewards are paid on transitions or new maxima. Opening a menu, retaining an item, maintaining HP,
or remaining at a high level does not create reward every step.

## Explicit Conventional milestones

Conventional receives the generic ladder plus:

| Milestone | Reward |
|---|---:|
| Oak's Parcel obtained | +30 |
| Oak's Parcel delivered | +40 |
| Pokédex obtained | +50 |
| First Poké Balls obtained | +15 |
| Story/key item or HM obtained | +50 each |

The tracked item set covers the Bicycle, Secret Key, Card Key, S.S. Ticket, Gold Teeth, Silph
Scope, Poké Flute, Lift Key, and all five HMs. Some are optional in a minimal route, but each is a
legible sign that the agent has opened a new part of the game.

This makes Conventional meaningfully conventional. The previous version gave it more RAM in its
observation but the same objective as Outcome-Rewarded. Extra exact state fragmented a table-based
policy without explaining which facts mattered.

The new policy key keeps map identity but coarsens coordinates into four-tile regions. It also adds
bounded counts for Pokédex progress, party level, bag size, and Pokédex acquisition. This preserves
useful progress context while allowing nearby states to share experience.

## Gentle loop pressure

The guided lanes receive small, graduated penalties:

- fourth identical action in a row: -0.02;
- sixth and later identical actions: -0.05;
- fourth visit to a coordinate: -0.02;
- eighth, sixteenth, and thirty-second visits: -0.05;
- each block of 64 consecutive steps without a coordinate change: -0.05.

These values are intentionally small. They discourage policy collapse without making experimentation
more expensive than progress is valuable. The curiosity and monkey lanes do not receive these
penalties.

## What is measured but not rewarded

The following remain visible in reports but are not direct objectives:

- raw experience and ordinary level gains;
- every battle start or every attack;
- money and repeated purchases;
- raw HP and repeated healing;
- opening menus;
- pressing A at arbitrary coordinates;
- total play time.

These signals are easy to farm. The first pretrial already demonstrated that blind agents can grind
Route 1 efficiently; paying them more for grinding would strengthen the cul-de-sac.

## Explainability contract

Every reward component is accumulated by name in `status.json` and displayed as an explainable
ledger. Major first-time events receive exact screenshots. Progress histories include maps,
positions, Pokédex counts, party level, badges, and reward. This lets a later video distinguish:

- what the agent saw;
- what the referee measured;
- what the learner was rewarded for;
- what the policy actually learned to repeat.

## External design references

- [Learning Pokémon With Reinforcement Learning: Rewards](https://drubinstein.github.io/pokerl/docs/chapter-2/rewards/)
  documents a full-game system with more than 25 reward terms and reports that coordinate-only
  exploration and menu rewards both created failure modes.
- [PokeRL](https://github.com/reddheeraj/PokemonRL) documents deterministic action abstraction,
  hierarchical early-game rewards, visited-map memory, and anti-loop controls.
- [PokémonRedExperiments](https://github.com/PWhiddy/PokemonRedExperiments) provides an influential
  open implementation using event flags, levels, healing, opponent strength, badges, and visual or
  coordinate exploration.
- [PRET pokered event constants](https://github.com/pret/pokered/blob/master/constants/event_constants.asm)
  and [WRAM definitions](https://github.com/pret/pokered/blob/master/ram/wram.asm) are the primary
  references for measurable game state.

## Interpretation limits

A single seed is a narrative scouting run, not statistical proof. A true comparison should repeat
each lane across multiple seeds and report medians and dispersion for time-to-starter, first new
map, first Pokédex, first capture, first badge, and furthest required event.

The reward ladder is also not neutral. It expresses a philosophy: exploration should become
interaction, interaction should become collection, and collection should eventually become story
progress. The purpose of keeping the four lanes is to make that increasing guidance visible rather
than hiding it.
