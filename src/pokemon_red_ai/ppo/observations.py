"""Observation construction and the per-episode trackers that feed it."""

from __future__ import annotations

import hashlib
from collections import deque
from dataclasses import dataclass, field

import numpy as np

from pokemon_red_ai.blind import (
    ACTION_HOLD_FRAMES,
    ACTION_RELEASE_FRAMES,
    BLIND_ACTIONS,
    NOOP_ACTION,
)
from pokemon_red_ai.emulator import PokemonRedEmulator
from pokemon_red_ai.expedition import (
    MilestoneProgress,
)
from pokemon_red_ai.milestones import MILESTONES
from pokemon_red_ai.ppo.constants import (
    GOAL_COUNT,
    MAP_MEMORY_SIZE,
    PRIVILEGED_STATE_SIZE,
    SKILL_COUNT,
)
from pokemon_red_ai.quest_navigation import route_guidance
from pokemon_red_ai.state import (
    PokemonRedState,
)


def _state_vector(state: PokemonRedState) -> np.ndarray:
    battle = np.zeros(4, dtype=np.float32)
    battle_index = {0: 0, 1: 1, 2: 2, 0xFF: 3}.get(state.battle_state or 0, 0)
    battle[battle_index] = 1
    badges = np.asarray(
        [float(bool((state.badge_bits or 0) & (1 << index))) for index in range(8)],
        dtype=np.float32,
    )
    base = np.asarray(
        [
            float(state.game_started),
            (state.map_id or 0) / 255,
            (state.player_x or 0) / 255,
            (state.player_y or 0) / 255,
            (state.party_count or 0) / 6,
        ],
        dtype=np.float32,
    )
    tail = np.asarray(
        [
            state.max_party_level / 100,
            state.pokedex_seen_count / 151,
            state.pokedex_owned_count / 151,
            state.event_flags_count / (319 * 8),
            len(state.bag_item_ids or ()) / 20,
            float(bool(state.got_pokedex)),
            len(set(state.party_species or ())) / 6,
        ],
        dtype=np.float32,
    )
    value = np.concatenate((base, battle, badges, tail))
    if value.shape != (PRIVILEGED_STATE_SIZE,):
        raise RuntimeError("Privileged PPO state vector changed without a protocol bump")
    return np.clip(value, 0, 1)


def _one_hot_action(action: int) -> np.ndarray:
    value = np.zeros(len(BLIND_ACTIONS), dtype=np.float32)
    if 0 <= action < len(BLIND_ACTIONS):
        value[action] = 1
    return value


def _action_history(actions: deque[int]) -> np.ndarray:
    return np.concatenate([_one_hot_action(action) for action in actions])


def _goal_observation(progress: MilestoneProgress) -> np.ndarray:
    value = np.zeros(GOAL_COUNT, dtype=np.float32)
    value[min(progress.index + 1, GOAL_COUNT - 1)] = 1
    return value


def _skill_observation(state: PokemonRedState, progress: MilestoneProgress) -> np.ndarray:
    value = np.zeros(SKILL_COUNT, dtype=np.float32)
    if state.battle_state in {1, 2}:
        index = 2  # battle
    elif progress.index < len(MILESTONES) and MILESTONES[progress.index].kind == "landmark":
        index = 0  # navigation
    else:
        index = 1  # interaction/dialogue/menu
    value[index] = 1
    return value


@dataclass(slots=True)
class EpisodeMapMemory:
    """Trainer-built visited map disclosed only to the assisted actor."""

    visited: dict[int, set[tuple[int, int]]] = field(default_factory=dict)

    def reset(self, state: PokemonRedState) -> None:
        self.visited = {}
        self.observe(state)

    def observe(self, state: PokemonRedState) -> None:
        if None in (state.map_id, state.player_x, state.player_y):
            return
        x, y = int(state.player_x), int(state.player_y)
        if 0 <= x < MAP_MEMORY_SIZE and 0 <= y < MAP_MEMORY_SIZE:
            self.visited.setdefault(int(state.map_id), set()).add((x, y))

    def observation(self, state: PokemonRedState) -> np.ndarray:
        value = np.zeros((2, MAP_MEMORY_SIZE, MAP_MEMORY_SIZE), dtype=np.uint8)
        if state.map_id is None:
            return value
        for x, y in self.visited.get(state.map_id, set()):
            value[0, y, x] = 255
        if state.player_x is not None and state.player_y is not None:
            x, y = int(state.player_x), int(state.player_y)
            if 0 <= x < MAP_MEMORY_SIZE and 0 <= y < MAP_MEMORY_SIZE:
                value[1, y, x] = 255
        return value


def _map_context(
    state: PokemonRedState,
    progress: MilestoneProgress,
    observed_edges: set[tuple[int, int]] | tuple[()] = (),
) -> np.ndarray:
    guidance = route_guidance(state, progress, observed_edges)
    return np.asarray(
        [
            (state.map_id or 0) / 255,
            min(progress.index + 1, GOAL_COUNT - 1) / max(1, GOAL_COUNT - 1),
            0.0 if guidance.next_map is None else (guidance.next_map + 1) / 256,
            0.0 if guidance.distance is None else min(guidance.distance, 8) / 8,
        ],
        dtype=np.float32,
    )


@dataclass(slots=True)
class VisualStagnationTracker:
    """Trainer-only loop watchdog; none of this state enters the actor observation."""

    cycle_window: int = 128
    cycle_unique_limit: int = 8
    hard_limit: int = 1_024
    use_authored_guidance: bool = True
    _frames: deque[bytes] = field(default_factory=lambda: deque(maxlen=128))
    _seen_positions: set[tuple[int, int, int]] = field(default_factory=set)
    _best_progress: int = 0
    _max_experience: int = 0
    _max_events: int = 0
    _max_owned: int = 0
    _max_badges: int = 0
    _enemy_hp_floor: int | None = None
    _last_battle: int = 0
    _max_mart_script: int = 0
    _goal_key: str | None = None
    _best_route_distance: int | None = None
    _stagnant_actions: int = 0

    def reset(self, state: PokemonRedState, progress: MilestoneProgress) -> None:
        self._frames = deque(maxlen=self.cycle_window)
        self._seen_positions = set()
        if state.map_id is not None and state.player_x is not None and state.player_y is not None:
            self._seen_positions.add((state.map_id, state.player_x, state.player_y))
        self._best_progress = progress.index if self.use_authored_guidance else 0
        self._max_experience = state.total_party_experience
        self._max_events = state.event_flags_count
        self._max_owned = state.pokedex_owned_count
        self._max_badges = state.badge_count
        self._enemy_hp_floor = state.enemy_hp
        self._last_battle = state.battle_state or 0
        self._max_mart_script = state.viridian_mart_script or 0 if self.use_authored_guidance else 0
        if self.use_authored_guidance:
            guidance = route_guidance(state, progress)
            self._goal_key = guidance.goal_key
            self._best_route_distance = guidance.distance
        else:
            self._goal_key = None
            self._best_route_distance = None
        self._stagnant_actions = 0

    def observe(
        self,
        frame: np.ndarray,
        state: PokemonRedState,
        progress: MilestoneProgress,
        *,
        perceptual_activity: bool = False,
    ) -> str | None:
        useful_progress = False
        position = (
            (state.map_id, state.player_x, state.player_y)
            if None not in (state.map_id, state.player_x, state.player_y)
            else None
        )
        if position is not None and position not in self._seen_positions:
            self._seen_positions.add(position)  # type: ignore[arg-type]
            useful_progress = True
        generic_progress = (
            (state.total_party_experience, "_max_experience"),
            (state.event_flags_count, "_max_events"),
            (state.pokedex_owned_count, "_max_owned"),
            (state.badge_count, "_max_badges"),
        )
        authored_progress = (
            (progress.index, "_best_progress"),
            (state.viridian_mart_script or 0, "_max_mart_script"),
        )
        for current, name in generic_progress + (
            authored_progress if self.use_authored_guidance else ()
        ):
            if current > getattr(self, name):
                setattr(self, name, current)
                useful_progress = True
        if self.use_authored_guidance:
            guidance = route_guidance(state, progress)
            if guidance.goal_key != self._goal_key:
                self._goal_key = guidance.goal_key
                self._best_route_distance = guidance.distance
                useful_progress = True
            elif guidance.distance is not None and (
                self._best_route_distance is None or guidance.distance < self._best_route_distance
            ):
                self._best_route_distance = guidance.distance
                useful_progress = True
        battle = state.battle_state or 0
        if battle in {1, 2}:
            if self._last_battle not in {1, 2}:
                self._enemy_hp_floor = state.enemy_hp
            elif (
                state.enemy_hp is not None
                and self._enemy_hp_floor is not None
                and state.enemy_hp < self._enemy_hp_floor
            ):
                self._enemy_hp_floor = state.enemy_hp
                useful_progress = True
        else:
            self._enemy_hp_floor = None
        self._last_battle = battle

        # Perceptual signatures ignore tiny animation changes but retain menus and cursor cycles.
        signature = hashlib.blake2b(
            (frame[::4, ::4] // 32).astype(np.uint8).tobytes(), digest_size=8
        ).digest()
        self._frames.append(signature)
        if useful_progress:
            self._stagnant_actions = 0
            self._frames.clear()
            self._frames.append(signature)
            return None
        if perceptual_activity:
            # V10 treats visually effective backtracking as activity without clearing the
            # signature window that still detects short oscillations.  Earlier protocols pass
            # the default False and retain their frozen watchdog behavior.
            self._stagnant_actions = 0
        else:
            self._stagnant_actions += 1
        if self._stagnant_actions >= self.hard_limit:
            return "progress_stagnation"
        if (
            len(self._frames) == self.cycle_window
            and len(set(self._frames)) <= self.cycle_unique_limit
        ):
            return "visual_cycle"
        return None


def _execute_action(emulator: PokemonRedEmulator, action_index: int) -> bool:
    action = BLIND_ACTIONS[action_index]
    if action == NOOP_ACTION:
        return emulator.tick(ACTION_HOLD_FRAMES + ACTION_RELEASE_FRAMES, render_last=True)
    return emulator.press(
        action,
        hold_frames=ACTION_HOLD_FRAMES,
        release_frames=ACTION_RELEASE_FRAMES,
    )
