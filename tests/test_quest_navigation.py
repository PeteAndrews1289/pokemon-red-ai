from __future__ import annotations

from pokemon_red_ai.expedition import MilestoneProgress
from pokemon_red_ai.milestones import PokemonRedMap
from pokemon_red_ai.quest_navigation import active_goal, route_guidance
from pokemon_red_ai.state import PokemonRedState


def test_parcel_goal_reuses_verified_route_in_reverse() -> None:
    parcel = MilestoneProgress("obtained_oaks_parcel", 10, "Obtained Oak's Parcel")
    state = PokemonRedState(True, int(PokemonRedMap.VIRIDIAN_MART), 6, 4, 1, 0)

    guidance = route_guidance(state, parcel)

    assert active_goal(parcel) == "returned_to_route_1_with_parcel"
    assert guidance.target_maps == (int(PokemonRedMap.ROUTE_1),)
    assert guidance.next_map == int(PokemonRedMap.VIRIDIAN_CITY)
    assert guidance.distance == 2


def test_observed_edges_extend_the_certified_route_without_future_walkthrough_data() -> None:
    route = MilestoneProgress(
        "returned_to_route_1_with_parcel",
        11,
        "Returned to Route 1 with Oak's Parcel",
    )
    state = PokemonRedState(True, 0xEE, 1, 1, 1, 0)

    unknown = route_guidance(state, route)
    learned = route_guidance(
        state,
        route,
        observed_edges=((0xEE, int(PokemonRedMap.ROUTE_1)),),
    )

    assert unknown.distance is None
    assert learned.next_map == int(PokemonRedMap.ROUTE_1)
    assert learned.distance == 2


def test_pokedex_to_pewter_curriculum_exposes_one_map_at_a_time() -> None:
    cases = (
        (
            "obtained_pokedex",
            15,
            "Received the Pokedex",
            PokemonRedMap.OAKS_LAB,
            "left_oaks_lab_with_pokedex",
            PokemonRedMap.PALLET_TOWN,
            1,
        ),
        (
            "left_oaks_lab_with_pokedex",
            16,
            "Left Oak's Lab with the Pokedex",
            PokemonRedMap.PALLET_TOWN,
            "returned_to_route_1_with_pokedex",
            PokemonRedMap.ROUTE_1,
            1,
        ),
        (
            "returned_to_route_1_with_pokedex",
            17,
            "Returned to Route 1 with the Pokedex",
            PokemonRedMap.ROUTE_1,
            "returned_to_viridian_city_with_pokedex",
            PokemonRedMap.VIRIDIAN_CITY,
            1,
        ),
        (
            "returned_to_viridian_city_with_pokedex",
            18,
            "Returned to Viridian City with the Pokedex",
            PokemonRedMap.VIRIDIAN_CITY,
            "reached_route_2_with_pokedex",
            PokemonRedMap.ROUTE_2,
            1,
        ),
        (
            "reached_route_2_with_pokedex",
            19,
            "Reached Route 2 with the Pokedex",
            PokemonRedMap.ROUTE_2,
            "entered_viridian_forest_south_gate",
            PokemonRedMap.VIRIDIAN_FOREST_SOUTH_GATE,
            1,
        ),
        (
            "entered_viridian_forest_south_gate",
            20,
            "Entered the Viridian Forest south gate",
            PokemonRedMap.VIRIDIAN_FOREST_SOUTH_GATE,
            "reached_viridian_forest",
            PokemonRedMap.VIRIDIAN_FOREST,
            1,
        ),
        (
            "reached_viridian_forest",
            21,
            "Entered Viridian Forest",
            PokemonRedMap.VIRIDIAN_FOREST,
            "crossed_viridian_forest",
            PokemonRedMap.VIRIDIAN_FOREST_NORTH_GATE,
            1,
        ),
        (
            "crossed_viridian_forest",
            22,
            "Reached the Viridian Forest north gate",
            PokemonRedMap.VIRIDIAN_FOREST_NORTH_GATE,
            "reached_pewter_city",
            PokemonRedMap.ROUTE_2,
            2,
        ),
        (
            "reached_pewter_city",
            23,
            "Reached Pewter City",
            PokemonRedMap.PEWTER_CITY,
            "entered_pewter_gym",
            PokemonRedMap.PEWTER_GYM,
            1,
        ),
    )

    for key, index, label, current_map, goal, next_map, distance in cases:
        progress = MilestoneProgress(key, index, label)
        guidance = route_guidance(
            PokemonRedState(True, int(current_map), 1, 1, 1, 0),
            progress,
        )
        assert active_goal(progress) == goal
        assert guidance.next_map == int(next_map)
        assert guidance.distance == distance
