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
