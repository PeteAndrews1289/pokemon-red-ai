from __future__ import annotations

import base64
import hashlib
import random
import zlib
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from pokemon_red_ai.state import PokemonRedState


def policy_state_key(pixel_key: bytes, semantic_state: PokemonRedState | None = None) -> bytes:
    """Create a bounded policy-state key from declared observations.

    Passing no semantic state produces a pixels-only key. The conventional arm deliberately adds
    its disclosed RAM observation; the outcome-rewarded arm must never pass that state here.
    """

    digest = hashlib.blake2b(digest_size=16, person=b"pkmn-policy-v1")
    digest.update(pixel_key)
    if semantic_state is not None:
        values = (
            int(semantic_state.game_started),
            semantic_state.map_id or 0,
            semantic_state.player_x or 0,
            semantic_state.player_y or 0,
            semantic_state.party_count or 0,
            semantic_state.battle_state or 0,
            semantic_state.badge_bits or 0,
        )
        digest.update(bytes(values))
    return digest.digest()


@dataclass(slots=True)
class HashedQPolicy:
    """Small online Q learner whose memory stays bounded during multi-day runs."""

    action_count: int
    bucket_count: int = 16_384
    learning_rate: float = 0.12
    discount: float = 0.97
    minimum_epsilon: float = 0.05
    exploration_scale: float = 40.0
    q_values: np.ndarray = field(init=False, repr=False)
    visits: np.ndarray = field(init=False, repr=False)
    updates: int = 0
    exploratory_actions: int = 0

    def __post_init__(self) -> None:
        if self.action_count < 2:
            raise ValueError("A learning policy needs at least two actions")
        if self.bucket_count < 1_024:
            raise ValueError("Q-policy bucket count must be at least 1,024")
        self.q_values = np.zeros((self.bucket_count, self.action_count), dtype=np.float32)
        self.visits = np.zeros(self.bucket_count, dtype=np.uint32)

    def bucket(self, key: bytes) -> int:
        return int.from_bytes(key[:8], "big") % self.bucket_count

    def select(self, key: bytes, rng: random.Random) -> tuple[int, int, float]:
        bucket = self.bucket(key)
        visits = int(self.visits[bucket])
        epsilon = max(
            self.minimum_epsilon,
            (self.exploration_scale / (self.exploration_scale + visits)) ** 0.5,
        )
        self.visits[bucket] = min(visits + 1, np.iinfo(np.uint32).max)
        if rng.random() < epsilon:
            self.exploratory_actions += 1
            return rng.randrange(self.action_count), bucket, epsilon
        row = self.q_values[bucket]
        best = np.flatnonzero(row == row.max())
        return int(best[rng.randrange(len(best))]), bucket, epsilon

    def update(self, bucket: int, action_index: int, reward: float, next_key: bytes) -> None:
        current = float(self.q_values[bucket, action_index])
        target = reward + self.discount * float(self.q_values[self.bucket(next_key)].max())
        updated = current + self.learning_rate * (target - current)
        self.q_values[bucket, action_index] = np.float32(np.clip(updated, -1_000, 1_000))
        self.updates += 1

    @property
    def occupied_buckets(self) -> int:
        return int(np.count_nonzero(self.visits))

    def checkpoint_dict(self) -> dict[str, Any]:
        def encode(array: np.ndarray) -> str:
            return base64.b64encode(zlib.compress(array.tobytes(), level=3)).decode("ascii")

        return {
            "schema_version": 1,
            "action_count": self.action_count,
            "bucket_count": self.bucket_count,
            "learning_rate": self.learning_rate,
            "discount": self.discount,
            "minimum_epsilon": self.minimum_epsilon,
            "exploration_scale": self.exploration_scale,
            "q_values_f32_zlib": encode(self.q_values),
            "visits_u32_zlib": encode(self.visits),
            "updates": self.updates,
            "exploratory_actions": self.exploratory_actions,
        }

    @classmethod
    def from_checkpoint_dict(cls, value: dict[str, Any]) -> HashedQPolicy:
        policy = cls(
            action_count=int(value["action_count"]),
            bucket_count=int(value["bucket_count"]),
            learning_rate=float(value["learning_rate"]),
            discount=float(value["discount"]),
            minimum_epsilon=float(value["minimum_epsilon"]),
            exploration_scale=float(value["exploration_scale"]),
        )

        def decode(name: str, dtype: np.dtype[Any], shape: tuple[int, ...]) -> np.ndarray:
            raw = zlib.decompress(base64.b64decode(str(value[name])))
            result = np.frombuffer(raw, dtype=dtype).copy()
            if result.size != int(np.prod(shape)):
                raise ValueError(f"Checkpoint policy array {name} has the wrong size")
            return result.reshape(shape)

        policy.q_values = decode(
            "q_values_f32_zlib",
            np.dtype(np.float32),
            (policy.bucket_count, policy.action_count),
        )
        policy.visits = decode(
            "visits_u32_zlib",
            np.dtype(np.uint32),
            (policy.bucket_count,),
        )
        policy.updates = int(value["updates"])
        policy.exploratory_actions = int(value["exploratory_actions"])
        return policy


@dataclass(slots=True)
class RewardTracker:
    """Tracks declared rewards without exposing them to pixels-only policy observations."""

    mode: str
    total_reward: float = 0.0
    visual_reward: float = 0.0
    outcome_reward: float = 0.0
    seen_maps: set[int] = field(default_factory=set)
    seen_positions: set[tuple[int, int, int]] = field(default_factory=set)
    seen_battles: set[int] = field(default_factory=set)
    max_party_count: int = 0
    badge_bits: int = 0
    game_started_seen: bool = False
    reward_events: int = 0

    def score(
        self,
        *,
        visually_novel: bool,
        state: PokemonRedState | None,
    ) -> tuple[float, dict[str, float]]:
        components: dict[str, float] = {}
        if self.mode == "curious":
            if visually_novel:
                components["visual_novelty"] = 1.0
        else:
            if visually_novel:
                components["visual_novelty"] = 0.05
            if state is None:
                raise ValueError(f"{self.mode} reward requires a referee state")
            if state.game_started and not self.game_started_seen:
                self.game_started_seen = True
                components["game_started"] = 3.0
            if state.game_started and state.map_id is not None:
                if state.map_id not in self.seen_maps:
                    self.seen_maps.add(state.map_id)
                    components["new_map"] = 5.0
                if state.player_x is not None and state.player_y is not None:
                    position = (state.map_id, state.player_x, state.player_y)
                    if position not in self.seen_positions:
                        self.seen_positions.add(position)
                        components["new_position"] = 0.20
            party_count = state.party_count or 0
            if party_count > self.max_party_count:
                components["party_increase"] = 25.0 * (party_count - self.max_party_count)
                self.max_party_count = party_count
            battle_state = state.battle_state or 0
            if battle_state and battle_state not in self.seen_battles:
                self.seen_battles.add(battle_state)
                components["new_battle_kind"] = 10.0
            badges = state.badge_bits or 0
            new_badges = (badges & ~self.badge_bits).bit_count()
            if new_badges:
                components["new_badge"] = 100.0 * new_badges
                self.badge_bits |= badges

        reward = sum(components.values())
        self.total_reward += reward
        self.visual_reward += components.get("visual_novelty", 0.0)
        self.outcome_reward += reward - components.get("visual_novelty", 0.0)
        if components:
            self.reward_events += 1
        return reward, components

    def checkpoint_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "mode": self.mode,
            "total_reward": self.total_reward,
            "visual_reward": self.visual_reward,
            "outcome_reward": self.outcome_reward,
            "seen_maps": sorted(self.seen_maps),
            "seen_positions": [list(value) for value in sorted(self.seen_positions)],
            "seen_battles": sorted(self.seen_battles),
            "max_party_count": self.max_party_count,
            "badge_bits": self.badge_bits,
            "game_started_seen": self.game_started_seen,
            "reward_events": self.reward_events,
        }

    @classmethod
    def from_checkpoint_dict(cls, value: dict[str, Any]) -> RewardTracker:
        return cls(
            mode=str(value["mode"]),
            total_reward=float(value["total_reward"]),
            visual_reward=float(value["visual_reward"]),
            outcome_reward=float(value["outcome_reward"]),
            seen_maps={int(item) for item in value["seen_maps"]},
            seen_positions={tuple(int(part) for part in item) for item in value["seen_positions"]},
            seen_battles={int(item) for item in value["seen_battles"]},
            max_party_count=int(value["max_party_count"]),
            badge_bits=int(value["badge_bits"]),
            game_started_seen=bool(value["game_started_seen"]),
            reward_events=int(value["reward_events"]),
        )
