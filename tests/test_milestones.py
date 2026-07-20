from __future__ import annotations

import pytest

from pokemon_red_ai.learning import RewardTracker
from pokemon_red_ai.milestones import (
    HALL_OF_FAME_KEY,
    MILESTONES,
    Badge,
    MilestoneTracker,
    PokemonRedEvent,
    PokemonRedItem,
    PokemonRedMap,
    event_flag_is_set,
)
from pokemon_red_ai.state import PokemonRedState

EVENT_FLAG_BYTES = 319


def event_flags(*events: PokemonRedEvent) -> bytes:
    result = bytearray(EVENT_FLAG_BYTES)
    for event in events:
        byte_index, bit = divmod(int(event), 8)
        result[byte_index] |= 1 << bit
    return bytes(result)


def state(
    *,
    map_id: int = int(PokemonRedMap.REDS_HOUSE_1F),
    party_count: int = 0,
    badges: Badge | int = 0,
    events: tuple[PokemonRedEvent, ...] = (),
    items: tuple[PokemonRedItem, ...] = (),
    got_pokedex: bool = False,
    game_started: bool = True,
) -> PokemonRedState:
    return PokemonRedState(
        game_started=game_started,
        map_id=map_id if game_started else None,
        player_y=0 if game_started else None,
        player_x=0 if game_started else None,
        party_count=party_count if game_started else None,
        battle_state=0 if game_started else None,
        badge_bits=int(badges) if game_started else None,
        event_flags=event_flags(*events) if game_started else None,
        bag_item_ids=tuple(int(item) for item in items) if game_started else None,
        got_pokedex=got_pokedex if game_started else None,
    )


def reached_keys(tracker: MilestoneTracker) -> set[str]:
    return {milestone.key for milestone in tracker.reached}


def test_catalog_is_stably_ordered_from_start_through_hall_of_fame() -> None:
    assert [milestone.ordinal for milestone in MILESTONES] == list(range(len(MILESTONES)))
    assert len({milestone.key for milestone in MILESTONES}) == len(MILESTONES)
    assert MILESTONES[0].key == "game_started"
    assert MILESTONES[-1].key == HALL_OF_FAME_KEY
    assert MILESTONES[-1].kind == "completion"


def test_catalog_names_mandatory_key_item_gates() -> None:
    required = {
        "entered_rocket_hideout",
        "obtained_lift_key",
        "obtained_silph_scope",
        "entered_pokemon_tower",
        "entered_silph_co",
        "obtained_card_key",
        "entered_safari_zone",
        "obtained_gold_teeth",
        "obtained_strength",
    }
    assert required.issubset({milestone.key for milestone in MILESTONES})

    tracker = MilestoneTracker()
    tracker.observe(
        state(
            items=(
                PokemonRedItem.LIFT_KEY,
                PokemonRedItem.SILPH_SCOPE,
                PokemonRedItem.CARD_KEY,
                PokemonRedItem.GOLD_TEETH,
                PokemonRedItem.HM04_STRENGTH,
            )
        )
    )
    assert {
        "obtained_lift_key",
        "obtained_silph_scope",
        "obtained_card_key",
        "obtained_gold_teeth",
        "obtained_strength",
    }.issubset(reached_keys(tracker))


def test_strength_gate_accepts_its_persistent_event_after_inventory_changes() -> None:
    tracker = MilestoneTracker()
    tracker.observe(state(events=(PokemonRedEvent.GOT_HM04,)))
    assert "obtained_strength" in reached_keys(tracker)


def test_event_flag_reader_handles_missing_and_short_state_without_false_positives() -> None:
    assert event_flag_is_set(None, int(PokemonRedEvent.GOT_STARTER)) is False
    assert event_flag_is_set(bytes(1), int(PokemonRedEvent.BEAT_CHAMPION_RIVAL)) is False
    assert event_flag_is_set(event_flags(PokemonRedEvent.GOT_STARTER), 0x022) is True
    with pytest.raises(ValueError, match="cannot be negative"):
        event_flag_is_set(bytes(1), -1)


def test_early_game_observations_become_named_monotonic_milestones() -> None:
    tracker = MilestoneTracker()

    assert tracker.observe(state(game_started=False)) == ()
    assert [item.key for item in tracker.observe(state())] == [
        "game_started",
        "left_bedroom",
    ]
    tracker.observe(state(map_id=PokemonRedMap.PALLET_TOWN))
    tracker.observe(
        state(
            map_id=0x28,
            party_count=1,
            events=(
                PokemonRedEvent.FOLLOWED_OAK_INTO_LAB,
                PokemonRedEvent.GOT_STARTER,
            ),
        )
    )
    tracker.observe(
        state(
            map_id=PokemonRedMap.VIRIDIAN_CITY,
            party_count=1,
            events=(
                PokemonRedEvent.FOLLOWED_OAK_INTO_LAB,
                PokemonRedEvent.GOT_STARTER,
                PokemonRedEvent.BATTLED_RIVAL_IN_OAKS_LAB,
                PokemonRedEvent.GOT_OAKS_PARCEL,
            ),
            items=(PokemonRedItem.OAKS_PARCEL,),
        )
    )
    tracker.observe(
        state(
            map_id=PokemonRedMap.PALLET_TOWN,
            party_count=1,
            events=(
                PokemonRedEvent.FOLLOWED_OAK_INTO_LAB,
                PokemonRedEvent.GOT_STARTER,
                PokemonRedEvent.BATTLED_RIVAL_IN_OAKS_LAB,
                PokemonRedEvent.GOT_OAKS_PARCEL,
                PokemonRedEvent.OAK_GOT_PARCEL,
                PokemonRedEvent.GOT_POKEDEX,
            ),
            got_pokedex=True,
        )
    )

    assert {
        "game_started",
        "left_bedroom",
        "left_home",
        "met_professor_oak",
        "chose_starter",
        "fought_lab_rival",
        "reached_viridian_city",
        "obtained_oaks_parcel",
        "delivered_oaks_parcel",
        "obtained_pokedex",
    }.issubset(reached_keys(tracker))
    assert tracker.first_observed["game_started"] == 2
    assert tracker.first_observed["left_home"] == 3


def test_viridian_mart_is_a_dense_checkpoint_before_oaks_parcel() -> None:
    tracker = MilestoneTracker()
    tracker.observe(state(map_id=PokemonRedMap.VIRIDIAN_CITY, party_count=1))
    newly_reached = tracker.observe(state(map_id=PokemonRedMap.VIRIDIAN_MART, party_count=1))
    assert [milestone.key for milestone in newly_reached][-1] == "entered_viridian_mart"

    parcel = tracker.observe(
        state(
            map_id=PokemonRedMap.VIRIDIAN_MART,
            party_count=1,
            events=(PokemonRedEvent.GOT_OAKS_PARCEL,),
            items=(PokemonRedItem.OAKS_PARCEL,),
        )
    )
    assert [milestone.key for milestone in parcel][-1] == "obtained_oaks_parcel"


def test_parcel_return_is_split_into_monotonic_backtracking_checkpoints() -> None:
    tracker = MilestoneTracker()
    parcel_state = {
        "party_count": 1,
        "events": (PokemonRedEvent.GOT_OAKS_PARCEL,),
        "items": (PokemonRedItem.OAKS_PARCEL,),
    }
    tracker.observe(state(map_id=PokemonRedMap.VIRIDIAN_MART, **parcel_state))
    route = tracker.observe(state(map_id=PokemonRedMap.ROUTE_1, **parcel_state))
    pallet = tracker.observe(state(map_id=PokemonRedMap.PALLET_TOWN, **parcel_state))
    lab = tracker.observe(state(map_id=PokemonRedMap.OAKS_LAB, **parcel_state))

    assert route[-1].key == "returned_to_route_1_with_parcel"
    assert pallet[-1].key == "returned_to_pallet_town_with_parcel"
    assert lab[-1].key == "entered_oaks_lab_with_parcel"

    without_parcel = MilestoneTracker()
    without_parcel.observe(state(map_id=PokemonRedMap.ROUTE_1, party_count=1))
    assert "returned_to_route_1_with_parcel" not in reached_keys(without_parcel)


def test_badges_are_named_individually_without_inventing_missing_badges() -> None:
    tracker = MilestoneTracker()
    tracker.observe(state(badges=Badge.EARTH))

    assert "earth_badge" in reached_keys(tracker)
    assert "boulder_badge" not in reached_keys(tracker)
    assert "cascade_badge" not in reached_keys(tracker)
    assert tracker.latest is not None
    assert tracker.latest.key == "earth_badge"


def test_hall_of_fame_requires_champion_flag_and_hall_map_together() -> None:
    champion_only = MilestoneTracker()
    champion_only.observe(
        state(
            map_id=PokemonRedMap.CHAMPIONS_ROOM,
            events=(PokemonRedEvent.BEAT_CHAMPION_RIVAL,),
        )
    )
    assert "defeated_champion" in reached_keys(champion_only)
    assert champion_only.hall_of_fame_reached is False

    map_only = MilestoneTracker()
    map_only.observe(state(map_id=PokemonRedMap.HALL_OF_FAME))
    assert map_only.hall_of_fame_reached is False

    completed = MilestoneTracker()
    newly_reached = completed.observe(
        state(
            map_id=PokemonRedMap.HALL_OF_FAME,
            events=(PokemonRedEvent.BEAT_CHAMPION_RIVAL,),
        )
    )
    assert [milestone.key for milestone in newly_reached][-2:] == [
        "defeated_champion",
        "hall_of_fame",
    ]
    assert completed.hall_of_fame_reached is True
    assert completed.public_dict()["hall_of_fame_reached"] is True


def test_transient_hall_of_fame_dex_rating_bit_is_not_completion_evidence() -> None:
    tracker = MilestoneTracker()
    tracker.observe(
        state(
            map_id=PokemonRedMap.PALLET_TOWN,
            events=(PokemonRedEvent.HALL_OF_FAME_DEX_RATING,),
        )
    )
    assert tracker.hall_of_fame_reached is False


def test_milestone_checkpoint_round_trip_and_validation() -> None:
    tracker = MilestoneTracker()
    tracker.observe(state())
    tracker.observe(state(map_id=PokemonRedMap.PALLET_TOWN))

    restored = MilestoneTracker.from_checkpoint_dict(tracker.checkpoint_dict())

    assert restored.observations == tracker.observations
    assert restored.first_observed == tracker.first_observed
    assert restored.public_dict() == tracker.public_dict()

    invalid = tracker.checkpoint_dict()
    invalid["first_observed"]["not_a_real_milestone"] = 1
    with pytest.raises(ValueError, match="unknown milestone"):
        MilestoneTracker.from_checkpoint_dict(invalid)


def test_reward_tracker_records_milestones_without_changing_reward_components() -> None:
    tracker = RewardTracker("observer")
    observation = state(map_id=PokemonRedMap.PALLET_TOWN)

    reward, components = tracker.score(visually_novel=False, state=observation)

    assert reward == 0
    assert components == {}
    assert reached_keys(tracker.milestone_tracker) == {"game_started", "left_home"}

    restored = RewardTracker.from_checkpoint_dict(tracker.checkpoint_dict())
    assert restored.milestone_tracker.public_dict() == tracker.milestone_tracker.public_dict()

    old_checkpoint = tracker.checkpoint_dict()
    old_checkpoint.pop("named_milestones")
    old_restored = RewardTracker.from_checkpoint_dict(old_checkpoint)
    assert old_restored.milestone_tracker.observations == 0
