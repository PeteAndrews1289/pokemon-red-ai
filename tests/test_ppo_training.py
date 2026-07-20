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
    PRIVILEGED_STATE_SIZE,
    ParallelPpoConfig,
    PokemonPpoFeatures,
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


@pytest.mark.parametrize("privileged", [False, True])
def test_feature_extractor_preserves_declared_information_boundary(privileged: bool) -> None:
    spaces = {
        "pixels": gym.spaces.Box(0, 255, shape=(2, 72, 80), dtype=np.uint8),
        "previous_action": gym.spaces.Box(0, 1, shape=(len(BLIND_ACTIONS),), dtype=np.float32),
    }
    if privileged:
        spaces["state"] = gym.spaces.Box(0, 1, shape=(PRIVILEGED_STATE_SIZE,), dtype=np.float32)
    extractor = PokemonPpoFeatures(gym.spaces.Dict(spaces))
    observations = {
        "pixels": torch.zeros((2, 2, 72, 80)),
        "previous_action": torch.zeros((2, len(BLIND_ACTIONS))),
    }
    if privileged:
        observations["state"] = torch.zeros((2, PRIVILEGED_STATE_SIZE))

    features = extractor(observations)
    expected = 256 + len(BLIND_ACTIONS) + (PRIVILEGED_STATE_SIZE if privileged else 0)
    assert features.shape == (2, expected)


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
            "information_boundary": "pixels + previous action; trainer-only RAM rewards",
            "novelty_scope": "persistent per worker across episodes and resumes",
        }
    )
    assert "Failures now" in page
    assert "pixels + previous action; trainer-only RAM rewards" in page
    assert "persistent per worker across episodes and resumes" in page
    assert "finished" in page
    assert page.count("Environment ") == 8
