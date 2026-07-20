from __future__ import annotations

import hashlib
import json
import random
from pathlib import Path

import numpy as np
import pytest

from pokemon_red_ai.apprentice_model import build_apprentice_policy, require_torch
from pokemon_red_ai.expedition import MilestoneProgress
from pokemon_red_ai.frontier_learning import (
    FrontierSelfImitationEmitter,
    FullGameRewardTracker,
    _parameter_sha256,
)
from pokemon_red_ai.state import PokemonRedState


def state(**changes: object) -> PokemonRedState:
    values: dict[str, object] = {
        "game_started": True,
        "map_id": 0,
        "player_y": 5,
        "player_x": 5,
        "party_count": 1,
        "battle_state": 0,
        "badge_bits": 0,
        "party_species": (1,),
        "party_levels": (5,),
        "party_experience": (125,),
        "party_moves": (33,),
        "pokedex_owned": bytes(19),
        "pokedex_seen": bytes(19),
        "event_flags": bytes(319),
        "bag_item_ids": (),
        "got_pokedex": True,
        "party_hp": (20,),
        "party_max_hp": (20,),
        "enemy_hp": None,
        "enemy_max_hp": None,
        "viridian_mart_script": None,
    }
    values.update(changes)
    return PokemonRedState(**values)  # type: ignore[arg-type]


def test_full_game_reward_is_nonrepeatable_and_round_trips() -> None:
    tracker = FullGameRewardTracker()
    pokedex = MilestoneProgress("obtained_pokedex", 15, "Received the Pokedex")
    forest = MilestoneProgress("reached_viridian_forest", 16, "Entered Viridian Forest")
    tracker.prime(state(), pokedex)

    events = bytearray(319)
    events[10] = 1
    owned = bytearray(19)
    owned[0] = 1
    first = tracker.score(
        state(
            map_id=0x33,
            player_x=2,
            player_y=3,
            badge_bits=1,
            party_levels=(6,),
            party_moves=(33, 45),
            pokedex_owned=bytes(owned),
            pokedex_seen=bytes(owned),
            event_flags=bytes(events),
            bag_item_ids=(4,),
        ),
        forest,
        action_button="up",
        loop_detected=False,
    )
    assert first.components["named_milestone"] == 1_000
    assert first.components["new_map"] == 25
    assert first.components["new_badge"] == 500
    assert first.components["new_event"] == 20
    assert first.components["species_owned"] == 30

    repeated = tracker.score(
        state(
            map_id=0x33,
            player_x=2,
            player_y=3,
            badge_bits=1,
            party_levels=(6,),
            party_moves=(33, 45),
            pokedex_owned=bytes(owned),
            pokedex_seen=bytes(owned),
            event_flags=bytes(events),
            bag_item_ids=(4,),
        ),
        forest,
        action_button="down",
        loop_detected=False,
    )
    assert repeated.total == 0

    restored = FullGameRewardTracker.from_checkpoint_dict(tracker.checkpoint_dict())
    assert restored.checkpoint_dict() == tracker.checkpoint_dict()


def test_reward_prime_absorbs_every_restored_parent_without_repaying_it() -> None:
    tracker = FullGameRewardTracker()
    route = MilestoneProgress("reached_route_1", 7, "Reached Route 1")
    pokedex = MilestoneProgress("obtained_pokedex", 15, "Received the Pokedex")
    tracker.prime(state(map_id=0x0C, player_x=4, player_y=8), route)
    tracker.prime(
        state(
            map_id=0x01,
            player_x=12,
            player_y=20,
            party_levels=(8,),
            bag_item_ids=(4,),
        ),
        pokedex,
    )

    restored_parent = tracker.score(
        state(
            map_id=0x01,
            player_x=12,
            player_y=20,
            party_levels=(8,),
            bag_item_ids=(4,),
        ),
        pokedex,
        action_button="up",
        loop_detected=False,
    )

    assert restored_parent.total == 0
    assert tracker.best_milestone_index == pokedex.index
    assert (0x01, 12, 20) in tracker.seen_positions


def test_battle_reward_requires_durable_progress_and_records_outcomes() -> None:
    tracker = FullGameRewardTracker()
    route = MilestoneProgress("reached_route_1", 7, "Reached Route 1")
    tracker.prime(state(party_experience=(125,)), route)

    started = tracker.score(
        state(battle_state=1, party_experience=(125,)),
        route,
        action_button="a",
        loop_detected=False,
    )
    escaped = tracker.score(
        state(battle_state=0, party_experience=(125,)),
        route,
        action_button="b",
        loop_detected=False,
    )

    assert started.battle_event == "started"
    assert escaped.battle_event == "ended_without_progress"
    assert "battle_success" not in escaped.components

    tracker.score(
        state(battle_state=1, party_experience=(125,)),
        route,
        action_button="a",
        loop_detected=False,
    )
    gained = tracker.score(
        state(battle_state=1, party_experience=(175,)),
        route,
        action_button="a",
        loop_detected=False,
    )
    won = tracker.score(
        state(battle_state=0, party_experience=(175,)),
        route,
        action_button="b",
        loop_detected=False,
    )

    assert gained.components["experience_gain"] == pytest.approx(1.0)
    assert won.components["battle_success"] == 2
    assert won.battle_event == "success"


def test_opponent_damage_gets_dense_credit_without_turning_escape_into_success() -> None:
    tracker = FullGameRewardTracker()
    route = MilestoneProgress("reached_route_1", 7, "Reached Route 1")
    tracker.prime(state(), route)
    tracker.score(
        state(battle_state=1, enemy_hp=20, enemy_max_hp=20),
        route,
        action_button="a",
        loop_detected=False,
    )
    damaged = tracker.score(
        state(battle_state=1, enemy_hp=10, enemy_max_hp=20),
        route,
        action_button="a",
        loop_detected=False,
    )
    escaped = tracker.score(
        state(), route, action_button="b", loop_detected=False
    )

    assert damaged.components["opponent_damage"] == pytest.approx(1.0)
    assert escaped.battle_event == "ended_without_progress"
    assert "battle_success" not in escaped.components


def test_mart_dialogue_stage_is_a_bounded_episode_lesson() -> None:
    tracker = FullGameRewardTracker()
    mart = MilestoneProgress("entered_viridian_mart", 9, "Entered the Viridian Poke Mart")
    tracker.prime(state(map_id=0x2A, viridian_mart_script=0), mart)

    first = tracker.score(
        state(map_id=0x2A, viridian_mart_script=1),
        mart,
        action_button="a",
        loop_detected=False,
    )
    repeated = tracker.score(
        state(map_id=0x2A, viridian_mart_script=1),
        mart,
        action_button="a",
        loop_detected=False,
    )
    assert first.components["mart_dialogue_progress"] == 5
    assert "mart_dialogue_progress" not in repeated.components

    tracker.prime(state(map_id=1, viridian_mart_script=None), mart)
    replayed_lesson = tracker.score(
        state(map_id=0x2A, viridian_mart_script=1),
        mart,
        action_button="a",
        loop_detected=False,
    )
    assert replayed_lesson.components["mart_dialogue_progress"] == 5


def test_mart_approach_only_rewards_a_new_episode_best_distance() -> None:
    tracker = FullGameRewardTracker()
    city = MilestoneProgress("reached_viridian_city", 8, "Reached Viridian City")
    tracker.prime(state(map_id=0x01, player_x=20, player_y=20), city)

    closer = tracker.score(
        state(map_id=0x01, player_x=21, player_y=20),
        city,
        action_button="right",
        loop_detected=False,
    )
    farther = tracker.score(
        state(map_id=0x01, player_x=20, player_y=20),
        city,
        action_button="left",
        loop_detected=False,
    )
    repeated = tracker.score(
        state(map_id=0x01, player_x=21, player_y=20),
        city,
        action_button="right",
        loop_detected=False,
    )

    assert closer.components["mart_approach"] == pytest.approx(0.25)
    assert "mart_approach" not in farther.components
    assert "mart_approach" not in repeated.components


def test_completed_mart_lessons_expire_after_the_parcel() -> None:
    tracker = FullGameRewardTracker()
    parcel = MilestoneProgress("obtained_oaks_parcel", 10, "Obtained Oak's Parcel")
    tracker.prime(
        state(map_id=0x2A, player_x=4, player_y=6, viridian_mart_script=1),
        parcel,
    )

    result = tracker.score(
        state(map_id=0x01, player_x=29, player_y=19, viridian_mart_script=2),
        parcel,
        action_button="down",
        loop_detected=False,
    )

    assert "mart_approach" not in result.components
    assert "mart_dialogue_progress" not in result.components


def test_bidirectional_goal_potential_rewards_return_and_cancels_oscillation() -> None:
    tracker = FullGameRewardTracker()
    parcel = MilestoneProgress("obtained_oaks_parcel", 10, "Obtained Oak's Parcel")
    tracker.prime(state(map_id=0x2A, bag_item_ids=(0x46,)), parcel)

    south = tracker.score(
        state(map_id=0x01, bag_item_ids=(0x46,)),
        parcel,
        action_button="down",
        loop_detected=False,
    )
    north = tracker.score(
        state(map_id=0x2A, bag_item_ids=(0x46,)),
        parcel,
        action_button="up",
        loop_detected=False,
    )

    assert south.components["goal_route_progress"] == 8
    assert north.components["goal_route_progress"] == -8
    assert (
        south.components["goal_route_progress"]
        + north.components["goal_route_progress"]
        == 0
    )


def test_experience_reward_is_lifetime_bounded_but_local_wins_still_count() -> None:
    tracker = FullGameRewardTracker()
    route = MilestoneProgress("reached_route_1", 7, "Reached Route 1")
    tracker.prime(state(party_experience=(1_000,)), route)
    tracker.prime(state(party_experience=(100,)), route)
    tracker.score(
        state(battle_state=1, party_experience=(100,)),
        route,
        action_button="a",
        loop_detected=False,
    )
    below_record = tracker.score(
        state(battle_state=1, party_experience=(150,)),
        route,
        action_button="a",
        loop_detected=False,
    )
    won = tracker.score(
        state(battle_state=0, party_experience=(150,)),
        route,
        action_button="b",
        loop_detected=False,
    )

    assert "experience_gain" not in below_record.components
    assert won.battle_event == "success"
    assert won.components["battle_success"] == 2
    assert tracker.max_party_experience == 1_000

    restored = FullGameRewardTracker.from_checkpoint_dict(tracker.checkpoint_dict())
    assert restored.max_party_experience == 1_000


def test_single_observation_experience_windfall_is_capped() -> None:
    tracker = FullGameRewardTracker()
    route = MilestoneProgress("reached_route_1", 7, "Reached Route 1")
    tracker.prime(state(party_experience=(100,)), route)

    result = tracker.score(
        state(party_experience=(10_100,)),
        route,
        action_button="a",
        loop_detected=False,
    )

    assert result.components["experience_gain"] == 10
    assert tracker.max_party_experience == 10_100


def test_legacy_battle_ending_reward_memory_is_rejected() -> None:
    checkpoint = FullGameRewardTracker().checkpoint_dict()
    checkpoint["config"] = {"battle_ended": 10.0}

    with pytest.raises(ValueError, match="Legacy battle-ending reward"):
        FullGameRewardTracker.from_checkpoint_dict(checkpoint)


class FakePixelsActor:
    def __init__(self) -> None:
        self.value = 0

    def observe(self) -> np.ndarray:
        self.value += 1
        return np.full((144, 160, 3), self.value % 255, dtype=np.uint8)


def test_frontier_learner_persists_and_restores_verified_update(tmp_path: Path) -> None:
    pytest.importorskip("torch")
    torch = require_torch()
    seed = tmp_path / "seed"
    run = tmp_path / "run"
    seed.mkdir()
    run.mkdir()
    model = build_apprentice_policy()
    model_path = seed / "learner.pt"
    torch.save(model.state_dict(), model_path)
    file_sha256 = hashlib.sha256(model_path.read_bytes()).hexdigest()
    (seed / "learner.json").write_text(
        json.dumps(
            {
                "development_only": True,
                "file_sha256": file_sha256,
                "parameter_sha256": _parameter_sha256(model),
            }
        ),
        encoding="utf-8",
    )

    actor = FakePixelsActor()
    learner = FrontierSelfImitationEmitter(
        random.Random(7),
        seed,
        run,
        expected_model_sha256=file_sha256,
        learning_rate=0.0001,
        training_epochs=1,
    )
    learner.reset(actor, exploration_probability=1)
    for _ in range(4):
        learner.emit()
    result = learner.learn_from_verified_promotion(
        MilestoneProgress("game_started", 1, "The adventure begins")
    )
    assert result["actions"] == 4
    checkpoint = learner.checkpoint_state()
    assert checkpoint["updates"] > 0
    assert (run / "frontier-learner.pt").is_file()

    restored = FrontierSelfImitationEmitter(
        random.Random(7),
        seed,
        run,
        expected_model_sha256=file_sha256,
        learning_rate=0.0001,
        training_epochs=1,
        resume_state=checkpoint,
    )
    assert restored.checkpoint_state() == checkpoint
