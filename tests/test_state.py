from __future__ import annotations

from pokemon_red_ai.state import PokemonRedState, PokemonRedStateReader, RamAddress


class RecordingMemory:
    def __init__(self, values: dict[int, int]) -> None:
        self.values = values
        self.reads: list[int] = []

    def read_u8(self, address: int) -> int:
        self.reads.append(address)
        return self.values.get(int(address), 0)


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

    assert state.game_started
    assert state.map_id == 0x26
    assert state.party_count == 0
    assert state.battle_kind == "none"
    assert state.badge_count == 2
    assert state.public_dict()["coordinates"] == {"x": 3, "y": 6}
    assert memory.reads[0] == RamAddress.STATUS_FLAGS_6
    assert RamAddress.CURRENT_MAP in memory.reads
    assert RamAddress.PLAYER_Y in memory.reads
    assert RamAddress.PLAYER_X in memory.reads
    assert RamAddress.PARTY_COUNT in memory.reads
    assert RamAddress.POKEDEX_OWNED in memory.reads
    assert RamAddress.IS_IN_BATTLE in memory.reads
    assert RamAddress.OBTAINED_BADGES in memory.reads


def test_state_reader_exposes_collection_and_party_progress() -> None:
    memory = RecordingMemory(
        {
            RamAddress.STATUS_FLAGS_6: 1,
            RamAddress.PARTY_COUNT: 1,
            RamAddress.PARTY_SPECIES: 0xB0,
            RamAddress.PARTY_MONS + 8: 33,
            RamAddress.PARTY_MONS + 9: 45,
            RamAddress.PARTY_MONS + 14: 0x01,
            RamAddress.PARTY_MONS + 15: 0x02,
            RamAddress.PARTY_MONS + 16: 0x03,
            RamAddress.PARTY_MONS + 33: 12,
            RamAddress.PARTY_MONS + 1: 0x00,
            RamAddress.PARTY_MONS + 2: 0x1A,
            RamAddress.PARTY_MONS + 34: 0x00,
            RamAddress.PARTY_MONS + 35: 0x27,
            RamAddress.POKEDEX_OWNED: 0b00000001,
            RamAddress.POKEDEX_SEEN: 0b00000101,
            RamAddress.NUM_BAG_ITEMS: 2,
            RamAddress.BAG_ITEMS: 0x04,
            RamAddress.BAG_ITEMS + 2: 0x46,
            0xD74B: 1 << 5,
        }
    )

    state = PokemonRedStateReader(memory).read()

    assert state.party_species == (0xB0,)
    assert state.party_levels == (12,)
    assert state.party_experience == (0x010203,)
    assert state.total_party_experience == 0x010203
    assert state.party_hp == (26,)
    assert state.party_max_hp == (39,)
    assert state.party_hp_fraction == 26 / 39
    assert state.party_moves == (33, 45)
    assert state.pokedex_seen_count == 2
    assert state.pokedex_owned_count == 1
    assert state.bag_item_ids == (0x04, 0x46)
    assert state.got_pokedex is True


def test_state_reader_exposes_enemy_health_only_during_battle() -> None:
    values = {
        RamAddress.STATUS_FLAGS_6: 1,
        RamAddress.IS_IN_BATTLE: 1,
        RamAddress.ENEMY_MON_HP: 0,
        RamAddress.ENEMY_MON_HP + 1: 17,
        RamAddress.ENEMY_MON_MAX_HP: 0,
        RamAddress.ENEMY_MON_MAX_HP + 1: 24,
    }
    state = PokemonRedStateReader(RecordingMemory(values)).read()
    assert (state.enemy_hp, state.enemy_max_hp) == (17, 24)

    values[RamAddress.IS_IN_BATTLE] = 0
    outside = PokemonRedStateReader(RecordingMemory(values)).read()
    assert outside.enemy_hp is None
    assert outside.enemy_max_hp is None


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
