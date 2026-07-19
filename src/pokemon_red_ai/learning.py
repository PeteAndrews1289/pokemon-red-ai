from __future__ import annotations

import base64
import hashlib
import random
import zlib
from collections import Counter, deque
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
            (semantic_state.player_x or 0) // 4,
            (semantic_state.player_y or 0) // 4,
            semantic_state.party_count or 0,
            semantic_state.battle_state or 0,
            semantic_state.badge_bits or 0,
            min(semantic_state.pokedex_seen_count, 255),
            min(semantic_state.pokedex_owned_count, 255),
            min(semantic_state.max_party_level, 255),
            min(len(semantic_state.bag_item_ids or ()), 255),
            int(bool(semantic_state.got_pokedex)),
        )
        digest.update(bytes(values))
    return digest.digest()


@dataclass(slots=True)
class HashedQPolicy:
    """Bounded n-step Q learner with replay for long, sparse-reward runs."""

    action_count: int
    bucket_count: int = 16_384
    learning_rate: float = 0.12
    discount: float = 0.97
    minimum_epsilon: float = 0.05
    exploration_scale: float = 40.0
    n_step: int = 128
    replay_capacity: int = 100_000
    replay_batch_size: int = 16
    replay_interval: int = 4
    important_capacity: int = 10_000
    q_values: np.ndarray = field(init=False, repr=False)
    visits: np.ndarray = field(init=False, repr=False)
    replay_buckets: np.ndarray = field(init=False, repr=False)
    replay_actions: np.ndarray = field(init=False, repr=False)
    replay_rewards: np.ndarray = field(init=False, repr=False)
    replay_next_buckets: np.ndarray = field(init=False, repr=False)
    replay_discounts: np.ndarray = field(init=False, repr=False)
    pending: deque[tuple[int, int, float]] = field(init=False, repr=False)
    important: list[tuple[int, int, float, int, float]] = field(init=False, repr=False)
    updates: int = 0
    exploratory_actions: int = 0
    environment_steps: int = 0
    replay_size: int = 0
    replay_index: int = 0
    replay_updates: int = 0
    important_index: int = 0

    def __post_init__(self) -> None:
        if self.action_count < 2:
            raise ValueError("A learning policy needs at least two actions")
        if self.bucket_count < 1_024:
            raise ValueError("Q-policy bucket count must be at least 1,024")
        if self.n_step < 1:
            raise ValueError("n_step must be positive")
        if self.replay_capacity < 1:
            raise ValueError("replay_capacity must be positive")
        if not 1 <= self.replay_batch_size <= self.replay_capacity:
            raise ValueError("replay_batch_size must fit inside replay_capacity")
        if self.replay_interval < 1:
            raise ValueError("replay_interval must be positive")
        if self.important_capacity < 1:
            raise ValueError("important_capacity must be positive")
        self.q_values = np.zeros((self.bucket_count, self.action_count), dtype=np.float32)
        self.visits = np.zeros(self.bucket_count, dtype=np.uint32)
        self.replay_buckets = np.zeros(self.replay_capacity, dtype=np.uint32)
        self.replay_actions = np.zeros(self.replay_capacity, dtype=np.uint8)
        self.replay_rewards = np.zeros(self.replay_capacity, dtype=np.float32)
        self.replay_next_buckets = np.zeros(self.replay_capacity, dtype=np.uint32)
        self.replay_discounts = np.zeros(self.replay_capacity, dtype=np.float32)
        self.pending = deque()
        self.important = []

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

    def _update_target(
        self,
        bucket: int,
        action_index: int,
        reward: float,
        next_bucket: int,
        bootstrap_discount: float,
    ) -> None:
        current = float(self.q_values[bucket, action_index])
        target = reward + bootstrap_discount * float(self.q_values[next_bucket].max())
        updated = current + self.learning_rate * (target - current)
        self.q_values[bucket, action_index] = np.float32(np.clip(updated, -1_000, 1_000))
        self.updates += 1

    def update(self, bucket: int, action_index: int, reward: float, next_key: bytes) -> None:
        """Apply a direct one-step update; retained for diagnostics and compatibility."""

        self._update_target(
            bucket,
            action_index,
            reward,
            self.bucket(next_key),
            self.discount,
        )

    def _remember(
        self,
        bucket: int,
        action_index: int,
        reward: float,
        next_bucket: int,
        bootstrap_discount: float,
    ) -> None:
        index = self.replay_index
        self.replay_buckets[index] = bucket
        self.replay_actions[index] = action_index
        self.replay_rewards[index] = reward
        self.replay_next_buckets[index] = next_bucket
        self.replay_discounts[index] = bootstrap_discount
        self.replay_index = (index + 1) % self.replay_capacity
        self.replay_size = min(self.replay_size + 1, self.replay_capacity)
        if abs(reward) > 1e-12:
            transition = (
                bucket,
                action_index,
                reward,
                next_bucket,
                bootstrap_discount,
            )
            if len(self.important) < self.important_capacity:
                self.important.append(transition)
            else:
                self.important[self.important_index] = transition
                self.important_index = (self.important_index + 1) % self.important_capacity

    def observe_transition(
        self,
        bucket: int,
        action_index: int,
        reward: float,
        next_key: bytes,
        rng: random.Random,
    ) -> None:
        """Learn an n-step transition and revisit past transitions from replay."""

        self.environment_steps += 1
        next_bucket = self.bucket(next_key)
        self.pending.append((bucket, action_index, float(reward)))
        if len(self.pending) >= self.n_step:
            discounted_reward = 0.0
            weight = 1.0
            for _pending_bucket, _pending_action, pending_reward in self.pending:
                discounted_reward += weight * pending_reward
                weight *= self.discount
            first_bucket, first_action, _first_reward = self.pending.popleft()
            self._remember(first_bucket, first_action, discounted_reward, next_bucket, weight)
            self._update_target(
                first_bucket,
                first_action,
                discounted_reward,
                next_bucket,
                weight,
            )

        if (
            self.environment_steps % self.replay_interval == 0
            and self.replay_size >= self.replay_batch_size
        ):
            for batch_index in range(self.replay_batch_size):
                if self.important and batch_index % 2 == 0:
                    transition = self.important[rng.randrange(len(self.important))]
                    replay_bucket, replay_action, replay_reward, replay_next, replay_discount = (
                        transition
                    )
                else:
                    index = rng.randrange(self.replay_size)
                    replay_bucket = int(self.replay_buckets[index])
                    replay_action = int(self.replay_actions[index])
                    replay_reward = float(self.replay_rewards[index])
                    replay_next = int(self.replay_next_buckets[index])
                    replay_discount = float(self.replay_discounts[index])
                self._update_target(
                    replay_bucket,
                    replay_action,
                    replay_reward,
                    replay_next,
                    replay_discount,
                )
                self.replay_updates += 1

    @property
    def occupied_buckets(self) -> int:
        return int(np.count_nonzero(self.visits))

    def checkpoint_dict(self) -> dict[str, Any]:
        def encode(array: np.ndarray) -> str:
            return base64.b64encode(zlib.compress(array.tobytes(), level=3)).decode("ascii")

        return {
            "schema_version": 2,
            "action_count": self.action_count,
            "bucket_count": self.bucket_count,
            "learning_rate": self.learning_rate,
            "discount": self.discount,
            "minimum_epsilon": self.minimum_epsilon,
            "exploration_scale": self.exploration_scale,
            "n_step": self.n_step,
            "replay_capacity": self.replay_capacity,
            "replay_batch_size": self.replay_batch_size,
            "replay_interval": self.replay_interval,
            "important_capacity": self.important_capacity,
            "q_values_f32_zlib": encode(self.q_values),
            "visits_u32_zlib": encode(self.visits),
            "replay_buckets_u32_zlib": encode(self.replay_buckets),
            "replay_actions_u8_zlib": encode(self.replay_actions),
            "replay_rewards_f32_zlib": encode(self.replay_rewards),
            "replay_next_buckets_u32_zlib": encode(self.replay_next_buckets),
            "replay_discounts_f32_zlib": encode(self.replay_discounts),
            "pending": [list(value) for value in self.pending],
            "important": [list(value) for value in self.important],
            "updates": self.updates,
            "exploratory_actions": self.exploratory_actions,
            "environment_steps": self.environment_steps,
            "replay_size": self.replay_size,
            "replay_index": self.replay_index,
            "replay_updates": self.replay_updates,
            "important_index": self.important_index,
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
            n_step=int(value.get("n_step", 1)),
            replay_capacity=int(value.get("replay_capacity", 1)),
            replay_batch_size=int(value.get("replay_batch_size", 1)),
            replay_interval=int(value.get("replay_interval", 1)),
            important_capacity=int(value.get("important_capacity", 1)),
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
        if int(value.get("schema_version", 1)) >= 2:
            policy.replay_buckets = decode(
                "replay_buckets_u32_zlib",
                np.dtype(np.uint32),
                (policy.replay_capacity,),
            )
            policy.replay_actions = decode(
                "replay_actions_u8_zlib",
                np.dtype(np.uint8),
                (policy.replay_capacity,),
            )
            policy.replay_rewards = decode(
                "replay_rewards_f32_zlib",
                np.dtype(np.float32),
                (policy.replay_capacity,),
            )
            policy.replay_next_buckets = decode(
                "replay_next_buckets_u32_zlib",
                np.dtype(np.uint32),
                (policy.replay_capacity,),
            )
            policy.replay_discounts = decode(
                "replay_discounts_f32_zlib",
                np.dtype(np.float32),
                (policy.replay_capacity,),
            )
            policy.pending = deque(
                (int(item[0]), int(item[1]), float(item[2])) for item in value["pending"]
            )
            policy.important = [
                (int(item[0]), int(item[1]), float(item[2]), int(item[3]), float(item[4]))
                for item in value.get("important", [])
            ]
        policy.updates = int(value["updates"])
        policy.exploratory_actions = int(value["exploratory_actions"])
        policy.environment_steps = int(value.get("environment_steps", policy.updates))
        policy.replay_size = int(value.get("replay_size", 0))
        policy.replay_index = int(value.get("replay_index", 0))
        policy.replay_updates = int(value.get("replay_updates", 0))
        policy.important_index = int(value.get("important_index", 0))
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
    seen_warps: set[tuple[int, int]] = field(default_factory=set)
    seen_battles: set[int] = field(default_factory=set)
    seen_pokedex_species: set[int] = field(default_factory=set)
    owned_pokedex_species: set[int] = field(default_factory=set)
    seen_event_flags: set[int] = field(default_factory=set)
    seen_bag_items: set[int] = field(default_factory=set)
    seen_moves: set[int] = field(default_factory=set)
    max_party_count: int = 0
    max_party_level: int = 0
    badge_bits: int = 0
    game_started_seen: bool = False
    reward_events: int = 0
    blackouts: int = 0
    last_battle_state: int = 0
    last_map_id: int | None = None
    last_position: tuple[int, int, int] | None = None
    last_action: str | None = None
    action_streak: int = 0
    stationary_steps: int = 0
    position_visits: Counter[tuple[int, int, int]] = field(default_factory=Counter)
    pokedex_initialized: bool = False
    event_flags_initialized: bool = False
    bag_initialized: bool = False
    got_pokedex_rewarded: bool = False
    had_oaks_parcel: bool = False
    parcel_delivered: bool = False
    got_pokeballs_rewarded: bool = False
    required_items_rewarded: set[int] = field(default_factory=set)
    component_totals: Counter[str] = field(default_factory=Counter)

    OAKS_PARCEL = 0x46
    POKE_BALL = 0x04
    REQUIRED_ITEM_IDS = frozenset(
        {
            0x06,  # Bicycle
            0x2B,  # Secret Key
            0x30,  # Card Key
            0x3F,  # S.S. Ticket
            0x40,  # Gold Teeth
            0x48,  # Silph Scope
            0x49,  # Poke Flute
            0x4A,  # Lift Key
            0xC4,  # HM01 Cut
            0xC5,  # HM02 Fly
            0xC6,  # HM03 Surf
            0xC7,  # HM04 Strength
            0xC8,  # HM05 Flash
        }
    )

    @staticmethod
    def _set_bits(value: bytes | None) -> set[int]:
        if value is None:
            return set()
        return {
            byte_index * 8 + bit
            for byte_index, byte in enumerate(value)
            for bit in range(8)
            if byte & (1 << bit)
        }

    def _track_action_and_loops(
        self,
        components: dict[str, float],
        *,
        action_button: str | None,
        position: tuple[int, int, int] | None,
    ) -> None:
        if action_button is not None:
            if action_button == self.last_action:
                self.action_streak += 1
            else:
                self.last_action = action_button
                self.action_streak = 1
            if self.action_streak == 4:
                components["repeated_action"] = -0.02
            elif self.action_streak >= 6:
                components["repeated_action"] = -0.05

        if position is None:
            return
        self.position_visits[position] += 1
        visits = self.position_visits[position]
        if visits == 4:
            components["revisited_position"] = -0.02
        elif visits in {8, 16, 32}:
            components["revisited_position"] = -0.05
        if position == self.last_position:
            self.stationary_steps += 1
            if self.stationary_steps >= 64 and self.stationary_steps % 64 == 0:
                components["stationary_loop"] = -0.05
        else:
            self.stationary_steps = 0
            self.last_position = position

    def score(
        self,
        *,
        visually_novel: bool,
        state: PokemonRedState | None,
        action_button: str | None = None,
    ) -> tuple[float, dict[str, float]]:
        components: dict[str, float] = {}
        if self.mode == "curious":
            if visually_novel:
                components["visual_novelty"] = 1.0
        elif self.mode == "observer":
            if state is None:
                raise ValueError("observer requires a referee state")
            self._score_semantic(state, action_button=None, components={})
            return 0.0, {}
        else:
            if state is None:
                raise ValueError(f"{self.mode} reward requires a referee state")
            self._score_semantic(state, action_button=action_button, components=components)

        reward = sum(components.values())
        self.total_reward += reward
        self.visual_reward += components.get("visual_novelty", 0.0)
        self.outcome_reward += reward - components.get("visual_novelty", 0.0)
        if components:
            self.reward_events += 1
            self.component_totals.update(components)
        return reward, components

    def _score_semantic(
        self,
        state: PokemonRedState,
        *,
        action_button: str | None,
        components: dict[str, float],
    ) -> None:
        rewards_enabled = self.mode in {"outcome", "conventional"}
        if state.game_started and not self.game_started_seen:
            self.game_started_seen = True
            if rewards_enabled:
                components["game_started"] = 3.0

        position: tuple[int, int, int] | None = None
        if state.game_started and state.map_id is not None:
            if state.map_id not in self.seen_maps:
                self.seen_maps.add(state.map_id)
                if rewards_enabled:
                    components["new_map"] = 20.0
            if self.last_map_id is not None and state.map_id != self.last_map_id:
                warp = (self.last_map_id, state.map_id)
                if warp not in self.seen_warps:
                    self.seen_warps.add(warp)
                    if rewards_enabled:
                        components["new_warp"] = 5.0
            self.last_map_id = state.map_id
            if state.player_x is not None and state.player_y is not None:
                position = (state.map_id, state.player_x, state.player_y)
                if position not in self.seen_positions:
                    self.seen_positions.add(position)
                    if rewards_enabled:
                        components["new_position"] = 0.03

        party_count = state.party_count or 0
        if party_count > self.max_party_count:
            if rewards_enabled:
                components["party_increase"] = 25.0 * (party_count - self.max_party_count)
            self.max_party_count = party_count
        self.max_party_level = max(self.max_party_level, state.max_party_level)

        current_moves = set(state.party_moves or ())
        new_moves = current_moves - self.seen_moves
        if new_moves and self.seen_moves and rewards_enabled:
            components["new_move"] = 2.0 * len(new_moves)
        self.seen_moves |= current_moves

        battle_state = state.battle_state or 0
        if battle_state == 0xFF:
            if self.last_battle_state != 0xFF:
                self.blackouts += 1
                if rewards_enabled and self.blackouts == 1:
                    components["blackout"] = -2.0
            self.seen_battles.add(0xFF)
        elif battle_state in {1, 2} and battle_state not in self.seen_battles:
            self.seen_battles.add(battle_state)
            if rewards_enabled:
                components["new_battle_kind"] = 5.0
        self.last_battle_state = battle_state

        badges = state.badge_bits or 0
        new_badges = (badges & ~self.badge_bits).bit_count()
        if new_badges and rewards_enabled:
            components["new_badge"] = 200.0 * new_badges
        self.badge_bits |= badges

        # StarterDex temporarily writes preview flags into wPokedexOwned while the player chooses a
        # starter. Those bits are a rendering trick, not captures, so the sealed referee ignores
        # both Pokédex bitfields until the actual Pokédex has been obtained.
        if state.got_pokedex:
            seen_species = self._set_bits(state.pokedex_seen)
            owned_species = self._set_bits(state.pokedex_owned)
            newly_seen = seen_species - self.seen_pokedex_species
            newly_owned = owned_species - self.owned_pokedex_species
            if newly_seen and rewards_enabled:
                components["new_species_seen"] = 3.0 * len(newly_seen)
            if newly_owned and rewards_enabled:
                components["new_species_owned"] = 25.0 * len(newly_owned)
            self.seen_pokedex_species |= newly_seen
            self.owned_pokedex_species |= newly_owned
            self.pokedex_initialized = True

        event_flags = self._set_bits(state.event_flags)
        if not self.event_flags_initialized:
            self.seen_event_flags = set(event_flags)
            self.event_flags_initialized = True
        else:
            new_events = event_flags - self.seen_event_flags
            if new_events and rewards_enabled:
                components["new_event_flag"] = 8.0 * len(new_events)
            self.seen_event_flags |= new_events

        bag_items = set(state.bag_item_ids or ())
        if not self.bag_initialized:
            self.seen_bag_items = set(bag_items)
            self.bag_initialized = True
        else:
            self.seen_bag_items |= bag_items

        if self.mode == "conventional":
            if self.OAKS_PARCEL in bag_items and not self.had_oaks_parcel:
                self.had_oaks_parcel = True
                components["oaks_parcel_obtained"] = 30.0
            if (
                self.had_oaks_parcel
                and self.OAKS_PARCEL not in bag_items
                and not self.parcel_delivered
            ):
                self.parcel_delivered = True
                components["oaks_parcel_delivered"] = 40.0
            if state.got_pokedex and not self.got_pokedex_rewarded:
                self.got_pokedex_rewarded = True
                components["pokedex_obtained"] = 50.0
            if self.POKE_BALL in bag_items and not self.got_pokeballs_rewarded:
                self.got_pokeballs_rewarded = True
                components["pokeballs_obtained"] = 15.0
            new_required_items = (
                bag_items & self.REQUIRED_ITEM_IDS
            ) - self.required_items_rewarded
            if new_required_items:
                components["required_item_obtained"] = 50.0 * len(new_required_items)
                self.required_items_rewarded |= new_required_items

        if rewards_enabled:
            self._track_action_and_loops(
                components,
                action_button=action_button,
                position=position,
            )

    def checkpoint_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "mode": self.mode,
            "total_reward": self.total_reward,
            "visual_reward": self.visual_reward,
            "outcome_reward": self.outcome_reward,
            "seen_maps": sorted(self.seen_maps),
            "seen_positions": [list(value) for value in sorted(self.seen_positions)],
            "seen_warps": [list(value) for value in sorted(self.seen_warps)],
            "seen_battles": sorted(self.seen_battles),
            "seen_pokedex_species": sorted(self.seen_pokedex_species),
            "owned_pokedex_species": sorted(self.owned_pokedex_species),
            "seen_event_flags": sorted(self.seen_event_flags),
            "seen_bag_items": sorted(self.seen_bag_items),
            "seen_moves": sorted(self.seen_moves),
            "max_party_count": self.max_party_count,
            "max_party_level": self.max_party_level,
            "badge_bits": self.badge_bits,
            "game_started_seen": self.game_started_seen,
            "reward_events": self.reward_events,
            "blackouts": self.blackouts,
            "last_battle_state": self.last_battle_state,
            "last_map_id": self.last_map_id,
            "last_position": None if self.last_position is None else list(self.last_position),
            "last_action": self.last_action,
            "action_streak": self.action_streak,
            "stationary_steps": self.stationary_steps,
            "position_visits": [
                [*position, visits] for position, visits in sorted(self.position_visits.items())
            ],
            "pokedex_initialized": self.pokedex_initialized,
            "event_flags_initialized": self.event_flags_initialized,
            "bag_initialized": self.bag_initialized,
            "got_pokedex_rewarded": self.got_pokedex_rewarded,
            "had_oaks_parcel": self.had_oaks_parcel,
            "parcel_delivered": self.parcel_delivered,
            "got_pokeballs_rewarded": self.got_pokeballs_rewarded,
            "required_items_rewarded": sorted(self.required_items_rewarded),
            "component_totals": dict(self.component_totals),
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
            seen_warps={
                tuple(int(part) for part in item) for item in value.get("seen_warps", [])
            },
            seen_battles={int(item) for item in value["seen_battles"]},
            seen_pokedex_species={
                int(item) for item in value.get("seen_pokedex_species", [])
            },
            owned_pokedex_species={
                int(item) for item in value.get("owned_pokedex_species", [])
            },
            seen_event_flags={int(item) for item in value.get("seen_event_flags", [])},
            seen_bag_items={int(item) for item in value.get("seen_bag_items", [])},
            seen_moves={int(item) for item in value.get("seen_moves", [])},
            max_party_count=int(value["max_party_count"]),
            max_party_level=int(value.get("max_party_level", 0)),
            badge_bits=int(value["badge_bits"]),
            game_started_seen=bool(value["game_started_seen"]),
            reward_events=int(value["reward_events"]),
            blackouts=int(value.get("blackouts", 0)),
            last_battle_state=int(value.get("last_battle_state", 0)),
            last_map_id=(
                None if value.get("last_map_id") is None else int(value["last_map_id"])
            ),
            last_position=(
                None
                if value.get("last_position") is None
                else tuple(int(part) for part in value["last_position"])
            ),
            last_action=value.get("last_action"),
            action_streak=int(value.get("action_streak", 0)),
            stationary_steps=int(value.get("stationary_steps", 0)),
            position_visits=Counter(
                {
                    tuple(int(part) for part in item[:3]): int(item[3])
                    for item in value.get("position_visits", [])
                }
            ),
            pokedex_initialized=bool(value.get("pokedex_initialized", False)),
            event_flags_initialized=bool(value.get("event_flags_initialized", False)),
            bag_initialized=bool(value.get("bag_initialized", False)),
            got_pokedex_rewarded=bool(value.get("got_pokedex_rewarded", False)),
            had_oaks_parcel=bool(value.get("had_oaks_parcel", False)),
            parcel_delivered=bool(value.get("parcel_delivered", False)),
            got_pokeballs_rewarded=bool(value.get("got_pokeballs_rewarded", False)),
            required_items_rewarded={
                int(item) for item in value.get("required_items_rewarded", [])
            },
            component_totals=Counter(
                {str(key): float(item) for key, item in value.get("component_totals", {}).items()}
            ),
        )
