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
        "party_moves": (33,),
        "pokedex_owned": bytes(19),
        "pokedex_seen": bytes(19),
        "event_flags": bytes(319),
        "bag_item_ids": (),
        "got_pokedex": True,
    }
    values.update(changes)
    return PokemonRedState(**values)  # type: ignore[arg-type]


def test_full_game_reward_is_nonrepeatable_and_round_trips() -> None:
    tracker = FullGameRewardTracker()
    pokedex = MilestoneProgress("obtained_pokedex", 11, "Received the Pokedex")
    forest = MilestoneProgress("reached_viridian_forest", 12, "Entered Viridian Forest")
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
    pokedex = MilestoneProgress("obtained_pokedex", 11, "Received the Pokedex")
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
