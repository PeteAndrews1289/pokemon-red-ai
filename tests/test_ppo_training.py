from __future__ import annotations

# Optional RL dependencies must be checked before importing the PPO module.
# ruff: noqa: E402
import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

gym = pytest.importorskip("gymnasium")
pytest.importorskip("stable_baselines3")
pytest.importorskip("sb3_contrib")
torch = pytest.importorskip("torch")

from pokemon_red_ai.blind import BLIND_ACTIONS
from pokemon_red_ai.ppo_training import (
    ACTION_HISTORY_LENGTH,
    GOAL_COUNT,
    MAP_CONTEXT_SIZE,
    MAP_MEMORY_FEATURES,
    MAP_MEMORY_SIZE,
    PRIVILEGED_STATE_SIZE,
    SKILL_COUNT,
    EpisodeMapMemory,
    ParallelPpoConfig,
    PokemonPpoFeatures,
    VisualStagnationTracker,
    _copy_retained_ppo_policy,
    _remaining_action_budget,
    _remap_warm_start_lstm_input,
    _render_dashboard,
    _state_vector,
    _train_self_imitation_policy,
)
from pokemon_red_ai.state import PokemonRedState


def test_parallel_config_enforces_vector_batch_boundary() -> None:
    config = ParallelPpoConfig(environments=4, rollout_steps=64, batch_size=128)
    assert config.environments * config.rollout_steps == 256

    with pytest.raises(ValueError, match="must divide"):
        ParallelPpoConfig(environments=3, rollout_steps=64, batch_size=128)

    with pytest.raises(ValueError, match="competence"):
        ParallelPpoConfig(competence_window=1)

    with pytest.raises(ValueError, match="Self-taught"):
        ParallelPpoConfig(mode="self_taught")
    self_taught = ParallelPpoConfig(
        mode="self_taught", random_initialization=True, power_on_only=True
    )
    assert self_taught.consolidation is False


def test_retained_policy_copy_requires_clean_compatible_terminal_evidence(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    model = source / "ppo-latest.zip"
    model.write_bytes(b"verified policy")
    config = ParallelPpoConfig(mode="assisted")
    checkpoint = {
        "protocol": "parallel-recurrent-ppo-v5.2",
        "total_actions": 1234,
        "model_file_sha256": hashlib.sha256(model.read_bytes()).hexdigest(),
        "config": config.public_dict(),
    }
    (source / "checkpoint.json").write_text(json.dumps(checkpoint), encoding="utf-8")
    (source / "status.json").write_text(
        json.dumps(
            {
                "state": "finished",
                "stop_reason": "stop_requested",
                "total_actions": 1234,
                "best_milestone": {"index": 17, "key": "route", "label": "Route"},
            }
        ),
        encoding="utf-8",
    )
    (source / "manifest.json").write_text(
        json.dumps({"actor_mode": "assisted"}), encoding="utf-8"
    )
    destination = tmp_path / "retained.zip"

    metadata = _copy_retained_ppo_policy(source, destination, config)

    assert destination.read_bytes() == model.read_bytes()
    assert metadata["optimizer_state_retained"] is True
    assert metadata["source_total_actions"] == 1234

    failed_status = json.loads((source / "status.json").read_text(encoding="utf-8"))
    failed_status["state"] = "running"
    (source / "status.json").write_text(json.dumps(failed_status), encoding="utf-8")
    with pytest.raises(ValueError, match="cleanly finished"):
        _copy_retained_ppo_policy(source, tmp_path / "rejected.zip", config)


def test_retained_policy_gets_a_fresh_budget_but_resume_does_not() -> None:
    assert _remaining_action_budget(8_192, 8_192, resume=False) == 8_192
    assert _remaining_action_budget(8_192, 4_096, resume=True) == 4_096


def test_self_imitation_updates_recurrent_policy_from_its_own_dataset(
    tmp_path: Path,
) -> None:
    from sb3_contrib import RecurrentPPO
    from stable_baselines3.common.vec_env import DummyVecEnv

    class TinySelfTaughtEnv(gym.Env):
        def __init__(self) -> None:
            self.action_space = gym.spaces.Discrete(len(BLIND_ACTIONS))
            self.observation_space = gym.spaces.Dict(
                {
                    "pixels": gym.spaces.Box(
                        0, 255, shape=(2, 72, 80), dtype=np.uint8
                    ),
                    "action_history": gym.spaces.Box(
                        0,
                        1,
                        shape=(ACTION_HISTORY_LENGTH * len(BLIND_ACTIONS),),
                        dtype=np.float32,
                    ),
                    "target_pixels": gym.spaces.Box(
                        0, 255, shape=(1, 72, 80), dtype=np.uint8
                    ),
                }
            )

        def observation(self) -> dict[str, np.ndarray]:
            return {
                "pixels": np.zeros((2, 72, 80), dtype=np.uint8),
                "action_history": np.zeros(
                    ACTION_HISTORY_LENGTH * len(BLIND_ACTIONS), dtype=np.float32
                ),
                "target_pixels": np.zeros((1, 72, 80), dtype=np.uint8),
            }

        def reset(self, *, seed=None, options=None):  # type: ignore[no-untyped-def]
            super().reset(seed=seed)
            return self.observation(), {}

        def step(self, action):  # type: ignore[no-untyped-def]
            return self.observation(), 0.0, False, False, {}

    vector = DummyVecEnv([TinySelfTaughtEnv])
    model = RecurrentPPO(
        "MultiInputLstmPolicy",
        vector,
        n_steps=8,
        batch_size=8,
        n_epochs=1,
        policy_kwargs={
            "features_extractor_class": PokemonPpoFeatures,
            "net_arch": [],
            "lstm_hidden_size": 32,
        },
        device="cpu",
    )
    dataset = tmp_path / "self.npz"
    np.savez_compressed(
        dataset,
        pixels=np.zeros((4, 2, 72, 80), dtype=np.uint8),
        action_history=np.zeros(
            (4, ACTION_HISTORY_LENGTH * len(BLIND_ACTIONS)), dtype=np.float32
        ),
        target_pixels=np.zeros((1, 72, 80), dtype=np.uint8),
        actions=np.asarray([0, 1, 2, 3], dtype=np.int64),
    )

    result = _train_self_imitation_policy(model, [dataset], epochs=1)

    assert result["updates"] == 1
    assert result["examples"] == 4
    assert np.isfinite(result["mean_loss"])
    vector.close()


def test_privileged_state_vector_is_fixed_and_bounded() -> None:
    state = PokemonRedState(
        game_started=True,
        map_id=255,
        player_y=200,
        player_x=100,
        party_count=6,
        battle_state=2,
        badge_bits=0b10101010,
        party_species=(1, 2, 3),
        party_levels=(5, 50, 100),
        party_moves=(1, 2),
        pokedex_owned=bytes([0xFF]) + bytes(18),
        pokedex_seen=bytes([0xFF, 0xFF]) + bytes(17),
        event_flags=bytes([0xFF]) + bytes(318),
        bag_item_ids=(1, 2, 3),
        got_pokedex=True,
    )
    vector = _state_vector(state)
    assert vector.shape == (PRIVILEGED_STATE_SIZE,)
    assert vector.dtype == np.float32
    assert np.all((vector >= 0) & (vector <= 1))


@pytest.mark.parametrize("mode", ["pixels", "assisted", "privileged", "self_taught"])
def test_feature_extractor_preserves_declared_information_boundary(mode: str) -> None:
    spaces = {
        "pixels": gym.spaces.Box(0, 255, shape=(2, 72, 80), dtype=np.uint8),
        "action_history": gym.spaces.Box(
            0,
            1,
            shape=(ACTION_HISTORY_LENGTH * len(BLIND_ACTIONS),),
            dtype=np.float32,
        ),
    }
    if mode == "privileged":
        spaces["state"] = gym.spaces.Box(0, 1, shape=(PRIVILEGED_STATE_SIZE,), dtype=np.float32)
    if mode == "assisted":
        spaces.update(
            {
                "map_memory": gym.spaces.Box(
                    0, 255, shape=(2, MAP_MEMORY_SIZE, MAP_MEMORY_SIZE), dtype=np.uint8
                ),
                "goal": gym.spaces.Box(0, 1, shape=(GOAL_COUNT,), dtype=np.float32),
                "skill": gym.spaces.Box(0, 1, shape=(SKILL_COUNT,), dtype=np.float32),
                "map_context": gym.spaces.Box(0, 1, shape=(MAP_CONTEXT_SIZE,), dtype=np.float32),
            }
        )
    if mode == "self_taught":
        spaces["target_pixels"] = gym.spaces.Box(
            0, 255, shape=(1, 72, 80), dtype=np.uint8
        )
    extractor = PokemonPpoFeatures(gym.spaces.Dict(spaces))
    observations = {
        "pixels": torch.zeros((2, 2, 72, 80)),
        "action_history": torch.zeros((2, ACTION_HISTORY_LENGTH * len(BLIND_ACTIONS))),
    }
    if mode == "privileged":
        observations["state"] = torch.zeros((2, PRIVILEGED_STATE_SIZE))
    if mode == "assisted":
        observations.update(
            {
                "map_memory": torch.zeros((2, 2, MAP_MEMORY_SIZE, MAP_MEMORY_SIZE)),
                "goal": torch.zeros((2, GOAL_COUNT)),
                "skill": torch.zeros((2, SKILL_COUNT)),
                "map_context": torch.zeros((2, MAP_CONTEXT_SIZE)),
            }
        )
    if mode == "self_taught":
        observations["target_pixels"] = torch.zeros((2, 1, 72, 80))

    features = extractor(observations)
    expected = (
        256
        + ACTION_HISTORY_LENGTH * len(BLIND_ACTIONS)
        + (
            MAP_MEMORY_FEATURES + GOAL_COUNT + SKILL_COUNT + MAP_CONTEXT_SIZE
            if mode == "assisted"
            else 0
        )
        + (128 if mode == "self_taught" else 0)
        + (PRIVILEGED_STATE_SIZE if mode == "privileged" else 0)
    )
    assert features.shape == (2, expected)


def test_episode_map_memory_marks_visited_and_current_cells() -> None:
    memory = EpisodeMapMemory()
    first = PokemonRedState(True, 1, 4, 3, 1, 0)
    second = PokemonRedState(True, 1, 4, 4, 1, 0)
    memory.reset(first)
    memory.observe(second)
    value = memory.observation(second)
    assert value[0, 4, 3] == 255
    assert value[0, 4, 4] == 255
    assert value[1, 4, 4] == 255
    assert value[1].sum() == 255


def test_visual_stagnation_tracker_finds_cycles_and_resets_on_progress() -> None:
    tracker = VisualStagnationTracker(cycle_window=4, cycle_unique_limit=2, hard_limit=20)
    progress = pytest.importorskip("pokemon_red_ai.expedition").MilestoneProgress(
        "power_on", 0, "Power-on"
    )
    state = PokemonRedState(True, 0, 1, 1, 1, 0, party_experience=(1,))
    tracker.reset(state, progress)
    frame = np.zeros((72, 80), dtype=np.uint8)
    assert tracker.observe(frame, state, progress) is None
    assert tracker.observe(frame, state, progress) is None
    assert tracker.observe(frame, state, progress) is None
    assert tracker.observe(frame, state, progress) == "visual_cycle"

    moved = PokemonRedState(True, 0, 1, 2, 1, 0, party_experience=(1,))
    assert tracker.observe(frame, moved, progress) is None


def test_warm_start_maps_previous_action_to_newest_history_slot() -> None:
    source = torch.arange(2 * (256 + len(BLIND_ACTIONS)), dtype=torch.float32).reshape(2, -1)
    destination = torch.full(
        (2, 256 + ACTION_HISTORY_LENGTH * len(BLIND_ACTIONS) + PRIVILEGED_STATE_SIZE),
        -1.0,
    )
    _remap_warm_start_lstm_input(destination, source)

    newest = 256 + (ACTION_HISTORY_LENGTH - 1) * len(BLIND_ACTIONS)
    assert torch.equal(destination[:, :256], source[:, :256])
    assert torch.count_nonzero(destination[:, 256:newest]) == 0
    assert torch.equal(destination[:, newest : newest + len(BLIND_ACTIONS)], source[:, 256:])
    assert torch.count_nonzero(destination[:, newest + len(BLIND_ACTIONS) :]) == 0


def test_dashboard_names_actor_boundary_and_finished_state() -> None:
    page = _render_dashboard(
        {
            "state": "finished",
            "mode": "pixels",
            "environments": 4,
            "total_actions": 10,
            "actions_per_second": 2,
            "ppo_updates": 1,
            "verified_promotions": 0,
            "unique_positions": 3,
            "episodes": 2,
            "best_milestone": {"label": "Reached Route 1"},
            "information_boundary": (
                "pixels + three recent actions; trainer-only RAM rewards and loop termination"
            ),
            "novelty_scope": "persistent per worker across episodes and resumes",
            "reward_protocol": "retained-policy-backward-consolidation-v1",
            "battle_events": {"success": 3, "ended_without_progress": 7},
            "self_taught": {
                "skills_discovered": 2,
                "skills_competent": 1,
                "imitation_examples": 12,
            },
        }
    )
    assert "Failures now" in page
    assert "pixels + three recent actions; trainer-only RAM rewards" in page
    assert "persistent per worker across episodes and resumes" in page
    assert "retained-policy-backward-consolidation-v1" in page
    assert "Consolidation start" in page
    assert "Self-discovered skills" in page
    assert "Self-imitation examples" in page
    assert "Navigation-recovery credit" in page
    assert "Battle successes" in page
    assert ">3<" in page
    assert "No-progress battle exits" in page
    assert ">7<" in page
    assert "finished" in page
    assert page.count("Environment ") == 8
