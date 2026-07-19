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

    IS_IN_BATTLE = 0xD057
    PARTY_COUNT = 0xD163
    CURRENT_MAP = 0xD35E
    PLAYER_Y = 0xD361
    PLAYER_X = 0xD362
    STATUS_FLAGS_6 = 0xD732


GAME_TIMER_COUNTING_MASK = 0x01


@dataclass(frozen=True, slots=True)
class PokemonRedState:
    """A versioned, read-only view of a few documented game-state fields."""

    game_started: bool
    map_id: int | None
    player_y: int | None
    player_x: int | None
    party_count: int | None
    battle_state: int | None

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
            )
        return PokemonRedState(
            game_started=True,
            map_id=self._memory.read_u8(RamAddress.CURRENT_MAP),
            player_y=self._memory.read_u8(RamAddress.PLAYER_Y),
            player_x=self._memory.read_u8(RamAddress.PLAYER_X),
            party_count=self._memory.read_u8(RamAddress.PARTY_COUNT),
            battle_state=self._memory.read_u8(RamAddress.IS_IN_BATTLE),
        )
