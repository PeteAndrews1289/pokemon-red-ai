from __future__ import annotations

# Optional RL dependencies must be checked before importing the PPO module.
# ruff: noqa: E402
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
    _remap_warm_start_lstm_input,
    _render_dashboard,
    _state_vector,
)
from pokemon_red_ai.state import PokemonRedState


def test_parallel_config_enforces_vector_batch_boundary() -> None:
    config = ParallelPpoConfig(environments=4, rollout_steps=64, batch_size=128)
    assert config.environments * config.rollout_steps == 256

    with pytest.raises(ValueError, match="must divide"):
        ParallelPpoConfig(environments=3, rollout_steps=64, batch_size=128)


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


@pytest.mark.parametrize("mode", ["pixels", "assisted", "privileged"])
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
                "map_context": gym.spaces.Box(
                    0, 1, shape=(MAP_CONTEXT_SIZE,), dtype=np.float32
                ),
            }
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

    features = extractor(observations)
    expected = (
        256
        + ACTION_HISTORY_LENGTH * len(BLIND_ACTIONS)
        + (
            MAP_MEMORY_FEATURES + GOAL_COUNT + SKILL_COUNT + MAP_CONTEXT_SIZE
            if mode == "assisted"
            else 0
        )
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
    assert torch.equal(
        destination[:, newest : newest + len(BLIND_ACTIONS)], source[:, 256:]
    )
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
            "reward_protocol": "active-goal-bidirectional-navigation-v1",
            "battle_events": {"success": 3, "ended_without_progress": 7},
        }
    )
    assert "Failures now" in page
    assert "pixels + three recent actions; trainer-only RAM rewards" in page
    assert "persistent per worker across episodes and resumes" in page
    assert "active-goal-bidirectional-navigation-v1" in page
    assert "Battle successes" in page
    assert ">3<" in page
    assert "No-progress battle exits" in page
    assert ">7<" in page
    assert "finished" in page
    assert page.count("Environment ") == 8
