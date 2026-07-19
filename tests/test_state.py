from __future__ import annotations

from pokemon_red_ai.state import PokemonRedState, PokemonRedStateReader, RamAddress


class RecordingMemory:
    def __init__(self, values: dict[int, int]) -> None:
        self.values = values
        self.reads: list[int] = []

    def read_u8(self, address: int) -> int:
        self.reads.append(address)
        return self.values[int(address)]


def test_state_reader_exposes_named_read_only_fields() -> None:
    memory = RecordingMemory(
        {
            RamAddress.STATUS_FLAGS_6: 0x01,
            RamAddress.CURRENT_MAP: 0x26,
            RamAddress.PLAYER_Y: 6,
            RamAddress.PLAYER_X: 3,
            RamAddress.PARTY_COUNT: 0,
            RamAddress.IS_IN_BATTLE: 0,
            RamAddress.OBTAINED_BADGES: 0b00000101,
        }
    )

    state = PokemonRedStateReader(memory).read()

    assert state == PokemonRedState(True, 0x26, 6, 3, 0, 0, 0b00000101)
    assert state.battle_kind == "none"
    assert state.badge_count == 2
    assert state.public_dict()["coordinates"] == {"x": 3, "y": 6}
    assert memory.reads == [
        RamAddress.STATUS_FLAGS_6,
        RamAddress.CURRENT_MAP,
        RamAddress.PLAYER_Y,
        RamAddress.PLAYER_X,
        RamAddress.PARTY_COUNT,
        RamAddress.IS_IN_BATTLE,
        RamAddress.OBTAINED_BADGES,
    ]


def test_unknown_battle_state_is_preserved() -> None:
    state = PokemonRedState(True, 0, 0, 0, 0, 17)
    assert state.battle_kind == "unknown"
    assert state.public_dict()["battle_state"] == 17


def test_state_reader_hides_pre_game_scratch_values() -> None:
    memory = RecordingMemory({RamAddress.STATUS_FLAGS_6: 0x00})

    state = PokemonRedStateReader(memory).read()

    assert state == PokemonRedState(False, None, None, None, None, None)
    assert state.battle_kind == "unavailable"
    assert state.public_dict()["coordinates"] is None
    assert memory.reads == [RamAddress.STATUS_FLAGS_6]
