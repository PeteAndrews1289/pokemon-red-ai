from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from typing import Protocol


class ReadOnlyMemory(Protocol):
    """The deliberately small memory interface available to state adapters."""

    def read_u8(self, address: int) -> int: ...


class RamAddress(IntEnum):
    """Verified WRAM symbols for the supported Pokemon Red revision.

    The addresses were generated from pret/pokered commit
    1e96034092686d006e863cace09e87273051a3d8 and checked against a build with
    the same SHA-1 as the supported ROM.
    """

    ENEMY_MON_HP = 0xCFE6
    ENEMY_MON_MAX_HP = 0xCFF4
    IS_IN_BATTLE = 0xD057
    PARTY_COUNT = 0xD163
    PARTY_SPECIES = 0xD164
    PARTY_MONS = 0xD16B
    POKEDEX_OWNED = 0xD2F7
    POKEDEX_SEEN = 0xD30A
    NUM_BAG_ITEMS = 0xD31D
    BAG_ITEMS = 0xD31E
    OBTAINED_BADGES = 0xD356
    CURRENT_MAP = 0xD35E
    PLAYER_Y = 0xD361
    PLAYER_X = 0xD362
    STATUS_FLAGS_6 = 0xD732
    EVENT_FLAGS = 0xD747
    VIRIDIAN_MART_SCRIPT = 0xD60D


GAME_TIMER_COUNTING_MASK = 0x01
PARTY_LENGTH = 6
PARTY_MON_STRUCT_LENGTH = 44
PARTY_MON_HP_OFFSET = 1
PARTY_MON_MAX_HP_OFFSET = 34
PARTY_MON_MOVES_OFFSET = 8
PARTY_MON_EXPERIENCE_OFFSET = 14
PARTY_MON_EXPERIENCE_LENGTH = 3
PARTY_MON_LEVEL_OFFSET = 33
POKEDEX_BYTES = 19
MAX_BAG_ITEMS = 20
EVENT_FLAGS_END = 0xD886
GOT_POKEDEX_ADDRESS = 0xD74B
GOT_POKEDEX_MASK = 1 << 5


@dataclass(frozen=True, slots=True)
class PokemonRedState:
    """A versioned, read-only view of a few documented game-state fields."""

    game_started: bool
    map_id: int | None
    player_y: int | None
    player_x: int | None
    party_count: int | None
    battle_state: int | None
    badge_bits: int | None = None
    party_species: tuple[int, ...] | None = None
    party_levels: tuple[int, ...] | None = None
    party_moves: tuple[int, ...] | None = None
    pokedex_owned: bytes | None = None
    pokedex_seen: bytes | None = None
    event_flags: bytes | None = None
    bag_item_ids: tuple[int, ...] | None = None
    got_pokedex: bool | None = None
    party_experience: tuple[int, ...] | None = None
    party_hp: tuple[int, ...] | None = None
    party_max_hp: tuple[int, ...] | None = None
    enemy_hp: int | None = None
    enemy_max_hp: int | None = None
    viridian_mart_script: int | None = None

    @property
    def badge_count(self) -> int:
        return 0 if self.badge_bits is None else self.badge_bits.bit_count()

    @property
    def battle_kind(self) -> str:
        if self.battle_state is None:
            return "unavailable"
        return {
            0: "none",
            1: "wild",
            2: "trainer",
            0xFF: "lost",
        }.get(self.battle_state, "unknown")

    @staticmethod
    def _bit_count(value: bytes | None) -> int:
        return 0 if value is None else sum(byte.bit_count() for byte in value)

    @property
    def pokedex_owned_count(self) -> int:
        return self._bit_count(self.pokedex_owned)

    @property
    def pokedex_seen_count(self) -> int:
        return self._bit_count(self.pokedex_seen)

    @property
    def event_flags_count(self) -> int:
        return self._bit_count(self.event_flags)

    @property
    def max_party_level(self) -> int:
        return max(self.party_levels or (), default=0)

    @property
    def total_party_experience(self) -> int:
        return sum(self.party_experience or ())

    @property
    def current_party_hp(self) -> int:
        return sum(self.party_hp or ())

    @property
    def maximum_party_hp(self) -> int:
        return sum(self.party_max_hp or ())

    @property
    def party_hp_fraction(self) -> float:
        return self.current_party_hp / max(1, self.maximum_party_hp)

    def public_dict(self) -> dict[str, object]:
        return {
            "schema_version": 1,
            "game_started": self.game_started,
            "map_id": self.map_id,
            "coordinates": (
                {"x": self.player_x, "y": self.player_y} if self.game_started else None
            ),
            "party_count": self.party_count,
            "battle_state": self.battle_state,
            "battle_kind": self.battle_kind,
            "badge_bits": self.badge_bits,
            "badge_count": self.badge_count,
            "party_species": list(self.party_species or ()),
            "party_levels": list(self.party_levels or ()),
            "party_experience": list(self.party_experience or ()),
            "total_party_experience": self.total_party_experience,
            "max_party_level": self.max_party_level,
            "party_hp": list(self.party_hp or ()),
            "party_max_hp": list(self.party_max_hp or ()),
            "party_hp_fraction": self.party_hp_fraction,
            "enemy_hp": self.enemy_hp,
            "enemy_max_hp": self.enemy_max_hp,
            "viridian_mart_script": self.viridian_mart_script,
            "pokedex_seen_count": self.pokedex_seen_count,
            "pokedex_owned_count": self.pokedex_owned_count,
            "event_flags_count": self.event_flags_count,
            "bag_item_count": len(self.bag_item_ids or ()),
            "got_pokedex": self.got_pokedex,
        }


class PokemonRedStateReader:
    """Translate named WRAM bytes into a stable observation without mutation."""

    def __init__(self, memory: ReadOnlyMemory) -> None:
        self._memory = memory

    def read(self) -> PokemonRedState:
        status_flags_6 = self._memory.read_u8(RamAddress.STATUS_FLAGS_6)
        game_started = bool(status_flags_6 & GAME_TIMER_COUNTING_MASK)
        if not game_started:
            return PokemonRedState(
                game_started=False,
                map_id=None,
                player_y=None,
                player_x=None,
                party_count=None,
                battle_state=None,
                badge_bits=None,
            )
        party_count = min(self._memory.read_u8(RamAddress.PARTY_COUNT), PARTY_LENGTH)
        party_species = tuple(
            self._memory.read_u8(int(RamAddress.PARTY_SPECIES) + index)
            for index in range(party_count)
        )
        party_levels = tuple(
            self._memory.read_u8(
                int(RamAddress.PARTY_MONS)
                + index * PARTY_MON_STRUCT_LENGTH
                + PARTY_MON_LEVEL_OFFSET
            )
            for index in range(party_count)
        )
        party_experience = tuple(
            sum(
                self._memory.read_u8(
                    int(RamAddress.PARTY_MONS)
                    + index * PARTY_MON_STRUCT_LENGTH
                    + PARTY_MON_EXPERIENCE_OFFSET
                    + offset
                )
                << (8 * (PARTY_MON_EXPERIENCE_LENGTH - offset - 1))
                for offset in range(PARTY_MON_EXPERIENCE_LENGTH)
            )
            for index in range(party_count)
        )
        party_hp = tuple(
            self._read_u16_be(
                int(RamAddress.PARTY_MONS)
                + index * PARTY_MON_STRUCT_LENGTH
                + PARTY_MON_HP_OFFSET
            )
            for index in range(party_count)
        )
        party_max_hp = tuple(
            self._read_u16_be(
                int(RamAddress.PARTY_MONS)
                + index * PARTY_MON_STRUCT_LENGTH
                + PARTY_MON_MAX_HP_OFFSET
            )
            for index in range(party_count)
        )
        party_moves = tuple(
            move
            for index in range(party_count)
            for offset in range(4)
            if (
                move := self._memory.read_u8(
                    int(RamAddress.PARTY_MONS)
                    + index * PARTY_MON_STRUCT_LENGTH
                    + PARTY_MON_MOVES_OFFSET
                    + offset
                )
            )
        )
        pokedex_owned = bytes(
            self._memory.read_u8(int(RamAddress.POKEDEX_OWNED) + index)
            for index in range(POKEDEX_BYTES)
        )
        pokedex_seen = bytes(
            self._memory.read_u8(int(RamAddress.POKEDEX_SEEN) + index)
            for index in range(POKEDEX_BYTES)
        )
        event_flags = bytes(
            self._memory.read_u8(int(RamAddress.EVENT_FLAGS) + index)
            for index in range(EVENT_FLAGS_END - int(RamAddress.EVENT_FLAGS))
        )
        bag_item_count = min(self._memory.read_u8(RamAddress.NUM_BAG_ITEMS), MAX_BAG_ITEMS)
        bag_item_ids = tuple(
            self._memory.read_u8(int(RamAddress.BAG_ITEMS) + index * 2)
            for index in range(bag_item_count)
        )
        current_map = self._memory.read_u8(RamAddress.CURRENT_MAP)
        battle_state = self._memory.read_u8(RamAddress.IS_IN_BATTLE)
        in_battle = battle_state in {1, 2}
        return PokemonRedState(
            game_started=True,
            map_id=current_map,
            player_y=self._memory.read_u8(RamAddress.PLAYER_Y),
            player_x=self._memory.read_u8(RamAddress.PLAYER_X),
            party_count=party_count,
            battle_state=battle_state,
            badge_bits=self._memory.read_u8(RamAddress.OBTAINED_BADGES),
            party_species=party_species,
            party_levels=party_levels,
            party_experience=party_experience,
            party_moves=party_moves,
            pokedex_owned=pokedex_owned,
            pokedex_seen=pokedex_seen,
            event_flags=event_flags,
            bag_item_ids=bag_item_ids,
            got_pokedex=bool(self._memory.read_u8(GOT_POKEDEX_ADDRESS) & GOT_POKEDEX_MASK),
            party_hp=party_hp,
            party_max_hp=party_max_hp,
            enemy_hp=(self._read_u16_be(RamAddress.ENEMY_MON_HP) if in_battle else None),
            enemy_max_hp=(
                self._read_u16_be(RamAddress.ENEMY_MON_MAX_HP) if in_battle else None
            ),
            viridian_mart_script=(
                self._memory.read_u8(RamAddress.VIRIDIAN_MART_SCRIPT)
                if current_map == 0x2A else None
            ),
        )

    def _read_u16_be(self, address: int) -> int:
        return (self._memory.read_u8(int(address)) << 8) | self._memory.read_u8(
            int(address) + 1
        )
