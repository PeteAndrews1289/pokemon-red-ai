from __future__ import annotations

import contextlib
import hashlib
import json
import os
import random
from collections import Counter
from collections.abc import Mapping
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from pokemon_red_ai.apprentice_data import preprocess_apprentice_frame
from pokemon_red_ai.apprentice_model import build_apprentice_policy, require_torch
from pokemon_red_ai.blind import (
    ACTION_HOLD_FRAMES,
    ACTION_RELEASE_FRAMES,
    BLIND_ACTIONS,
    BlindAction,
    PixelsOnlyActor,
)
from pokemon_red_ai.expedition import MilestoneProgress
from pokemon_red_ai.milestones import MILESTONE_BY_KEY
from pokemon_red_ai.quest_navigation import active_goal, route_guidance
from pokemon_red_ai.state import PokemonRedState

FRONTIER_LEARNER_POLICY_ID = "visual-frontier-self-imitation-v1"
FRONTIER_LEARNER_SCHEMA = 1
VIRIDIAN_CITY_MAP_ID = 0x01
VIRIDIAN_MART_DOOR = (29, 19)
NAVIGATION_RECOVERY_ACTIONS = 12
NAVIGATION_RECOVERY_EPISODE_CAP = 3


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _parameter_sha256(model: Any) -> str:
    digest = hashlib.sha256()
    for name, tensor in sorted(model.state_dict().items()):
        value = tensor.detach().cpu().contiguous().numpy()
        descriptor = json.dumps(
            {"name": name, "dtype": value.dtype.str, "shape": list(value.shape)},
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        digest.update(len(descriptor).to_bytes(8, "big"))
        digest.update(descriptor)
        digest.update(value.tobytes())
    return digest.hexdigest()


@dataclass(frozen=True, slots=True)
class FullGameRewardConfig:
    """Trainer-only rewards that apply uniformly across the complete milestone catalogue."""

    milestone: float = 1_000.0
    badge: float = 500.0
    new_event: float = 20.0
    new_map: float = 25.0
    new_warp: float = 10.0
    new_position: float = 0.05
    party_member: float = 50.0
    party_level: float = 5.0
    new_move: float = 3.0
    species_seen: float = 5.0
    species_owned: float = 30.0
    new_item: float = 10.0
    experience_gain: float = 0.02
    experience_gain_cap: float = 500.0
    battle_success: float = 2.0
    opponent_damage: float = 2.0
    opponent_damage_cap: float = 4.0
    lesson_navigation: float = 0.25
    lesson_progress: float = 5.0
    goal_navigation: float = 8.0
    navigation_recovery: float = 2.0
    blackout: float = -20.0
    visual_loop: float = -2.0
    repeated_action: float = -0.02

    def __post_init__(self) -> None:
        values = asdict(self)
        if any(not np.isfinite(value) for value in values.values()):
            raise ValueError("Frontier rewards must be finite")
        if any(
            values[name] < 0
            for name in values
            if name not in {"blackout", "visual_loop", "repeated_action"}
        ):
            raise ValueError("Progress rewards cannot be negative")
        if any(values[name] > 0 for name in ("blackout", "visual_loop", "repeated_action")):
            raise ValueError("Frontier penalties cannot be positive")


@dataclass(frozen=True, slots=True)
class RewardStep:
    total: float
    components: Mapping[str, float]
    battle_event: str | None = None


def _set_bits(value: bytes | None) -> set[int]:
    if value is None:
        return set()
    return {
        byte_index * 8 + bit
        for byte_index, byte in enumerate(value)
        for bit in range(8)
        if byte & (1 << bit)
    }


@dataclass(slots=True)
class FullGameRewardTracker:
    """Persistent trainer memory for dense, non-repeatable progress rewards.

    The pixel actor never receives this object. It exists to make learning signals and their
    narrative ledger explicit while preventing a restored checkpoint from being paid repeatedly
    for progress that the run has already observed.
    """

    config: FullGameRewardConfig = field(default_factory=FullGameRewardConfig)
    seen_maps: set[int] = field(default_factory=set)
    seen_positions: set[tuple[int, int, int]] = field(default_factory=set)
    seen_warps: set[tuple[int, int]] = field(default_factory=set)
    seen_events: set[int] = field(default_factory=set)
    seen_species: set[int] = field(default_factory=set)
    owned_species: set[int] = field(default_factory=set)
    seen_items: set[int] = field(default_factory=set)
    seen_moves: set[int] = field(default_factory=set)
    badge_bits: int = 0
    max_party_count: int = 0
    max_party_level: int = 0
    max_party_experience: int = 0
    best_milestone_index: int = 0
    total_reward: float = 0.0
    reward_events: int = 0
    component_totals: Counter[str] = field(default_factory=Counter)
    _initialized: bool = False
    _last_map: int | None = None
    _last_battle: int = 0
    _last_party_experience: int | None = None
    _battle_progressed: bool = False
    _enemy_hp_floor: int | None = None
    _last_enemy_hp: int | None = None
    _battle_damage_credit: float = 0.0
    _episode_mart_distance: int | None = None
    _episode_mart_script: int = 0
    _episode_goal_key: str | None = None
    _episode_route_distance: int | None = None
    _episode_last_position: tuple[int, int, int] | None = None
    _episode_stationary_actions: int = 0
    _episode_navigation_recoveries: int = 0
    _last_action: str | None = None
    _action_streak: int = 0

    def prime(self, state: PokemonRedState, progress: MilestoneProgress) -> None:
        """Observe a restored parent without paying rewards for its inherited state."""

        self.seen_maps |= {state.map_id} if state.map_id is not None else set()
        if state.map_id is not None and state.player_x is not None and state.player_y is not None:
            self.seen_positions.add((state.map_id, state.player_x, state.player_y))
        self.seen_events |= _set_bits(state.event_flags)
        self.seen_species |= _set_bits(state.pokedex_seen) if state.got_pokedex else set()
        self.owned_species |= _set_bits(state.pokedex_owned) if state.got_pokedex else set()
        self.seen_items |= set(state.bag_item_ids or ())
        self.seen_moves |= set(state.party_moves or ())
        self.badge_bits |= state.badge_bits or 0
        self.max_party_count = max(self.max_party_count, state.party_count or 0)
        self.max_party_level = max(self.max_party_level, state.max_party_level)
        self.max_party_experience = max(self.max_party_experience, state.total_party_experience)
        self.best_milestone_index = max(self.best_milestone_index, progress.index)
        self._initialized = True
        self._last_map = state.map_id
        self._last_battle = state.battle_state or 0
        self._last_party_experience = state.total_party_experience
        self._battle_progressed = False
        self._prime_enemy_health(state)
        self._episode_mart_distance = (
            self._mart_distance(state) if progress.key == "reached_viridian_city" else None
        )
        self._episode_mart_script = state.viridian_mart_script or 0
        guidance = route_guidance(state, progress, self.seen_warps)
        self._episode_goal_key = guidance.goal_key
        self._episode_route_distance = guidance.distance
        self._episode_last_position = self._position(state)
        self._episode_stationary_actions = 0
        self._episode_navigation_recoveries = 0
        self._last_action = None
        self._action_streak = 0

    def score(
        self,
        state: PokemonRedState,
        progress: MilestoneProgress,
        *,
        action_button: str,
        loop_detected: bool,
    ) -> RewardStep:
        if not self._initialized:
            self.prime(state, progress)
            return RewardStep(0.0, {})
        c = self.config
        components: dict[str, float] = {}
        battle = state.battle_state or 0
        previous_battle = self._last_battle
        active_battle = battle in {1, 2} or previous_battle in {1, 2}
        battle_event: str | None = None
        if previous_battle not in {1, 2} and battle in {1, 2}:
            self._battle_progressed = False
            self._prime_enemy_health(state)
            battle_event = "started"

        if battle in {1, 2}:
            enemy_hp = state.enemy_hp
            enemy_max_hp = state.enemy_max_hp
            if (
                enemy_hp is not None
                and enemy_max_hp is not None
                and enemy_max_hp > 0
                and self._enemy_hp_floor is not None
                and enemy_hp < self._enemy_hp_floor
            ):
                fraction = (self._enemy_hp_floor - enemy_hp) / enemy_max_hp
                available = max(0.0, c.opponent_damage_cap - self._battle_damage_credit)
                credit = min(c.opponent_damage * fraction, available)
                if credit > 0:
                    components["opponent_damage"] = credit
                    self._battle_damage_credit += credit
                self._enemy_hp_floor = enemy_hp
            elif enemy_hp is not None and self._last_enemy_hp == 0 and enemy_hp > 0:
                # A trainer has sent out a new opponent. Healing never resets the floor.
                self._enemy_hp_floor = enemy_hp
            self._last_enemy_hp = enemy_hp

        if progress.index > self.best_milestone_index:
            delta = progress.index - self.best_milestone_index
            components["named_milestone"] = c.milestone * delta
            self.best_milestone_index = progress.index

        mart_distance = (
            self._mart_distance(state) if progress.key == "reached_viridian_city" else None
        )
        if mart_distance is not None:
            if self._episode_mart_distance is None:
                self._episode_mart_distance = mart_distance
            elif mart_distance < self._episode_mart_distance:
                components["mart_approach"] = c.lesson_navigation * (
                    self._episode_mart_distance - mart_distance
                )
                self._episode_mart_distance = mart_distance

        mart_script = (
            state.viridian_mart_script if progress.key == "entered_viridian_mart" else None
        )
        if mart_script is not None and mart_script > self._episode_mart_script:
            components["mart_dialogue_progress"] = c.lesson_progress * (
                mart_script - self._episode_mart_script
            )
            self._episode_mart_script = mart_script

        if state.map_id is not None:
            if state.map_id not in self.seen_maps:
                components["new_map"] = c.new_map
                self.seen_maps.add(state.map_id)
            if self._last_map is not None and state.map_id != self._last_map:
                warp = (self._last_map, state.map_id)
                if warp not in self.seen_warps:
                    components["new_warp"] = c.new_warp
                    self.seen_warps.add(warp)
            self._last_map = state.map_id
            if state.player_x is not None and state.player_y is not None:
                position = (state.map_id, state.player_x, state.player_y)
                if position not in self.seen_positions:
                    components["new_position"] = c.new_position
                    self.seen_positions.add(position)

        guidance = route_guidance(state, progress, self.seen_warps)
        if guidance.goal_key != self._episode_goal_key:
            self._episode_goal_key = guidance.goal_key
            self._episode_route_distance = guidance.distance
        elif guidance.distance is not None and self._episode_route_distance is not None:
            delta = self._episode_route_distance - guidance.distance
            if delta:
                # Signed potential change: advancing pays, undoing the move takes the same credit
                # back, and oscillation therefore cannot manufacture reward.
                components["goal_route_progress"] = c.goal_navigation * delta
            self._episode_route_distance = guidance.distance
        elif guidance.distance is not None:
            self._episode_route_distance = guidance.distance

        position = self._position(state)
        goal_key = active_goal(progress)
        navigation_active = bool(
            goal_key is not None and MILESTONE_BY_KEY[goal_key].kind == "landmark" and battle == 0
        )
        if not navigation_active or position is None:
            self._episode_stationary_actions = 0
        elif position == self._episode_last_position:
            self._episode_stationary_actions += 1
        else:
            if (
                self._episode_stationary_actions >= NAVIGATION_RECOVERY_ACTIONS
                and self._episode_navigation_recoveries < NAVIGATION_RECOVERY_EPISODE_CAP
            ):
                components["navigation_recovery"] = c.navigation_recovery
                self._episode_navigation_recoveries += 1
            self._episode_stationary_actions = 0
        self._episode_last_position = position

        events = _set_bits(state.event_flags)
        new_events = events - self.seen_events
        if new_events:
            components["new_event"] = c.new_event * len(new_events)
            self.seen_events |= new_events

        badges = state.badge_bits or 0
        new_badges = (badges & ~self.badge_bits).bit_count()
        if new_badges:
            components["new_badge"] = c.badge * new_badges
            self.badge_bits |= badges

        party_count = state.party_count or 0
        if party_count > self.max_party_count:
            components["party_member"] = c.party_member * (party_count - self.max_party_count)
            self.max_party_count = party_count
        if state.max_party_level > self.max_party_level:
            components["party_level"] = c.party_level * (
                state.max_party_level - self.max_party_level
            )
            self.max_party_level = state.max_party_level

        party_experience = state.total_party_experience
        previous_experience = self._last_party_experience
        if (
            previous_experience is not None
            and party_experience > previous_experience
            and active_battle
        ):
            self._battle_progressed = True
        if party_experience > self.max_party_experience:
            gained = party_experience - self.max_party_experience
            components["experience_gain"] = c.experience_gain * min(gained, c.experience_gain_cap)
            self.max_party_experience = party_experience
        self._last_party_experience = party_experience

        moves = set(state.party_moves or ())
        new_moves = moves - self.seen_moves
        if new_moves:
            components["new_move"] = c.new_move * len(new_moves)
            self.seen_moves |= new_moves

        if state.got_pokedex:
            seen = _set_bits(state.pokedex_seen)
            owned = _set_bits(state.pokedex_owned)
            newly_seen = seen - self.seen_species
            newly_owned = owned - self.owned_species
            if newly_seen:
                components["species_seen"] = c.species_seen * len(newly_seen)
            if newly_owned:
                components["species_owned"] = c.species_owned * len(newly_owned)
                if active_battle:
                    self._battle_progressed = True
            self.seen_species |= newly_seen
            self.owned_species |= newly_owned

        items = set(state.bag_item_ids or ())
        new_items = items - self.seen_items
        if new_items:
            components["new_item"] = c.new_item * len(new_items)
            self.seen_items |= new_items

        if previous_battle in {1, 2} and battle == 0:
            if self._battle_progressed:
                components["battle_success"] = c.battle_success
                battle_event = "success"
            else:
                battle_event = "ended_without_progress"
            self._battle_progressed = False
            self._clear_enemy_health()
        elif battle == 0xFF and previous_battle != 0xFF:
            components["blackout"] = c.blackout
            battle_event = "blackout"
            self._battle_progressed = False
            self._clear_enemy_health()
        self._last_battle = battle

        if action_button == self._last_action:
            self._action_streak += 1
        else:
            self._last_action = action_button
            self._action_streak = 1
        if self._action_streak >= 6:
            components["repeated_action"] = c.repeated_action
        if loop_detected:
            components["visual_loop"] = c.visual_loop

        total = float(sum(components.values()))
        self.total_reward += total
        if components:
            self.reward_events += 1
            self.component_totals.update(components)
        return RewardStep(total, components, battle_event)

    @staticmethod
    def _mart_distance(state: PokemonRedState) -> int | None:
        if state.map_id != VIRIDIAN_CITY_MAP_ID or state.player_x is None or state.player_y is None:
            return None
        door_x, door_y = VIRIDIAN_MART_DOOR
        return abs(state.player_x - door_x) + abs(state.player_y - door_y)

    @staticmethod
    def _position(state: PokemonRedState) -> tuple[int, int, int] | None:
        if None in (state.map_id, state.player_x, state.player_y):
            return None
        return int(state.map_id), int(state.player_x), int(state.player_y)

    def _prime_enemy_health(self, state: PokemonRedState) -> None:
        self._enemy_hp_floor = state.enemy_hp
        self._last_enemy_hp = state.enemy_hp
        self._battle_damage_credit = 0.0

    def _clear_enemy_health(self) -> None:
        self._enemy_hp_floor = None
        self._last_enemy_hp = None
        self._battle_damage_credit = 0.0

    def checkpoint_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "config": asdict(self.config),
            "seen_maps": sorted(self.seen_maps),
            "seen_positions": [list(value) for value in sorted(self.seen_positions)],
            "seen_warps": [list(value) for value in sorted(self.seen_warps)],
            "seen_events": sorted(self.seen_events),
            "seen_species": sorted(self.seen_species),
            "owned_species": sorted(self.owned_species),
            "seen_items": sorted(self.seen_items),
            "seen_moves": sorted(self.seen_moves),
            "badge_bits": self.badge_bits,
            "max_party_count": self.max_party_count,
            "max_party_level": self.max_party_level,
            "max_party_experience": self.max_party_experience,
            "best_milestone_index": self.best_milestone_index,
            "total_reward": self.total_reward,
            "reward_events": self.reward_events,
            "component_totals": dict(sorted(self.component_totals.items())),
            "initialized": self._initialized,
        }

    @classmethod
    def from_checkpoint_dict(cls, value: Mapping[str, Any]) -> FullGameRewardTracker:
        if int(value.get("schema_version", -1)) != 1:
            raise ValueError("Unsupported full-game reward checkpoint")
        config = dict(value.get("config", {}))
        if "battle_ended" in config:
            raise ValueError("Legacy battle-ending reward memory cannot enter the new protocol")
        tracker = cls(config=FullGameRewardConfig(**config))
        tracker.seen_maps = {int(item) for item in value.get("seen_maps", [])}
        tracker.seen_positions = {
            (int(item[0]), int(item[1]), int(item[2])) for item in value.get("seen_positions", [])
        }
        tracker.seen_warps = {(int(item[0]), int(item[1])) for item in value.get("seen_warps", [])}
        for name in ("seen_events", "seen_species", "owned_species", "seen_items", "seen_moves"):
            setattr(tracker, name, {int(item) for item in value.get(name, [])})
        tracker.badge_bits = int(value.get("badge_bits", 0))
        tracker.max_party_count = int(value.get("max_party_count", 0))
        tracker.max_party_level = int(value.get("max_party_level", 0))
        tracker.max_party_experience = int(value.get("max_party_experience", 0))
        tracker.best_milestone_index = int(value.get("best_milestone_index", 0))
        tracker.total_reward = float(value.get("total_reward", 0))
        tracker.reward_events = int(value.get("reward_events", 0))
        tracker.component_totals = Counter(
            {str(k): float(v) for k, v in value.get("component_totals", {}).items()}
        )
        tracker._initialized = bool(value.get("initialized", False))
        return tracker


class FrontierSelfImitationEmitter:
    """Pixels-only policy that learns only from replay-verified milestone suffixes."""

    policy_id = FRONTIER_LEARNER_POLICY_ID

    def __init__(
        self,
        rng: random.Random,
        model_directory: Path,
        run_directory: Path,
        *,
        expected_model_sha256: str,
        learning_rate: float,
        training_epochs: int,
        resume_state: Mapping[str, Any] | None = None,
    ) -> None:
        if learning_rate <= 0 or training_epochs < 1:
            raise ValueError("Frontier learner training settings are invalid")
        self._rng = rng
        self._actor: PixelsOnlyActor | None = None
        self._previous_frame: np.ndarray | None = None
        self._previous_action = -1
        self._recurrent_state: tuple[Any, Any] | None = None
        self._exploration_probability = 0.0
        self._forced_exploration_actions = 0
        self._episode_frames: list[np.ndarray] = []
        self._episode_previous_actions: list[int] = []
        self._episode_actions: list[int] = []
        self._training_epochs = training_epochs
        self._torch = require_torch()
        self._torch.set_num_threads(1)
        with contextlib.suppress(RuntimeError):
            self._torch.set_num_interop_threads(1)
        self._torch.use_deterministic_algorithms(True)
        directory = model_directory.expanduser().resolve()
        metadata_path = directory / "learner.json"
        model_path = directory / "learner.pt"
        if not metadata_path.is_file() or not model_path.is_file():
            raise ValueError("Frontier learning requires a completed apprentice learner bundle")
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        if (
            metadata.get("development_only") is not True
            or metadata.get("file_sha256") != expected_model_sha256
            or _sha256_file(model_path) != expected_model_sha256
        ):
            raise ValueError("Frontier learner seed model does not match its declared identity")
        self._model = build_apprentice_policy().to("cpu")
        seed_state = self._torch.load(model_path, map_location="cpu", weights_only=True)
        self._model.load_state_dict(seed_state, strict=True)
        seed_parameter_sha256 = _parameter_sha256(self._model)
        if metadata.get("parameter_sha256") != seed_parameter_sha256:
            raise ValueError("Frontier learner seed tensors do not match their metadata")
        self._anchor = {
            name: value.detach().clone() for name, value in self._model.state_dict().items()
        }
        self._optimizer = self._torch.optim.Adam(self._model.parameters(), lr=learning_rate)
        self._run_directory = run_directory
        self._latest_path = run_directory / "frontier-learner.pt"
        self._previous_path = run_directory / "frontier-learner.previous.pt"
        self.updates = 0
        self.promotions_learned = 0
        self.success_actions_learned = 0
        self.last_learned_milestone: str | None = None
        self._exemplars: list[dict[str, Any]] = []
        self.reward_tracker = FullGameRewardTracker()
        if resume_state is not None:
            self._restore(resume_state)
        self._model.eval()
        self._identity = {
            "policy_id": self.policy_id,
            "inputs": [
                "two_processed_pixel_frames",
                "previous_action",
                "recurrent_state",
                "seeded_prng_exploration",
            ],
            "pretrained_components": [
                {
                    "kind": "visual_apprentice_reverse_curriculum_development_model",
                    "file_sha256": expected_model_sha256,
                    "parameter_sha256": seed_parameter_sha256,
                }
            ],
            "frozen_weights": False,
            "trainer_routes_exploration": True,
        }

    def public_identity(self) -> dict[str, object]:
        return dict(self._identity)

    def public_status(self) -> dict[str, Any]:
        return {
            "protocol": FRONTIER_LEARNER_POLICY_ID,
            "updates": self.updates,
            "promotions_learned": self.promotions_learned,
            "success_actions_learned": self.success_actions_learned,
            "last_learned_milestone": self.last_learned_milestone,
            "exploration_probability": round(self._exploration_probability, 4),
            "forced_exploration_actions": self._forced_exploration_actions,
            "reward_total": round(self.reward_tracker.total_reward, 4),
            "reward_events": self.reward_tracker.reward_events,
            "reward_components": dict(sorted(self.reward_tracker.component_totals.items())),
        }

    def reset(self, actor: PixelsOnlyActor, *, exploration_probability: float) -> None:
        if not 0 <= exploration_probability <= 1:
            raise ValueError("Frontier learner exploration must be a probability")
        self._actor = actor
        current = preprocess_apprentice_frame(actor.observe())
        self._previous_frame = current
        self._previous_action = -1
        self._recurrent_state = None
        self._exploration_probability = exploration_probability
        self._forced_exploration_actions = 0
        self._episode_frames = []
        self._episode_previous_actions = []
        self._episode_actions = []

    def force_exploration(self, actions: int) -> None:
        if actions < 1:
            raise ValueError("A loop escape burst must contain at least one action")
        self._forced_exploration_actions = max(self._forced_exploration_actions, actions)

    def emit(self) -> BlindAction:
        if self._actor is None or self._previous_frame is None:
            raise RuntimeError("Frontier learner must reset after every checkpoint restore")
        current = preprocess_apprentice_frame(self._actor.observe())
        pair = np.stack((self._previous_frame, current), axis=0)
        with self._torch.no_grad():
            logits, self._recurrent_state = self._model.step(
                self._torch.from_numpy(pair).unsqueeze(0),
                self._torch.tensor([self._previous_action], dtype=self._torch.long),
                self._recurrent_state,
            )
        epsilon = 1.0 if self._forced_exploration_actions else self._exploration_probability
        if self._rng.random() < epsilon:
            action_index = self._rng.randrange(len(BLIND_ACTIONS))
        else:
            action_index = int(logits.argmax(dim=-1).item())
        if self._forced_exploration_actions:
            self._forced_exploration_actions -= 1
        self._episode_frames.append(pair.copy())
        self._episode_previous_actions.append(self._previous_action)
        self._episode_actions.append(action_index)
        self._previous_frame = current
        self._previous_action = action_index
        return BlindAction(
            button=BLIND_ACTIONS[action_index],
            hold_frames=ACTION_HOLD_FRAMES,
            release_frames=ACTION_RELEASE_FRAMES,
        )

    def learn_from_verified_promotion(self, milestone: MilestoneProgress) -> dict[str, Any]:
        if not self._episode_actions:
            raise RuntimeError("A verified promotion cannot have an empty learning episode")
        frames = np.stack(self._episode_frames).astype(np.uint8, copy=False)
        previous = np.asarray(self._episode_previous_actions, dtype=np.int64)
        actions = np.asarray(self._episode_actions, dtype=np.int64)
        episode = {"frames": frames, "previous": previous, "actions": actions}
        losses: list[float] = []
        self._model.train()
        horizons = [8, 16, 32, 64, 128, 256, 512, len(actions)]
        starts = sorted({max(0, len(actions) - horizon) for horizon in horizons})
        training_episodes = [episode, *self._rehearsal_sample()]
        for _epoch in range(self._training_epochs):
            for source in training_episodes:
                source_length = len(source["actions"])
                source_starts = starts if source is episode else [0]
                for begin in source_starts:
                    if begin >= source_length:
                        continue
                    frame_values = source["frames"][begin:].copy()
                    previous_values = source["previous"][begin:].copy()
                    frame_values[0, 0] = frame_values[0, 1]
                    previous_values[0] = -1
                    logits, _state = self._model(
                        self._torch.from_numpy(frame_values).unsqueeze(0),
                        self._torch.from_numpy(previous_values).unsqueeze(0),
                    )
                    targets = self._torch.from_numpy(source["actions"][begin:]).unsqueeze(0)
                    imitation = self._torch.nn.functional.cross_entropy(
                        logits.reshape(-1, len(BLIND_ACTIONS)), targets.reshape(-1)
                    )
                    anchor = self._torch.zeros((), dtype=imitation.dtype)
                    for name, parameter in self._model.named_parameters():
                        anchor = anchor + (parameter - self._anchor[name]).pow(2).mean()
                    loss = imitation + 1e-5 * anchor
                    self._optimizer.zero_grad(set_to_none=True)
                    loss.backward()
                    self._torch.nn.utils.clip_grad_norm_(self._model.parameters(), 1.0)
                    self._optimizer.step()
                    losses.append(float(loss.detach().item()))
                    self.updates += 1
        self._model.eval()
        exemplar_start = max(0, len(actions) - 128)
        self._exemplars.append(
            {
                "milestone": milestone.key,
                "frames": frames[exemplar_start:].copy(),
                "previous": previous[exemplar_start:].copy(),
                "actions": actions[exemplar_start:].copy(),
            }
        )
        self.promotions_learned += 1
        self.success_actions_learned += len(actions)
        self.last_learned_milestone = milestone.key
        self._persist()
        return {
            "milestone": milestone.key,
            "actions": len(actions),
            "optimizer_steps": len(losses),
            "mean_loss": round(sum(losses) / len(losses), 6),
            "parameter_sha256": _parameter_sha256(self._model),
        }

    def _rehearsal_sample(self) -> list[dict[str, Any]]:
        if len(self._exemplars) <= 8:
            return list(self._exemplars)
        indexes = np.linspace(0, len(self._exemplars) - 1, num=8, dtype=int)
        return [self._exemplars[int(index)] for index in indexes]

    def _persist(self) -> None:
        serialized_exemplars = [
            {
                "milestone": exemplar["milestone"],
                "frames": self._torch.from_numpy(exemplar["frames"]),
                "previous": self._torch.from_numpy(exemplar["previous"]),
                "actions": self._torch.from_numpy(exemplar["actions"]),
            }
            for exemplar in self._exemplars
        ]
        payload = {
            "schema_version": FRONTIER_LEARNER_SCHEMA,
            "policy_id": self.policy_id,
            "model": self._model.state_dict(),
            "optimizer": self._optimizer.state_dict(),
            "updates": self.updates,
            "promotions_learned": self.promotions_learned,
            "success_actions_learned": self.success_actions_learned,
            "last_learned_milestone": self.last_learned_milestone,
            "exemplars": serialized_exemplars,
        }
        temporary = self._latest_path.with_suffix(".pt.tmp")
        self._torch.save(payload, temporary)
        with temporary.open("rb") as source:
            os.fsync(source.fileno())
        if self._latest_path.exists():
            os.replace(self._latest_path, self._previous_path)
        os.replace(temporary, self._latest_path)

    def checkpoint_state(self) -> dict[str, Any]:
        return {
            "schema_version": FRONTIER_LEARNER_SCHEMA,
            "policy_id": self.policy_id,
            "updates": self.updates,
            "model_file_sha256": (None if self.updates == 0 else _sha256_file(self._latest_path)),
            "parameter_sha256": _parameter_sha256(self._model),
            "promotions_learned": self.promotions_learned,
            "success_actions_learned": self.success_actions_learned,
            "last_learned_milestone": self.last_learned_milestone,
            "reward_tracker": self.reward_tracker.checkpoint_dict(),
        }

    def _restore(self, state: Mapping[str, Any]) -> None:
        if (
            int(state.get("schema_version", -1)) != FRONTIER_LEARNER_SCHEMA
            or state.get("policy_id") != self.policy_id
        ):
            raise ValueError("Frontier learner checkpoint identity does not match")
        expected_file = state.get("model_file_sha256")
        if expected_file is not None:
            matching = next(
                (
                    path
                    for path in (self._latest_path, self._previous_path)
                    if path.is_file() and _sha256_file(path) == expected_file
                ),
                None,
            )
            if matching is None:
                raise ValueError("Frontier learner model file does not match the runner checkpoint")
            payload = self._torch.load(matching, map_location="cpu", weights_only=True)
            if (
                int(payload.get("schema_version", -1)) != FRONTIER_LEARNER_SCHEMA
                or payload.get("policy_id") != self.policy_id
            ):
                raise ValueError("Frontier learner model payload is incompatible")
            self._model.load_state_dict(payload["model"], strict=True)
            self._optimizer.load_state_dict(payload["optimizer"])
            self.updates = int(payload["updates"])
            self.promotions_learned = int(payload["promotions_learned"])
            self.success_actions_learned = int(payload["success_actions_learned"])
            self.last_learned_milestone = payload.get("last_learned_milestone")
            self._exemplars = [
                {
                    "milestone": str(exemplar["milestone"]),
                    "frames": exemplar["frames"].cpu().numpy(),
                    "previous": exemplar["previous"].cpu().numpy(),
                    "actions": exemplar["actions"].cpu().numpy(),
                }
                for exemplar in payload.get("exemplars", [])
            ]
        if self.updates != int(state.get("updates", -1)):
            raise ValueError("Frontier learner update count does not match")
        if _parameter_sha256(self._model) != state.get("parameter_sha256"):
            raise ValueError("Frontier learner parameters do not match the runner checkpoint")
        reward_state = state.get("reward_tracker")
        if not isinstance(reward_state, Mapping):
            raise ValueError("Frontier learner reward checkpoint is missing")
        self.reward_tracker = FullGameRewardTracker.from_checkpoint_dict(reward_state)
