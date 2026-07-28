from __future__ import annotations

import random

from pokemon_red_ai.consolidation import (
    BackwardConsolidation,
    choose_consolidation_entry,
)


def entries(*indices: int) -> list[dict[str, int | str]]:
    return [
        {
            "entry_id": f"entry-{index}",
            "milestone_index": index,
        }
        for index in indices
    ]


def test_backward_gate_ignores_frontier_practice_and_expands_one_rung() -> None:
    state = BackwardConsolidation.initialize(
        entries(0, 3, 5),
        window_size=10,
        threshold=0.8,
    )
    assert state.target_index == 5
    assert state.active_start_index == 3

    ignored = state.record_episode(
        start_mode="frontier",
        start_index=5,
        target_index=5,
        best_reached_index=5,
    )
    assert ignored is False
    assert state.active_window == ()

    results = [False, False, *([True] * 8)]
    for result in results[:-1]:
        assert (
            state.record_episode(
                start_mode="consolidation",
                start_index=3,
                target_index=5,
                best_reached_index=5 if result else 4,
            )
            is False
        )
    assert state.record_episode(
        start_mode="consolidation",
        start_index=3,
        target_index=5,
        best_reached_index=5,
    )
    assert state.active_start_index == 0
    assert len(state.gates_passed) == 1
    assert state.power_on_training_gate_passed is False


def test_power_on_training_gate_and_round_trip_are_explicit() -> None:
    state = BackwardConsolidation.initialize(
        entries(0, 2),
        window_size=5,
        threshold=0.8,
    )
    for best in (2, 2, 2, 1):
        assert not state.record_episode(
            start_mode="consolidation",
            start_index=0,
            target_index=2,
            best_reached_index=best,
        )
    assert state.record_episode(
        start_mode="consolidation",
        start_index=0,
        target_index=2,
        best_reached_index=2,
    )
    assert state.power_on_training_gate_passed is True
    assert not state.record_episode(
        start_mode="consolidation",
        start_index=0,
        target_index=2,
        best_reached_index=2,
    )
    assert len(state.gates_passed) == 1

    restored = BackwardConsolidation.from_dict(state.public_dict())
    assert restored.target_index == state.target_index
    assert restored.active_start_index == state.active_start_index
    assert restored.gates_passed == state.gates_passed
    assert restored.power_on_training_gate_passed is True


def test_new_promotion_resets_target_to_the_preceding_verified_frontier() -> None:
    state = BackwardConsolidation.initialize(
        entries(0, 3, 5),
        window_size=10,
        threshold=0.8,
    )
    state.active_start_index = 0

    assert state.sync_curriculum(entries(0, 3, 5, 6)) is True
    assert state.target_index == 6
    assert state.active_start_index == 5
    assert state.power_on_training_gate_passed is False


def test_entry_selection_separates_frontier_and_consolidation_episodes() -> None:
    curriculum = entries(0, 3, 5)
    state = BackwardConsolidation.initialize(
        curriculum,
        window_size=10,
        threshold=0.8,
    )

    frontier, frontier_mode, target = choose_consolidation_entry(
        curriculum,
        state,
        random.Random(1),
        frontier_probability=1,
    )
    consolidation, consolidation_mode, same_target = choose_consolidation_entry(
        curriculum,
        state,
        random.Random(1),
        frontier_probability=0,
    )

    assert frontier["milestone_index"] == 5
    assert frontier_mode == "frontier"
    assert consolidation["milestone_index"] == 3
    assert consolidation_mode == "consolidation"
    assert target == same_target == 5
