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
    assert parts["new_badge"] == 200
    assert "visual_novelty" not in parts
    assert tracker.visual_reward == 0
    assert tracker.badge_bits.bit_count() == 1


def test_conventional_reward_adds_explicit_collection_milestones() -> None:
    tracker = RewardTracker("conventional")
    baseline = PokemonRedState(
        True,
        0,
        1,
        1,
        1,
        0,
        0,
        party_levels=(5,),
        pokedex_owned=bytes(19),
        pokedex_seen=bytes(19),
        event_flags=bytes(319),
        bag_item_ids=(),
        got_pokedex=False,
    )
    progressed = PokemonRedState(
        True,
        1,
        2,
        2,
        1,
        0,
        0,
        party_levels=(6,),
        pokedex_owned=bytes([1]) + bytes(18),
        pokedex_seen=bytes([3]) + bytes(18),
        event_flags=bytes([1]) + bytes(318),
        bag_item_ids=(0x04, 0x46, 0xC4),
        got_pokedex=True,
    )

    tracker.score(visually_novel=False, state=baseline, action_button="up")
    reward, parts = tracker.score(
        visually_novel=False,
        state=progressed,
        action_button="up",
    )

    assert reward > 150
    assert parts["new_species_seen"] == 6
    assert parts["new_species_owned"] == 25
    assert parts["oaks_parcel_obtained"] == 30
    assert parts["pokedex_obtained"] == 50
    assert parts["pokeballs_obtained"] == 15
    assert parts["required_item_obtained"] == 50


def test_observer_tracks_progress_without_returning_reward() -> None:
    tracker = RewardTracker("observer")
    state = PokemonRedState(True, 2, 3, 4, 1, 0, 1, party_levels=(7,))

    reward, parts = tracker.score(visually_novel=True, state=state)

    assert reward == 0
    assert parts == {}
    assert tracker.seen_maps == {2}
    assert tracker.max_party_count == 1
    assert tracker.max_party_level == 7


def test_blackouts_are_all_counted_but_only_the_first_is_penalized() -> None:
    tracker = RewardTracker("outcome")
    playing = PokemonRedState(True, 2, 3, 4, 1, 0, 0)
    lost = PokemonRedState(True, 2, 3, 4, 1, 0xFF, 0)

    tracker.score(visually_novel=False, state=playing)
    first_reward, first_parts = tracker.score(visually_novel=False, state=lost)
    tracker.score(visually_novel=False, state=lost)
    tracker.score(visually_novel=False, state=playing)
    second_reward, second_parts = tracker.score(visually_novel=False, state=lost)

    assert first_parts["blackout"] == -2
    assert first_reward == -2
    assert "blackout" not in second_parts
    assert second_reward == 0
    assert tracker.blackouts == 2


def test_curious_reward_uses_only_visual_novelty() -> None:
    tracker = RewardTracker("curious")
    reward, components = tracker.score(visually_novel=True, state=None)
    repeat, repeat_components = tracker.score(visually_novel=False, state=None)

    assert reward == 1
    assert components == {"visual_novelty": 1.0}
    assert repeat == 0
    assert repeat_components == {}


def test_n_step_replay_propagates_a_delayed_reward_and_round_trips() -> None:
    policy = HashedQPolicy(
        action_count=3,
        bucket_count=1_024,
        n_step=3,
        replay_capacity=16,
        replay_batch_size=2,
        replay_interval=1,
    )
    rng = random.Random(11)
    keys = [value.to_bytes(16, "big") for value in range(1, 5)]
    buckets = [policy.bucket(key) for key in keys]

    policy.observe_transition(buckets[0], 0, 0.0, keys[1], rng)
    policy.observe_transition(buckets[1], 1, 0.0, keys[2], rng)
    assert policy.updates == 0
    assert policy.replay_size == 0

    policy.observe_transition(buckets[2], 2, 10.0, keys[3], rng)

    assert policy.replay_size == 1
    assert policy.updates == 1
    assert policy.q_values[buckets[0], 0] > 0
    assert len(policy.pending) == 2

    restored = HashedQPolicy.from_checkpoint_dict(policy.checkpoint_dict())
    assert restored.n_step == 3
    assert restored.replay_size == 1
    assert list(restored.pending) == list(policy.pending)
    assert restored.important == policy.important
    np.testing.assert_array_equal(restored.replay_rewards, policy.replay_rewards)
