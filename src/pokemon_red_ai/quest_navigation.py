from __future__ import annotations

from collections import deque
from collections.abc import Iterable
from dataclasses import dataclass

from pokemon_red_ai.expedition import MilestoneProgress
from pokemon_red_ai.milestones import MILESTONES, PokemonRedMap
from pokemon_red_ai.state import PokemonRedState


@dataclass(frozen=True, slots=True)
class RouteGuidance:
    """A trainer-visible next goal and shortest certified map route."""

    goal_key: str | None
    target_maps: tuple[int, ...]
    next_map: int | None
    distance: int | None


# These are not a walkthrough of the future game. Each edge is an opening-game transition already
# verified by the curriculum lineage. Edges are deliberately usable in both directions: once a
# route has been demonstrated, the assisted teacher should not pretend the reverse trip is unknown.
CERTIFIED_MAP_EDGES = frozenset(
    {
        (int(PokemonRedMap.REDS_HOUSE_1F), int(PokemonRedMap.PALLET_TOWN)),
        (int(PokemonRedMap.PALLET_TOWN), int(PokemonRedMap.OAKS_LAB)),
        (int(PokemonRedMap.PALLET_TOWN), int(PokemonRedMap.ROUTE_1)),
        (int(PokemonRedMap.ROUTE_1), int(PokemonRedMap.VIRIDIAN_CITY)),
        (int(PokemonRedMap.VIRIDIAN_CITY), int(PokemonRedMap.VIRIDIAN_MART)),
    }
)


# Story and interaction goals do not always carry a map condition. These locations are disclosed
# only after the corresponding place has already entered the verified curriculum.
STORY_GOAL_MAPS: dict[str, tuple[int, ...]] = {
    "met_professor_oak": (int(PokemonRedMap.OAKS_LAB),),
    "chose_starter": (int(PokemonRedMap.OAKS_LAB),),
    "fought_lab_rival": (int(PokemonRedMap.OAKS_LAB),),
    "obtained_oaks_parcel": (int(PokemonRedMap.VIRIDIAN_MART),),
    "delivered_oaks_parcel": (int(PokemonRedMap.OAKS_LAB),),
    "obtained_pokedex": (int(PokemonRedMap.OAKS_LAB),),
}


def active_goal(progress: MilestoneProgress) -> str | None:
    """Return the next canonical milestone after inherited monotonic progress."""

    if not 0 <= progress.index < len(MILESTONES):
        return None
    return MILESTONES[progress.index].key


def goal_target_maps(progress: MilestoneProgress) -> tuple[int, ...]:
    goal_key = active_goal(progress)
    if goal_key is None:
        return ()
    milestone = MILESTONES[progress.index]
    conditioned = {
        int(map_id)
        for condition in milestone.conditions
        for map_id in condition.map_ids
    }
    return tuple(sorted(conditioned)) or STORY_GOAL_MAPS.get(goal_key, ())


def _graph(
    observed_edges: Iterable[tuple[int, int]],
) -> dict[int, set[int]]:
    adjacency: dict[int, set[int]] = {}
    for first, second in (*CERTIFIED_MAP_EDGES, *tuple(observed_edges)):
        first, second = int(first), int(second)
        adjacency.setdefault(first, set()).add(second)
        adjacency.setdefault(second, set()).add(first)
    return adjacency


def route_guidance(
    state: PokemonRedState,
    progress: MilestoneProgress,
    observed_edges: Iterable[tuple[int, int]] = (),
) -> RouteGuidance:
    """Find the next map on a shortest route assembled from certified and observed edges."""

    goal_key = active_goal(progress)
    targets = goal_target_maps(progress)
    if state.map_id is None or not targets:
        return RouteGuidance(goal_key, targets, None, None)
    start = int(state.map_id)
    if start in targets:
        return RouteGuidance(goal_key, targets, start, 0)

    adjacency = _graph(observed_edges)
    queue: deque[tuple[int, tuple[int, ...]]] = deque(((start, (start,)),))
    visited = {start}
    while queue:
        current, path = queue.popleft()
        for neighbor in sorted(adjacency.get(current, ())):
            if neighbor in visited:
                continue
            next_path = (*path, neighbor)
            if neighbor in targets:
                return RouteGuidance(goal_key, targets, next_path[1], len(next_path) - 1)
            visited.add(neighbor)
            queue.append((neighbor, next_path))
    return RouteGuidance(goal_key, targets, None, None)
