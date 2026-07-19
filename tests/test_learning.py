from __future__ import annotations

import random

import numpy as np

from pokemon_red_ai.learning import HashedQPolicy, RewardTracker, policy_state_key
from pokemon_red_ai.state import PokemonRedState


def test_policy_checkpoint_round_trip_preserves_learning() -> None:
    policy = HashedQPolicy(action_count=9, bucket_count=1_024)
    key = bytes.fromhex("12" * 16)
    action, bucket, _epsilon = policy.select(key, random.Random(4))
    policy.update(bucket, action, 3.0, key)

    restored = HashedQPolicy.from_checkpoint_dict(policy.checkpoint_dict())

    assert restored.updates == 1
    assert restored.occupied_buckets == 1
    np.testing.assert_array_equal(restored.q_values, policy.q_values)
    np.testing.assert_array_equal(restored.visits, policy.visits)


def test_outcome_reward_is_semantic_but_policy_key_can_remain_pixels_only() -> None:
    pixel_key = bytes.fromhex("34" * 16)
    first = PokemonRedState(True, 0x26, 6, 3, 0, 0, 0)
    progressed = PokemonRedState(True, 0x28, 5, 4, 1, 2, 1)
    tracker = RewardTracker("outcome")

    first_reward, _ = tracker.score(visually_novel=False, state=first)
    progressed_reward, parts = tracker.score(visually_novel=True, state=progressed)

    assert policy_state_key(pixel_key) == policy_state_key(pixel_key, None)
    assert policy_state_key(pixel_key, progressed) != policy_state_key(pixel_key)
    assert first_reward > 0
    assert progressed_reward > first_reward
    assert parts["party_increase"] == 25
    assert parts["new_badge"] == 100
    assert tracker.badge_bits.bit_count() == 1


def test_curious_reward_uses_only_visual_novelty() -> None:
    tracker = RewardTracker("curious")
    reward, components = tracker.score(visually_novel=True, state=None)
    repeat, repeat_components = tracker.score(visually_novel=False, state=None)

    assert reward == 1
    assert components == {"visual_novelty": 1.0}
    assert repeat == 0
    assert repeat_components == {}
