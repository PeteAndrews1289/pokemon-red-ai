from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum, IntFlag
from typing import Any

from pokemon_red_ai.state import PokemonRedState


class PokemonRedMap(IntEnum):
    """Map IDs from the supported pret/pokered revision."""

    PALLET_TOWN = 0x00
    VIRIDIAN_CITY = 0x01
    PEWTER_CITY = 0x02
    CERULEAN_CITY = 0x03
    LAVENDER_TOWN = 0x04
    FUCHSIA_CITY = 0x07
    CINNABAR_ISLAND = 0x08
    INDIGO_PLATEAU = 0x09
    ROUTE_1 = 0x0C
    ROUTE_23 = 0x22
    REDS_HOUSE_1F = 0x25
    VIRIDIAN_FOREST = 0x33
    MT_MOON_1F = 0x3B
    MT_MOON_B1F = 0x3C
    MT_MOON_B2F = 0x3D
    ROCK_TUNNEL_1F = 0x52
    SS_ANNE_1F = 0x5F
    SS_ANNE_B1F_ROOMS = 0x68
    VICTORY_ROAD_1F = 0x6C
    LANCES_ROOM = 0x71
    HALL_OF_FAME = 0x76
    CHAMPIONS_ROOM = 0x78
    POKEMON_TOWER_1F = 0x8E
    POKEMON_TOWER_7F = 0x94
    SAFARI_ZONE_GATE = 0x9C
    POKEMON_MANSION_1F = 0xA5
    INDIGO_PLATEAU_LOBBY = 0xAE
    SILPH_CO_1F = 0xB5
    VICTORY_ROAD_2F = 0xC2
    VICTORY_ROAD_3F = 0xC6
    ROCKET_HIDEOUT_B1F = 0xC7
    ROCKET_HIDEOUT_ELEVATOR = 0xCB
    SILPH_CO_2F = 0xCF
    SILPH_CO_8F = 0xD5
    POKEMON_MANSION_2F = 0xD6
    POKEMON_MANSION_B1F = 0xD8
    SAFARI_ZONE_EAST = 0xD9
    SAFARI_ZONE_NORTH_REST_HOUSE = 0xE1
    ROCK_TUNNEL_B1F = 0xE8
    SILPH_CO_9F = 0xE9
    SILPH_CO_ELEVATOR = 0xEC
    LORELEIS_ROOM = 0xF5
    BRUNOS_ROOM = 0xF6
    AGATHAS_ROOM = 0xF7


class PokemonRedEvent(IntEnum):
    """Stable bit indexes into ``wEventFlags`` for named story outcomes.

    Values come from ``constants/event_constants.asm`` at pret/pokered commit
    1e96034092686d006e863cace09e87273051a3d8, the revision already pinned by
    :mod:`pokemon_red_ai.state`.
    """

    FOLLOWED_OAK_INTO_LAB = 0x000
    HALL_OF_FAME_DEX_RATING = 0x003
    GOT_STARTER = 0x022
    BATTLED_RIVAL_IN_OAKS_LAB = 0x023
    GOT_POKEDEX = 0x025
    OAK_GOT_PARCEL = 0x038
    GOT_OAKS_PARCEL = 0x039
    BEAT_VIRIDIAN_GYM_GIOVANNI = 0x051
    BEAT_BROCK = 0x077
    BEAT_MISTY = 0x0BF
    BEAT_GHOST_MAROWAK = 0x10F
    RESCUED_MR_FUJI = 0x117
    GOT_POKE_FLUTE = 0x128
    BEAT_LT_SURGE = 0x167
    BEAT_ERIKA = 0x1A9
    BEAT_KOGA = 0x259
    GOT_HM04 = 0x238
    GAVE_GOLD_TEETH = 0x239
    BEAT_BLAINE = 0x299
    BEAT_SABRINA = 0x361
    USED_CELL_SEPARATOR_ON_BILL = 0x55B
    GOT_SS_TICKET = 0x55C
    GOT_HM01 = 0x5E0
    ROCKET_DROPPED_LIFT_KEY = 0x6A6
    BEAT_ROCKET_HIDEOUT_GIOVANNI = 0x6A7
    BEAT_SILPH_CO_GIOVANNI = 0x78F
    GOT_HM03 = 0x880
    BEAT_LORELEI = 0x8E1
    BEAT_BRUNO = 0x8E9
    BEAT_AGATHA = 0x8F1
    BEAT_LANCE = 0x8FE
    BEAT_CHAMPION_RIVAL = 0x901


class PokemonRedItem(IntEnum):
    OAKS_PARCEL = 0x46
    SECRET_KEY = 0x2B
    CARD_KEY = 0x30
    SS_TICKET = 0x3F
    GOLD_TEETH = 0x40
    SILPH_SCOPE = 0x48
    POKE_FLUTE = 0x49
    LIFT_KEY = 0x4A
    HM01_CUT = 0xC4
    HM03_SURF = 0xC6
    HM04_STRENGTH = 0xC7


class Badge(IntFlag):
    BOULDER = 1 << 0
    CASCADE = 1 << 1
    THUNDER = 1 << 2
    RAINBOW = 1 << 3
    SOUL = 1 << 4
    MARSH = 1 << 5
    VOLCANO = 1 << 6
    EARTH = 1 << 7


def event_flag_is_set(event_flags: bytes | None, bit_index: int) -> bool:
    """Return a documented event bit without trusting short or absent snapshots."""

    if bit_index < 0:
        raise ValueError("event bit index cannot be negative")
    if event_flags is None:
        return False
    byte_index, bit = divmod(bit_index, 8)
    return byte_index < len(event_flags) and bool(event_flags[byte_index] & (1 << bit))


@dataclass(frozen=True, slots=True)
class MilestoneCondition:
    """One conjunction of referee-visible evidence for a milestone.

    A definition can contain several conditions, which are alternatives. Within one condition,
    every populated field must match. This lets Hall of Fame require both the champion flag and
    the Hall of Fame map while starter selection can use either its persistent event bit or the
    already-populated party as recovery evidence.
    """

    game_started: bool = False
    event_flags: tuple[int, ...] = ()
    map_ids: tuple[int, ...] = ()
    badge_mask: int = 0
    minimum_party_count: int | None = None
    got_pokedex: bool = False
    bag_items: tuple[int, ...] = ()

    def __post_init__(self) -> None:
        if not any(
            (
                self.event_flags,
                self.map_ids,
                self.badge_mask,
                self.minimum_party_count is not None,
                self.got_pokedex,
                self.bag_items,
                self.game_started,
            )
        ):
            raise ValueError("a milestone condition needs at least one piece of evidence")
        if self.minimum_party_count is not None and self.minimum_party_count < 0:
            raise ValueError("minimum party count cannot be negative")

    def matches(self, state: PokemonRedState) -> bool:
        if not state.game_started:
            return False
        if self.event_flags and not all(
            event_flag_is_set(state.event_flags, event) for event in self.event_flags
        ):
            return False
        if self.map_ids and state.map_id not in self.map_ids:
            return False
        if self.badge_mask and ((state.badge_bits or 0) & self.badge_mask) != self.badge_mask:
            return False
        if (
            self.minimum_party_count is not None
            and (state.party_count or 0) < self.minimum_party_count
        ):
            return False
        if self.got_pokedex and not state.got_pokedex:
            return False
        return not self.bag_items or set(self.bag_items).issubset(state.bag_item_ids or ())


@dataclass(frozen=True, slots=True)
class MilestoneDefinition:
    ordinal: int
    key: str
    label: str
    chapter: str
    kind: str
    conditions: tuple[MilestoneCondition, ...]

    def reached_by(self, state: PokemonRedState) -> bool:
        return any(condition.matches(state) for condition in self.conditions)

    def public_dict(self) -> dict[str, object]:
        return {
            "ordinal": self.ordinal,
            "key": self.key,
            "label": self.label,
            "chapter": self.chapter,
            "kind": self.kind,
        }


def _condition(
    *,
    started: bool = False,
    event: PokemonRedEvent | None = None,
    maps: tuple[int | PokemonRedMap, ...] = (),
    badge: Badge | None = None,
    party: int | None = None,
    pokedex: bool = False,
    items: tuple[PokemonRedItem, ...] = (),
) -> MilestoneCondition:
    return MilestoneCondition(
        game_started=started,
        event_flags=() if event is None else (int(event),),
        map_ids=tuple(int(map_id) for map_id in maps),
        badge_mask=0 if badge is None else int(badge),
        minimum_party_count=party,
        got_pokedex=pokedex,
        bag_items=tuple(int(item) for item in items),
    )


def _definition(
    key: str,
    label: str,
    chapter: str,
    kind: str,
    *conditions: MilestoneCondition,
) -> MilestoneDefinition:
    return MilestoneDefinition(-1, key, label, chapter, kind, conditions)


_UNORDERED_MILESTONES = (
    _definition(
        "game_started",
        "The adventure begins",
        "Pallet Town",
        "state",
        _condition(started=True),
    ),
    _definition(
        "left_bedroom",
        "Reached the ground floor",
        "Pallet Town",
        "landmark",
        _condition(maps=(PokemonRedMap.REDS_HOUSE_1F,)),
    ),
    _definition(
        "left_home",
        "Stepped outside",
        "Pallet Town",
        "landmark",
        _condition(maps=(PokemonRedMap.PALLET_TOWN,)),
    ),
    _definition(
        "met_professor_oak",
        "Followed Professor Oak into his lab",
        "Pallet Town",
        "story",
        _condition(event=PokemonRedEvent.FOLLOWED_OAK_INTO_LAB),
    ),
    _definition(
        "chose_starter",
        "Chose a starter Pokemon",
        "Pallet Town",
        "story",
        _condition(event=PokemonRedEvent.GOT_STARTER),
        _condition(party=1),
    ),
    _definition(
        "fought_lab_rival",
        "Finished the first rival battle",
        "Pallet Town",
        "story",
        _condition(event=PokemonRedEvent.BATTLED_RIVAL_IN_OAKS_LAB),
    ),
    _definition(
        "reached_route_1",
        "Reached Route 1",
        "Oak's Errand",
        "landmark",
        _condition(maps=(PokemonRedMap.ROUTE_1,)),
    ),
    _definition(
        "reached_viridian_city",
        "Reached Viridian City",
        "Oak's Errand",
        "landmark",
        _condition(maps=(PokemonRedMap.VIRIDIAN_CITY,)),
    ),
    _definition(
        "obtained_oaks_parcel",
        "Obtained Oak's Parcel",
        "Oak's Errand",
        "story",
        _condition(event=PokemonRedEvent.GOT_OAKS_PARCEL),
        _condition(items=(PokemonRedItem.OAKS_PARCEL,)),
    ),
    _definition(
        "delivered_oaks_parcel",
        "Delivered Oak's Parcel",
        "Oak's Errand",
        "story",
        _condition(event=PokemonRedEvent.OAK_GOT_PARCEL),
    ),
    _definition(
        "obtained_pokedex",
        "Received the Pokedex",
        "Oak's Errand",
        "story",
        _condition(event=PokemonRedEvent.GOT_POKEDEX),
        _condition(pokedex=True),
    ),
    _definition(
        "reached_viridian_forest",
        "Entered Viridian Forest",
        "The Boulder Badge",
        "landmark",
        _condition(maps=(PokemonRedMap.VIRIDIAN_FOREST,)),
    ),
    _definition(
        "reached_pewter_city",
        "Reached Pewter City",
        "The Boulder Badge",
        "landmark",
        _condition(maps=(PokemonRedMap.PEWTER_CITY,)),
    ),
    _definition(
        "boulder_badge",
        "Earned the Boulder Badge",
        "The Boulder Badge",
        "badge",
        _condition(badge=Badge.BOULDER),
    ),
    _definition(
        "entered_mt_moon",
        "Entered Mt. Moon",
        "To Cerulean City",
        "landmark",
        _condition(
            maps=(
                PokemonRedMap.MT_MOON_1F,
                PokemonRedMap.MT_MOON_B1F,
                PokemonRedMap.MT_MOON_B2F,
            )
        ),
    ),
    _definition(
        "reached_cerulean_city",
        "Reached Cerulean City",
        "To Cerulean City",
        "landmark",
        _condition(maps=(PokemonRedMap.CERULEAN_CITY,)),
    ),
    _definition(
        "cascade_badge",
        "Earned the Cascade Badge",
        "Cerulean City",
        "badge",
        _condition(badge=Badge.CASCADE),
    ),
    _definition(
        "helped_bill",
        "Restored Bill",
        "Cerulean City",
        "story",
        _condition(event=PokemonRedEvent.USED_CELL_SEPARATOR_ON_BILL),
    ),
    _definition(
        "obtained_ss_ticket",
        "Obtained the S.S. Ticket",
        "Vermilion City",
        "story",
        _condition(event=PokemonRedEvent.GOT_SS_TICKET),
        _condition(items=(PokemonRedItem.SS_TICKET,)),
    ),
    _definition(
        "boarded_ss_anne",
        "Boarded the S.S. Anne",
        "Vermilion City",
        "landmark",
        _condition(
            maps=tuple(
                range(
                    int(PokemonRedMap.SS_ANNE_1F),
                    int(PokemonRedMap.SS_ANNE_B1F_ROOMS) + 1,
                )
            )
        ),
    ),
    _definition(
        "obtained_cut",
        "Obtained HM01 Cut",
        "Vermilion City",
        "story",
        _condition(event=PokemonRedEvent.GOT_HM01),
        _condition(items=(PokemonRedItem.HM01_CUT,)),
    ),
    _definition(
        "thunder_badge",
        "Earned the Thunder Badge",
        "Vermilion City",
        "badge",
        _condition(badge=Badge.THUNDER),
    ),
    _definition(
        "entered_rock_tunnel",
        "Entered Rock Tunnel",
        "Toward Lavender",
        "landmark",
        _condition(maps=(PokemonRedMap.ROCK_TUNNEL_1F, PokemonRedMap.ROCK_TUNNEL_B1F)),
    ),
    _definition(
        "reached_lavender_town",
        "Reached Lavender Town",
        "Toward Lavender",
        "landmark",
        _condition(maps=(PokemonRedMap.LAVENDER_TOWN,)),
    ),
    _definition(
        "rainbow_badge",
        "Earned the Rainbow Badge",
        "Celadon and Lavender",
        "badge",
        _condition(badge=Badge.RAINBOW),
    ),
    _definition(
        "entered_rocket_hideout",
        "Entered the Rocket Hideout",
        "Celadon and Lavender",
        "landmark",
        _condition(
            maps=tuple(
                range(
                    int(PokemonRedMap.ROCKET_HIDEOUT_B1F),
                    int(PokemonRedMap.ROCKET_HIDEOUT_ELEVATOR) + 1,
                )
            )
        ),
    ),
    _definition(
        "obtained_lift_key",
        "Obtained the Lift Key",
        "Celadon and Lavender",
        "story",
        _condition(event=PokemonRedEvent.ROCKET_DROPPED_LIFT_KEY),
        _condition(items=(PokemonRedItem.LIFT_KEY,)),
    ),
    _definition(
        "defeated_rocket_hideout_giovanni",
        "Defeated Giovanni in the Rocket Hideout",
        "Celadon and Lavender",
        "story",
        _condition(event=PokemonRedEvent.BEAT_ROCKET_HIDEOUT_GIOVANNI),
    ),
    _definition(
        "obtained_silph_scope",
        "Obtained the Silph Scope",
        "Celadon and Lavender",
        "story",
        _condition(items=(PokemonRedItem.SILPH_SCOPE,)),
    ),
    _definition(
        "entered_pokemon_tower",
        "Entered Pokemon Tower",
        "Celadon and Lavender",
        "landmark",
        _condition(
            maps=tuple(
                range(
                    int(PokemonRedMap.POKEMON_TOWER_1F),
                    int(PokemonRedMap.POKEMON_TOWER_7F) + 1,
                )
            )
        ),
    ),
    _definition(
        "defeated_ghost_marowak",
        "Defeated the ghost Marowak",
        "Celadon and Lavender",
        "story",
        _condition(event=PokemonRedEvent.BEAT_GHOST_MAROWAK),
    ),
    _definition(
        "rescued_mr_fuji",
        "Rescued Mr. Fuji",
        "Celadon and Lavender",
        "story",
        _condition(event=PokemonRedEvent.RESCUED_MR_FUJI),
    ),
    _definition(
        "obtained_poke_flute",
        "Obtained the Poke Flute",
        "Celadon and Lavender",
        "story",
        _condition(event=PokemonRedEvent.GOT_POKE_FLUTE),
        _condition(items=(PokemonRedItem.POKE_FLUTE,)),
    ),
    _definition(
        "entered_silph_co",
        "Entered Silph Co.",
        "Saffron City",
        "landmark",
        _condition(maps=(PokemonRedMap.SILPH_CO_1F,)),
    ),
    _definition(
        "obtained_card_key",
        "Obtained the Card Key",
        "Saffron City",
        "story",
        _condition(items=(PokemonRedItem.CARD_KEY,)),
    ),
    _definition(
        "defeated_silph_giovanni",
        "Defeated Giovanni at Silph Co.",
        "Saffron City",
        "story",
        _condition(event=PokemonRedEvent.BEAT_SILPH_CO_GIOVANNI),
    ),
    _definition(
        "marsh_badge",
        "Earned the Marsh Badge",
        "Saffron City",
        "badge",
        _condition(badge=Badge.MARSH),
    ),
    _definition(
        "entered_safari_zone",
        "Entered the Safari Zone",
        "Fuchsia City",
        "landmark",
        _condition(maps=(PokemonRedMap.SAFARI_ZONE_EAST,)),
    ),
    _definition(
        "obtained_gold_teeth",
        "Obtained the Gold Teeth",
        "Fuchsia City",
        "story",
        _condition(items=(PokemonRedItem.GOLD_TEETH,)),
        _condition(event=PokemonRedEvent.GAVE_GOLD_TEETH),
    ),
    _definition(
        "obtained_surf",
        "Obtained HM03 Surf",
        "Fuchsia City",
        "story",
        _condition(event=PokemonRedEvent.GOT_HM03),
        _condition(items=(PokemonRedItem.HM03_SURF,)),
    ),
    _definition(
        "obtained_strength",
        "Obtained HM04 Strength",
        "Fuchsia City",
        "story",
        _condition(event=PokemonRedEvent.GOT_HM04),
        _condition(items=(PokemonRedItem.HM04_STRENGTH,)),
    ),
    _definition(
        "soul_badge",
        "Earned the Soul Badge",
        "Fuchsia City",
        "badge",
        _condition(badge=Badge.SOUL),
    ),
    _definition(
        "reached_cinnabar_island",
        "Reached Cinnabar Island",
        "Cinnabar Island",
        "landmark",
        _condition(maps=(PokemonRedMap.CINNABAR_ISLAND,)),
    ),
    _definition(
        "obtained_secret_key",
        "Obtained the Secret Key",
        "Cinnabar Island",
        "story",
        _condition(items=(PokemonRedItem.SECRET_KEY,)),
    ),
    _definition(
        "volcano_badge",
        "Earned the Volcano Badge",
        "Cinnabar Island",
        "badge",
        _condition(badge=Badge.VOLCANO),
    ),
    _definition(
        "earth_badge",
        "Earned the Earth Badge",
        "Viridian City",
        "badge",
        _condition(badge=Badge.EARTH),
    ),
    _definition(
        "reached_route_23",
        "Passed onto Route 23",
        "The Pokemon League",
        "landmark",
        _condition(maps=(PokemonRedMap.ROUTE_23,)),
    ),
    _definition(
        "entered_victory_road",
        "Entered Victory Road",
        "The Pokemon League",
        "landmark",
        _condition(
            maps=(
                PokemonRedMap.VICTORY_ROAD_1F,
                PokemonRedMap.VICTORY_ROAD_2F,
                PokemonRedMap.VICTORY_ROAD_3F,
            )
        ),
    ),
    _definition(
        "reached_indigo_plateau",
        "Reached Indigo Plateau",
        "The Pokemon League",
        "landmark",
        _condition(
            maps=(PokemonRedMap.INDIGO_PLATEAU, PokemonRedMap.INDIGO_PLATEAU_LOBBY)
        ),
    ),
    _definition(
        "defeated_lorelei",
        "Defeated Lorelei",
        "The Elite Four",
        "league",
        _condition(event=PokemonRedEvent.BEAT_LORELEI),
    ),
    _definition(
        "defeated_bruno",
        "Defeated Bruno",
        "The Elite Four",
        "league",
        _condition(event=PokemonRedEvent.BEAT_BRUNO),
    ),
    _definition(
        "defeated_agatha",
        "Defeated Agatha",
        "The Elite Four",
        "league",
        _condition(event=PokemonRedEvent.BEAT_AGATHA),
    ),
    _definition(
        "defeated_lance",
        "Defeated Lance",
        "The Elite Four",
        "league",
        _condition(event=PokemonRedEvent.BEAT_LANCE),
    ),
    _definition(
        "defeated_champion",
        "Defeated the Champion",
        "The Champion",
        "league",
        _condition(event=PokemonRedEvent.BEAT_CHAMPION_RIVAL),
    ),
    _definition(
        "hall_of_fame",
        "Entered the Hall of Fame",
        "Hall of Fame",
        "completion",
        _condition(
            event=PokemonRedEvent.BEAT_CHAMPION_RIVAL,
            maps=(PokemonRedMap.HALL_OF_FAME,),
        ),
    ),
)


MILESTONES = tuple(
    MilestoneDefinition(
        ordinal=ordinal,
        key=definition.key,
        label=definition.label,
        chapter=definition.chapter,
        kind=definition.kind,
        conditions=definition.conditions,
    )
    for ordinal, definition in enumerate(_UNORDERED_MILESTONES)
)
MILESTONE_BY_KEY = {milestone.key: milestone for milestone in MILESTONES}
HALL_OF_FAME_KEY = "hall_of_fame"

if len(MILESTONE_BY_KEY) != len(MILESTONES):
    raise RuntimeError("milestone keys must be unique")


@dataclass(slots=True)
class MilestoneTracker:
    """Monotonically accumulate named outcomes observed by the sealed referee."""

    observations: int = 0
    first_observed: dict[str, int] = field(default_factory=dict)

    def observe(self, state: PokemonRedState) -> tuple[MilestoneDefinition, ...]:
        self.observations += 1
        if not state.game_started:
            return ()
        new_milestones: list[MilestoneDefinition] = []
        for milestone in MILESTONES:
            if milestone.key not in self.first_observed and milestone.reached_by(state):
                self.first_observed[milestone.key] = self.observations
                new_milestones.append(milestone)
        return tuple(new_milestones)

    @property
    def reached(self) -> tuple[MilestoneDefinition, ...]:
        return tuple(
            milestone for milestone in MILESTONES if milestone.key in self.first_observed
        )

    @property
    def latest(self) -> MilestoneDefinition | None:
        return self.reached[-1] if self.reached else None

    @property
    def next_milestone(self) -> MilestoneDefinition | None:
        return next(
            (
                milestone
                for milestone in MILESTONES
                if milestone.key not in self.first_observed
            ),
            None,
        )

    @property
    def hall_of_fame_reached(self) -> bool:
        return HALL_OF_FAME_KEY in self.first_observed

    @property
    def completion_fraction(self) -> float:
        return len(self.first_observed) / len(MILESTONES)

    def public_dict(self) -> dict[str, object]:
        latest = self.latest
        next_milestone = self.next_milestone
        return {
            "schema_version": 1,
            "observations": self.observations,
            "reached_count": len(self.first_observed),
            "total_count": len(MILESTONES),
            "completion_fraction": self.completion_fraction,
            "latest": None if latest is None else latest.public_dict(),
            "next": None if next_milestone is None else next_milestone.public_dict(),
            "hall_of_fame_reached": self.hall_of_fame_reached,
            "reached": [
                {
                    **milestone.public_dict(),
                    "first_observation": self.first_observed[milestone.key],
                }
                for milestone in self.reached
            ],
        }

    def checkpoint_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "observations": self.observations,
            "first_observed": dict(sorted(self.first_observed.items())),
        }

    @classmethod
    def from_checkpoint_dict(cls, value: dict[str, Any] | None) -> MilestoneTracker:
        if not value:
            return cls()
        observations = int(value.get("observations", 0))
        if observations < 0:
            raise ValueError("milestone observation count cannot be negative")
        first_observed = {
            str(key): int(observation)
            for key, observation in value.get("first_observed", {}).items()
        }
        unknown = set(first_observed) - MILESTONE_BY_KEY.keys()
        if unknown:
            names = ", ".join(sorted(unknown))
            raise ValueError(f"unknown milestone keys in checkpoint: {names}")
        if any(
            observation < 1 or observation > observations
            for observation in first_observed.values()
        ):
            raise ValueError("milestone first-observation values must fit the observation count")
        return cls(observations=observations, first_observed=first_observed)
